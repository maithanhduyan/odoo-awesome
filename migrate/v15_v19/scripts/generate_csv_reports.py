"""Generate CSV reports from migration results.

Reads id_map.json + queries both Odoo instances to produce per-model CSV files
with v15_id, v19_id, and a human-readable label (e.g. partner name).

Output: migrate/reports/<model>_<timestamp>.csv
"""

import csv
import json
import sys
import xmlrpc.client
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.config import (
    V15_URL, V15_DB, V15_USER, V15_PASSWORD,
    V19_URL, V19_DB, V19_USER, V19_PASSWORD,
)

REPORT_DIR = Path(__file__).parent / "migrate" / "reports"
MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

# Which field to use as label for each model
MODEL_LABEL = {
    "res.country": "name",
    "res.country.state": "name",
    "res.currency": "name",
    "res.partner.industry": "full_name",
    "res.partner.title": "name",
    "res.partner.category": "name",
    "res.company": "name",
    "res.partner": "name",
    "res.users": "login",
    "res.partner.bank": "acc_number",
    "res.bank": "name",
}


def connect(url, db, user, pwd, label):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, pwd, {})
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    print(f"[{label}] Connected uid={uid}")
    return uid, models


def search_read(models, uid, url_cfg, model, domain, fields):
    db, pwd = url_cfg
    return models.execute_kw(db, uid, pwd, model, "search_read",
                             [domain], {"fields": fields})


def generate_reports():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Load id_map
    id_map = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    total_mappings = sum(len(v) for v in id_map.values())
    print(f"Loaded id_map: {len(id_map)} models, {total_mappings} mappings")

    # Connect
    uid15, m15 = connect(V15_URL, V15_DB, V15_USER, V15_PASSWORD, "v15")
    uid19, m19 = connect(V19_URL, V19_DB, V19_USER, V19_PASSWORD, "v19")

    summary_rows = []

    for model, mappings in id_map.items():
        if not mappings:
            continue

        label_field = MODEL_LABEL.get(model, "name")
        v15_ids = [int(k) for k in mappings.keys()]
        v19_ids = list(mappings.values())

        # Read labels from both sides
        v15_labels = {}
        v19_labels = {}

        try:
            for batch_start in range(0, len(v15_ids), 200):
                batch = v15_ids[batch_start:batch_start + 200]
                recs = search_read(m15, uid15, (V15_DB, V15_PASSWORD),
                                   model, [("id", "in", batch)], ["id", label_field])
                for r in recs:
                    v15_labels[r["id"]] = r.get(label_field, "")
        except Exception:
            pass  # Some models may not have the label field

        try:
            for batch_start in range(0, len(v19_ids), 200):
                batch = v19_ids[batch_start:batch_start + 200]
                recs = search_read(m19, uid19, (V19_DB, V19_PASSWORD),
                                   model, [("id", "in", batch)], ["id", label_field])
                for r in recs:
                    v19_labels[r["id"]] = r.get(label_field, "")
        except Exception:
            pass

        # Write CSV
        safe_model = model.replace(".", "_")
        csv_path = REPORT_DIR / f"{safe_model}_{ts}.csv"

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["v15_id", "v19_id", "v15_label", "v19_label", "status"])

            for v15_str, v19_id in sorted(mappings.items(), key=lambda x: int(x[0])):
                v15_id = int(v15_str)
                v15_label = v15_labels.get(v15_id, "")
                v19_label = v19_labels.get(v19_id, "")

                # Normalize label for comparison
                if isinstance(v15_label, (list, tuple)):
                    v15_label = v15_label[1] if len(v15_label) > 1 else str(v15_label)
                if isinstance(v19_label, (list, tuple)):
                    v19_label = v19_label[1] if len(v19_label) > 1 else str(v19_label)

                status = "OK" if v15_label == v19_label else "MAPPED"
                writer.writerow([v15_id, v19_id, v15_label, v19_label, status])

        count = len(mappings)
        summary_rows.append((model, count, csv_path.name))
        print(f"  {model}: {count} records -> {csv_path.name}")

    # Write summary CSV
    summary_path = REPORT_DIR / f"_summary_{ts}.csv"
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["model", "count", "csv_file"])
        for row in summary_rows:
            writer.writerow(row)

    print(f"\n{'='*60}")
    print(f"Summary: {len(summary_rows)} models, {total_mappings} total mappings")
    print(f"Reports saved to: {REPORT_DIR}")
    print(f"Summary file: {summary_path.name}")


if __name__ == "__main__":
    generate_reports()
