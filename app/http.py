import json
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


@dataclass
class HttpResponse:
    status: int
    payload: Optional[Any]
    raw: str


class HttpClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30, max_retries: int = 4):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries

    def _build_url(self, path: str, params: Optional[dict] = None) -> str:
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        return url

    def request_json(self, method: str, path: str, params: Optional[dict] = None, payload: Optional[dict] = None) -> HttpResponse:
        url = self._build_url(path, params)

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = Request(url, headers=headers, data=data, method=method.upper())

        attempt = 0
        while True:
            attempt += 1
            try:
                with urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    try:
                        return HttpResponse(status=resp.status, payload=json.loads(raw), raw=raw)
                    except json.JSONDecodeError:
                        return HttpResponse(status=resp.status, payload=None, raw=raw)

            except HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace")
                status = e.code

                # Retry only on 429 and 5xx
                if (status == 429 or 500 <= status <= 599) and attempt <= self.max_retries:
                    backoff = min(8.0, 0.5 * (2 ** (attempt - 1)))
                    time.sleep(backoff)
                    continue

                try:
                    payload_obj = json.loads(raw)
                except json.JSONDecodeError:
                    payload_obj = None

                return HttpResponse(status=status, payload=payload_obj, raw=raw)

            except URLError:
                # network error, retry a bit
                if attempt <= self.max_retries:
                    backoff = min(8.0, 0.5 * (2 ** (attempt - 1)))
                    time.sleep(backoff)
                    continue
                raise
