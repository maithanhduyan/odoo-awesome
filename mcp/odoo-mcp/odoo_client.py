"""
Odoo JSON-RPC async client for MCP server.

Uses httpx for async HTTP requests to Odoo's /jsonrpc endpoint.
Stateless authentication (uid + password per request).
"""

import os
import logging
from time import perf_counter
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ODOO_URL = os.getenv("ODOO_URL", "http://localhost")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ODOO_USER = os.getenv("ODOO_USER", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")

# Timeout for Odoo requests (seconds)
REQUEST_TIMEOUT = 30.0


class OdooClientError(Exception):
    """Raised when Odoo JSON-RPC returns an error."""


class OdooClient:
    """Async Odoo JSON-RPC client."""

    def __init__(
        self,
        url: str = ODOO_URL,
        db: str = ODOO_DB,
        user: str = ODOO_USER,
        password: str = ODOO_PASSWORD,
    ):
        self.url = url.rstrip("/")
        self.db = db
        self.user = user
        self.password = password
        self._uid: int | None = None
        self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        self._request_id = 0

    async def _jsonrpc(self, service: str, method: str, args: list) -> Any:
        """Execute a JSON-RPC call to Odoo."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args,
            },
            "id": self._request_id,
        }
        resp = await self._client.post(f"{self.url}/jsonrpc", json=payload)
        resp.raise_for_status()
        result = resp.json()

        if "error" in result:
            err = result["error"]
            msg = err.get("data", {}).get("message", err.get("message", str(err)))
            raise OdooClientError(f"Odoo RPC error: {msg}")

        return result.get("result")

    async def authenticate(self) -> int:
        """Authenticate and return uid. Caches result."""
        if self._uid is not None:
            return self._uid
        uid = await self._jsonrpc(
            "common", "authenticate", [self.db, self.user, self.password, {}]
        )
        if not uid:
            raise OdooClientError(
                f"Authentication failed for {self.user}@{self.db}"
            )
        self._uid = uid
        logger.info("Authenticated as uid=%d on db=%s", uid, self.db)
        return uid

    async def execute_kw(
        self,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> Any:
        """Call execute_kw on an Odoo model."""
        uid = await self.authenticate()
        rpc_args = args or []
        rpc_kwargs = kwargs or {}
        started_at = perf_counter()
        logger.info("RPC start %s.%s args=%s kwargs=%s", model, method, rpc_args, rpc_kwargs)
        try:
            result = await self._jsonrpc(
                "object",
                "execute_kw",
                [self.db, uid, self.password, model, method, rpc_args, rpc_kwargs],
            )
        except Exception:
            duration_ms = round((perf_counter() - started_at) * 1000, 1)
            logger.exception("RPC failed %s.%s duration_ms=%s", model, method, duration_ms)
            raise

        duration_ms = round((perf_counter() - started_at) * 1000, 1)
        result_count = len(result) if isinstance(result, list) else 1
        logger.info(
            "RPC done %s.%s duration_ms=%s result_count=%s",
            model,
            method,
            duration_ms,
            result_count,
        )
        return result

    # ── Convenience methods ───────────────────────────────────

    async def search_read(
        self,
        model: str,
        domain: list | None = None,
        fields: list[str] | None = None,
        limit: int = 80,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict]:
        """Search and read records."""
        kwargs: dict[str, Any] = {"limit": limit, "offset": offset}
        if fields:
            kwargs["fields"] = fields
        if order:
            kwargs["order"] = order
        return await self.execute_kw(
            model, "search_read", [domain or []], kwargs
        )

    async def read_group(
        self,
        model: str,
        domain: list | None = None,
        fields: list[str] | None = None,
        groupby: list[str] | None = None,
        limit: int | None = None,
        orderby: str | None = None,
        lazy: bool = True,
    ) -> list[dict]:
        """Read grouped/aggregated data."""
        kwargs: dict[str, Any] = {"lazy": lazy}
        if limit:
            kwargs["limit"] = limit
        if orderby:
            kwargs["orderby"] = orderby
        return await self.execute_kw(
            model,
            "read_group",
            [domain or [], fields or [], groupby or []],
            kwargs,
        )

    async def search_count(self, model: str, domain: list | None = None) -> int:
        """Count records matching domain."""
        return await self.execute_kw(model, "search_count", [domain or []])

    async def fields_get(
        self, model: str, attributes: list[str] | None = None
    ) -> dict:
        """Get model field definitions."""
        return await self.execute_kw(
            model,
            "fields_get",
            [],
            {"attributes": attributes or ["string", "type", "required", "readonly"]},
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
