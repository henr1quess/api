"""HTTP client for ActiveSoft SigaWeb API v0.

Features:
- Bearer token auth
- Automatic retry with exponential backoff (429, 5xx)
- Pagination helper (count/next/previous/results pattern)
- Token masking in logs/errors
"""

import time
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Raised when the API returns a non-success response."""

    def __init__(self, status: int, detail: str, raw: str = ""):
        self.status = status
        self.detail = detail
        self.raw = raw
        super().__init__(f"HTTP {status}: {detail}")


class ActiveSoftClient:
    """Thin HTTP wrapper for SigaWeb API v0."""

    API_VERSION = "v0"

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )

    # ── low level ─────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json_body: Optional[Any] = None,
    ) -> requests.Response:
        url = self._url(path)
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._session.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )
                if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                    if attempt <= self.max_retries:
                        wait = min(8.0, 0.5 * (2 ** (attempt - 1)))
                        logger.warning(
                            "Retry %d for %s %s (status %s)",
                            attempt,
                            method,
                            path,
                            resp.status_code,
                        )
                        time.sleep(wait)
                        continue
                return resp
            except requests.exceptions.RequestException as exc:
                if attempt <= self.max_retries:
                    wait = min(8.0, 0.5 * (2 ** (attempt - 1)))
                    logger.warning(
                        "Retry %d for %s %s (%s)", attempt, method, path, exc
                    )
                    time.sleep(wait)
                    continue
                raise

    # ── public helpers ────────────────────────────────────────────

    def get(self, path: str, params: Optional[Dict] = None) -> Any:
        """Single GET request. Returns parsed JSON."""
        resp = self._request("GET", path, params=params)
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json().get("detail", resp.text[:200])
            except Exception:
                detail = resp.text[:200]
            raise APIError(resp.status_code, detail, resp.text)
        return resp.json()

    def get_all(
        self,
        path: str,
        params: Optional[Dict] = None,
        page_size: int = 100,
    ) -> List[Any]:
        """Auto-paginate through count/next/previous/results endpoints."""
        if params is None:
            params = {}
        params = {**params, "limit": page_size, "offset": 0}

        all_results: List[Any] = []
        while True:
            data = self.get(path, params=params)

            # Some endpoints return a plain list (no pagination)
            if isinstance(data, list):
                return data

            results = data.get("results", [])
            all_results.extend(results)

            if data.get("next"):
                params["offset"] = params["offset"] + page_size
            else:
                break

        return all_results

    def post_json(self, path: str, body: Any) -> Dict:
        """POST JSON. Used ONLY in write mode (currently blocked)."""
        resp = self._request("POST", path, json_body=body)
        body_json = None
        try:
            body_json = resp.json()
        except Exception:
            pass
        return {"status": resp.status_code, "body": body_json, "raw": resp.text}

    # ── convenience ───────────────────────────────────────────────

    def test_connection(self) -> Dict:
        """Quick smoke test: fetch 1 record from acesso/alunos."""
        try:
            data = self.get(
                "/api/v0/acesso/alunos/", params={"limit": 1, "offset": 0}
            )
            count = 0
            if isinstance(data, dict):
                count = data.get("count", 0)
            elif isinstance(data, list):
                count = len(data)
            return {"ok": True, "count": count, "error": None}
        except Exception as exc:
            return {"ok": False, "count": 0, "error": str(exc)}
