from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class GeoLookupResult:
    country: str | None
    country_code: str | None
    region: str | None
    city: str | None
    lat: float | None
    lon: float | None
    raw_json: str


class GeoLookupError(RuntimeError):
    def __init__(
        self, message: str, *, status_code: int | None = None, raw_json: str | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.raw_json = raw_json


def _ip_api_base_url() -> str:
    # ip-api.com free endpoint is HTTP only.
    return (os.environ.get("IP_GEO_IP_API_BASE_URL") or "http://ip-api.com/json").rstrip("/")


def _timeout_seconds() -> float:
    raw = os.environ.get("IP_GEO_TIMEOUT_SECONDS")
    try:
        if raw is None:
            return 1.5
        return max(0.2, float(raw))
    except Exception:
        return 1.5


async def fetch_ip_api(ip: str) -> GeoLookupResult:
    url = f"{_ip_api_base_url()}/{ip}"

    # Request only what we need.
    params = {
        "fields": "status,message,country,countryCode,regionName,city,lat,lon,query",
    }

    timeout = httpx.Timeout(_timeout_seconds())
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params, headers={"Accept": "application/json"})

    raw_text = resp.text or ""
    status_code = resp.status_code

    # 429 needs special handling by the worker (backoff).
    if status_code == 429:
        raise GeoLookupError("rate_limited", status_code=status_code, raw_json=raw_text)

    if status_code < 200 or status_code >= 300:
        raise GeoLookupError(f"http_{status_code}", status_code=status_code, raw_json=raw_text)

    try:
        data = resp.json()
    except Exception:
        raise GeoLookupError("invalid_json", status_code=status_code, raw_json=raw_text)

    if not isinstance(data, dict):
        raise GeoLookupError("invalid_payload", status_code=status_code, raw_json=raw_text)

    if (data.get("status") or "").lower() != "success":
        msg = (data.get("message") or "fail").strip() or "fail"
        # Treat provider-level failures as non-fatal errors for retry policy.
        raise GeoLookupError(
            msg, status_code=status_code, raw_json=json.dumps(data, ensure_ascii=False)
        )

    # Store raw provider payload (JSON string) as requested.
    raw_json = json.dumps(data, ensure_ascii=False)

    def _maybe_float(v: Any) -> float | None:
        try:
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    return GeoLookupResult(
        country=(data.get("country") or None),
        country_code=(data.get("countryCode") or None),
        region=(data.get("regionName") or None),
        city=(data.get("city") or None),
        lat=_maybe_float(data.get("lat")),
        lon=_maybe_float(data.get("lon")),
        raw_json=raw_json,
    )
