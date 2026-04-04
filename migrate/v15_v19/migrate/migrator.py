"""
Core migration engine: reads from Odoo 15 via XML-RPC, writes to Odoo 19 via XML-RPC.

Handles:
- Authentication to both instances
- ID mapping (v15 id → v19 id) with JSON persistence
- xmlid-based mapping for seeded master data (countries, currencies, ...)
- Generic model migration with field mapping
- Batch operations and progress logging
"""

import json
import logging
import time
import xmlrpc.client
from pathlib import Path

log = logging.getLogger("migrate")

MAP_FILE = Path(__file__).parent / "id_map.json"


class OdooConnection:
    """XML-RPC connection to a single Odoo instance."""

    def __init__(self, url: str, db: str, user: str, password: str, label: str = ""):
        self.url = url
        self.db = db
        self.user = user
        self.password = password
        self.label = label
        self.uid = None
        self._models = None
        self._db_proxy = None

    def connect(self):
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        version = common.version()["server_version"]
        self.uid = common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise ConnectionError(f"[{self.label}] Authentication failed: {self.user}@{self.db}")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        log.info("[%s] Connected: %s (v%s) uid=%s", self.label, self.db, version, self.uid)

    def execute(self, model: str, method: str, *args, **kwargs):
        return self._models.execute_kw(self.db, self.uid, self.password, model, method, args, kwargs)

    def search_read(self, model: str, domain=None, fields=None, limit=0, order="id asc"):
        return self.execute(model, "search_read", domain or [], fields=fields, limit=limit, order=order)

    def search_count(self, model: str, domain=None):
        return self.execute(model, "search_count", domain or [])

    def create(self, model: str, vals: dict) -> int:
        return self.execute(model, "create", vals)

    def write(self, model: str, ids: list, vals: dict):
        return self.execute(model, "write", ids, vals)

    def read(self, model: str, ids: list, fields: list):
        return self.execute(model, "read", ids, fields=fields)

    def fields_get(self, model: str):
        return self.execute(model, "fields_get", attributes=["type", "readonly", "required", "relation"])


class IDMap:
    """Bidirectional ID mapping: v15_id ↔ v19_id, per model. Persisted to JSON."""

    def __init__(self, path: Path = MAP_FILE):
        self.path = path
        self._map: dict[str, dict[int, int]] = {}  # {model: {v15_id: v19_id}}
        self._load()

    def _load(self):
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            # JSON keys are strings; convert to int
            self._map = {
                model: {int(k): v for k, v in pairs.items()}
                for model, pairs in raw.items()
            }
            total = sum(len(v) for v in self._map.values())
            log.info("Loaded id_map: %d models, %d mappings", len(self._map), total)

    def save(self):
        self.path.write_text(json.dumps(self._map, indent=2, ensure_ascii=False), encoding="utf-8")

    def set(self, model: str, v15_id: int, v19_id: int):
        self._map.setdefault(model, {})[v15_id] = v19_id

    def get(self, model: str, v15_id: int) -> int | None:
        return self._map.get(model, {}).get(v15_id)

    def get_or_raise(self, model: str, v15_id: int) -> int:
        v19_id = self.get(model, v15_id)
        if v19_id is None:
            raise KeyError(f"No mapping for {model} v15_id={v15_id}")
        return v19_id

    def has(self, model: str, v15_id: int) -> bool:
        return v15_id in self._map.get(model, {})

    def count(self, model: str) -> int:
        return len(self._map.get(model, {}))

    def all(self, model: str) -> dict[int, int]:
        return dict(self._map.get(model, {}))


class Migrator:
    """
    Core migration engine.

    Usage:
        m = Migrator(v15_config, v19_config)
        m.connect()
        m.build_xmlid_map("res.country")       # map seeded data by xmlid
        m.migrate_model("res.partner", {...})   # migrate user data
        m.save()
    """

    def __init__(self, src: OdooConnection, dst: OdooConnection):
        self.src = src
        self.dst = dst
        self.id_map = IDMap()

    def connect(self):
        self.src.connect()
        self.dst.connect()

    def save(self):
        self.id_map.save()

    # ── xmlid-based mapping (for seeded master data) ────────────────────

    def build_xmlid_map(self, model: str, module: str = "base"):
        """Map records that exist on both sides by their xmlid (ir.model.data)."""
        src_xmlids = self.src.search_read(
            "ir.model.data",
            [("model", "=", model), ("module", "=", module)],
            ["name", "res_id"],
        )
        dst_xmlids = self.dst.search_read(
            "ir.model.data",
            [("model", "=", model), ("module", "=", module)],
            ["name", "res_id"],
        )
        dst_by_name = {x["name"]: x["res_id"] for x in dst_xmlids}

        mapped = 0
        for x in src_xmlids:
            if x["name"] in dst_by_name:
                self.id_map.set(model, x["res_id"], dst_by_name[x["name"]])
                mapped += 1

        log.info("xmlid map %s: %d/%d mapped", model, mapped, len(src_xmlids))

    # ── Generic model migration ─────────────────────────────────────────

    def migrate_model(
        self,
        model: str,
        fields: list[str],
        domain: list | None = None,
        field_transform: dict | None = None,
        m2o_models: dict | None = None,
        skip_existing: bool = True,
        batch_size: int = 100,
        context: dict | None = None,
    ) -> int:
        """
        Migrate records of a model from v15 to v19.

        Args:
            model: Odoo model name (e.g. "res.partner")
            fields: List of field names to read from v15 and write to v19
            domain: Optional search domain to filter v15 records
            field_transform: {field_name: callable(value) -> new_value}
            m2o_models: {field_name: related_model} for many2one fields that need ID mapping
            skip_existing: If True, skip records already in id_map
            batch_size: Number of records to read per batch
            context: Optional context dict for v19 create calls
        """
        domain = domain or []
        field_transform = field_transform or {}
        m2o_models = m2o_models or {}

        total = self.src.search_count(model, domain)
        log.info("Migrating %s: %d records (domain=%s)", model, total, domain)

        created = 0
        skipped = 0
        errors = 0
        offset = 0

        while offset < total:
            records = self.src.search_read(
                model, domain, fields=["id"] + fields, limit=batch_size, order="id asc",
            )
            if not records:
                break

            # Filter out already-migrated to avoid duplicate reads at offset
            remaining_domain = domain + [("id", ">", records[-1]["id"])] if len(records) == batch_size else domain
            actual_batch = records

            for rec in actual_batch:
                v15_id = rec["id"]

                if skip_existing and self.id_map.has(model, v15_id):
                    skipped += 1
                    continue

                vals = {}
                skip_record = False

                for field in fields:
                    value = rec[field]

                    # Handle many2one: (id, name) tuple → mapped id
                    if field in m2o_models and value:
                        if isinstance(value, (list, tuple)):
                            old_id = value[0]
                        else:
                            old_id = value
                        related_model = m2o_models[field]
                        new_id = self.id_map.get(related_model, old_id)
                        if new_id is None:
                            log.warning("  %s #%d: no mapping for %s.%s=%d, skipping field",
                                        model, v15_id, field, related_model, old_id)
                            continue
                        vals[field] = new_id
                    elif field in field_transform:
                        vals[field] = field_transform[field](value)
                    elif isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], int):
                        # Generic many2one fallback: take just the id
                        vals[field] = value[0]
                    else:
                        if value is not False or field in ("active",):
                            vals[field] = value

                if skip_record:
                    continue

                try:
                    if context:
                        # Use execute_kw directly to pass context
                        v19_id = self.dst.execute(model, "create", vals, context=context)
                    else:
                        v19_id = self.dst.create(model, vals)
                    self.id_map.set(model, v15_id, v19_id)
                    created += 1
                except Exception as e:
                    log.error("  %s #%d FAILED: %s (vals=%s)", model, v15_id, e, _truncate(vals))
                    errors += 1

            offset += len(records)
            if created % 50 == 0 and created > 0:
                self.id_map.save()

            # Use id-based pagination instead of offset
            if records:
                last_id = records[-1]["id"]
                domain = [d for d in (domain or []) if not (isinstance(d, (list, tuple)) and len(d) == 3 and d[0] == "id" and d[1] == ">")]
                domain.append(("id", ">", last_id))

        self.id_map.save()
        log.info("  %s done: %d created, %d skipped, %d errors", model, created, skipped, errors)
        return created

    # ── Many2many migration ─────────────────────────────────────────────

    def migrate_m2m(self, model: str, field: str, related_model: str, domain: list | None = None):
        """Migrate a many2many field by reading from v15 and writing to v19."""
        domain = domain or []
        records = self.src.search_read(model, domain, fields=["id", field])

        updated = 0
        for rec in records:
            v15_id = rec["id"]
            v19_id = self.id_map.get(model, v15_id)
            if v19_id is None:
                continue

            old_ids = rec[field]
            if not old_ids:
                continue

            new_ids = []
            for old_id in old_ids:
                new_id = self.id_map.get(related_model, old_id)
                if new_id is not None:
                    new_ids.append(new_id)

            if new_ids:
                try:
                    self.dst.write(model, [v19_id], {field: [(6, 0, new_ids)]})
                    updated += 1
                except Exception as e:
                    log.error("  m2m %s.%s #%d: %s", model, field, v15_id, e)

        log.info("  m2m %s.%s: %d updated", model, field, updated)

    # ── Attachment migration ────────────────────────────────────────────

    def migrate_attachments(self, domain: list | None = None, batch_size: int = 20):
        """Migrate ir.attachment records including binary data."""
        model = "ir.attachment"
        domain = domain or [("type", "=", "binary")]

        total = self.src.search_count(model, domain)
        log.info("Migrating attachments: %d records", total)

        created = 0
        skipped = 0
        errors = 0
        last_id = 0

        while True:
            batch_domain = domain + [("id", ">", last_id)]
            records = self.src.search_read(
                model, batch_domain,
                fields=["id", "name", "datas", "mimetype", "res_model", "res_id", "res_field", "type"],
                limit=batch_size, order="id asc",
            )
            if not records:
                break

            for rec in records:
                v15_id = rec["id"]
                last_id = v15_id

                if self.id_map.has(model, v15_id):
                    skipped += 1
                    continue

                # Map res_id to v19 if res_model is mapped
                res_model = rec.get("res_model")
                res_id = rec.get("res_id")
                v19_res_id = False
                if res_model and res_id:
                    v19_res_id = self.id_map.get(res_model, res_id)
                    if v19_res_id is None:
                        v19_res_id = False

                vals = {
                    "name": rec["name"],
                    "type": "binary",
                    "datas": rec.get("datas") or False,
                    "mimetype": rec.get("mimetype"),
                    "res_model": res_model or False,
                    "res_id": v19_res_id,
                    "res_field": rec.get("res_field") or False,
                }

                if not vals["datas"]:
                    skipped += 1
                    continue

                try:
                    v19_id = self.dst.create(model, vals)
                    self.id_map.set(model, v15_id, v19_id)
                    created += 1
                except Exception as e:
                    log.error("  attachment #%d (%s) FAILED: %s", v15_id, rec["name"], e)
                    errors += 1

            if created % 20 == 0 and created > 0:
                self.id_map.save()
                log.info("  attachments progress: %d/%d", created + skipped, total)

        self.id_map.save()
        log.info("  attachments done: %d created, %d skipped, %d errors", created, skipped, errors)
        return created


def _truncate(vals, max_len=200):
    """Truncate vals dict repr for logging."""
    s = str(vals)
    return s[:max_len] + "..." if len(s) > max_len else s
