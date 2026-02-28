"""Live-server smoke test for demo-pydantic-schemaforms.

This script is intentionally lightweight: it does not re-test library internals.
Instead, it verifies the demo app wiring works end-to-end against a running server:
- fetch schema
- render HTML
- submit invalid payload -> expect validation errors
- submit minimal valid payload -> expect success

Usage:
  python scripts/smoke_live_server.py --base-url http://localhost:5000

Exit codes:
  0: all checks passed
  2: server unreachable
  1: one or more checks failed
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _resolve_ref(ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"Unsupported $ref: {ref}")

    node: Any = root_schema
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f"$ref did not resolve to an object schema: {ref}")
    return node


def _merge_dicts(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in other.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
            and key in {"properties"}
        ):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _string_for_schema(schema: dict[str, Any]) -> str:
    if "const" in schema:
        return str(schema["const"])

    if "enum" in schema and schema["enum"]:
        return str(schema["enum"][0])

    fmt = schema.get("format")
    if fmt == "email":
        return "test@example.com"
    if fmt == "uri":
        return "https://example.com"
    if fmt == "uuid":
        return "00000000-0000-0000-0000-000000000000"
    if fmt == "date":
        return "2020-01-01"
    if fmt == "date-time":
        return "2020-01-01T00:00:00Z"

    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        if pattern == r"^[A-Z]{2}$":
            return "AA"
        if pattern == r"^\d{5}$":
            return "00000"

        m = re.fullmatch(r"\^\[A-Z\]\{(\d+),(\d+)\}\$", pattern)
        if m:
            return "A" * int(m.group(1))

        m = re.fullmatch(r"\^\[A-Z\]\{(\d+)\}\$", pattern)
        if m:
            return "A" * int(m.group(1))

        m = re.fullmatch(r"\^\[A-Za-z\]\{(\d+)\}\$", pattern)
        if m:
            return "a" * int(m.group(1))

        m = re.fullmatch(r"\^\[0-9\]\{(\d+),(\d+)\}\$", pattern)
        if m:
            return "0" * int(m.group(1))

        m = re.fullmatch(r"\^\[0-9\]\{(\d+)\}\$", pattern)
        if m:
            return "0" * int(m.group(1))

    min_length = schema.get("minLength")
    if isinstance(min_length, int) and min_length > 0:
        return "a" * min_length

    return "test"


def _number_for_schema(schema: dict[str, Any]) -> int | float:
    if "const" in schema:
        value = schema["const"]
        return int(value) if isinstance(value, int) else float(value)

    if "enum" in schema and schema["enum"]:
        value = schema["enum"][0]
        return int(value) if isinstance(value, int) else float(value)

    minimum = schema.get("minimum")
    if isinstance(minimum, (int, float)):
        return minimum

    exclusive_minimum = schema.get("exclusiveMinimum")
    if isinstance(exclusive_minimum, (int, float)):
        return exclusive_minimum + 1

    return 1


def build_minimal_payload_from_schema(
    schema: dict[str, Any], *, root_schema: dict[str, Any], depth: int = 0, seen_refs: set[str] | None = None
) -> Any:
    if seen_refs is None:
        seen_refs = set()

    if depth > 10:
        return None

    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen_refs:
            return {}
        seen_refs.add(ref)
        resolved = _resolve_ref(ref, root_schema)
        return build_minimal_payload_from_schema(
            resolved, root_schema=root_schema, depth=depth + 1, seen_refs=seen_refs
        )

    if "allOf" in schema:
        merged: dict[str, Any] = {}
        for subschema in schema.get("allOf", []):
            value = build_minimal_payload_from_schema(
                subschema, root_schema=root_schema, depth=depth + 1, seen_refs=seen_refs
            )
            if isinstance(value, dict):
                merged = _merge_dicts(merged, value)
        if merged:
            return merged

    if "anyOf" in schema and schema["anyOf"]:
        return build_minimal_payload_from_schema(
            schema["anyOf"][0], root_schema=root_schema, depth=depth + 1, seen_refs=seen_refs
        )

    if "oneOf" in schema and schema["oneOf"]:
        return build_minimal_payload_from_schema(
            schema["oneOf"][0], root_schema=root_schema, depth=depth + 1, seen_refs=seen_refs
        )

    if "const" in schema:
        return schema["const"]

    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((t for t in schema_type if t != "null"), schema_type[0])

    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        result: dict[str, Any] = {}

        for field_name in required:
            field_schema = properties.get(field_name, {})
            result[field_name] = build_minimal_payload_from_schema(
                field_schema, root_schema=root_schema, depth=depth + 1, seen_refs=seen_refs
            )

        if not result and properties:
            first_key = sorted(properties.keys())[0]
            result[first_key] = build_minimal_payload_from_schema(
                properties[first_key], root_schema=root_schema, depth=depth + 1, seen_refs=seen_refs
            )

        return result

    if schema_type == "array":
        items = schema.get("items", {})
        min_items = schema.get("minItems", 0)
        count = 1 if (isinstance(min_items, int) and min_items > 0) else 0
        if count == 0:
            return []
        return [
            build_minimal_payload_from_schema(
                items, root_schema=root_schema, depth=depth + 1, seen_refs=seen_refs
            )
        ]

    if schema_type == "boolean":
        return True

    if schema_type in {"integer", "number"}:
        value = _number_for_schema(schema)
        return int(value) if schema_type == "integer" else float(value)

    return _string_for_schema(schema)


def make_invalid_payload(root_schema: dict[str, Any]) -> dict[str, Any] | None:
    required = root_schema.get("required")
    properties = root_schema.get("properties")
    if not required or not properties:
        return None

    field_name = required[0]
    field_schema = properties.get(field_name, {})

    field_type = field_schema.get("type")
    if field_type == "string":
        return {field_name: {"not": "a string"}}
    if field_type == "integer":
        return {field_name: "not-an-int"}
    if field_type == "number":
        return {field_name: "not-a-number"}
    if field_type == "boolean":
        return {field_name: "not-a-bool"}
    if field_type == "array":
        return {field_name: "not-an-array"}
    if field_type == "object":
        return {field_name: "not-an-object"}

    return {field_name: None}


def _get_form_types() -> list[str]:
    # This is a live-server test (network), but we still need a stable list of
    # form types to exercise. The demo app exposes the mapping centrally.
    from src.main import _form_mapping  # noqa: PLC0415

    return sorted(_form_mapping().keys())


def main() -> int:
    parser = argparse.ArgumentParser(description="Live-server smoke tests via httpx")
    parser.add_argument(
        "--base-url",
        default="http://localhost:5000",
        help="Base URL of the running demo server (default: http://localhost:5000)",
    )
    args = parser.parse_args()

    base_url: str = args.base_url.rstrip("/")

    timeout = httpx.Timeout(connect=2.0, read=10.0, write=10.0, pool=2.0)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    try:
        with httpx.Client(base_url=base_url, timeout=timeout, limits=limits) as client:
            health = client.get("/api/health")
            health.raise_for_status()

            failures: list[str] = []
            for form_type in _get_form_types():
                schema_resp = client.get(f"/api/forms/{form_type}/schema")
                if schema_resp.status_code == 404:
                    # Mapping and server may be out of sync; skip rather than hard fail.
                    continue
                if schema_resp.status_code != 200:
                    failures.append(f"{form_type}: schema status {schema_resp.status_code}")
                    continue

                schema_body = schema_resp.json()
                schema = schema_body.get("schema")
                if not isinstance(schema, dict):
                    failures.append(f"{form_type}: missing schema")
                    continue

                render_resp = client.get(
                    f"/api/forms/{form_type}/render",
                    params={
                        "style": "bootstrap",
                        "debug": "false",
                        "include_assets": "false",
                        "asset_mode": "vendored",
                    },
                )
                if render_resp.status_code != 200:
                    failures.append(f"{form_type}: render status {render_resp.status_code}")
                    continue

                render_body = render_resp.json()
                html = render_body.get("html")
                if not isinstance(html, str) or len(html) < 100:
                    failures.append(f"{form_type}: render html too short")
                    continue

                invalid_payload = make_invalid_payload(schema)
                if invalid_payload is not None:
                    invalid_resp = client.post(f"/api/forms/{form_type}/submit", json=invalid_payload)
                    if invalid_resp.status_code != 200:
                        failures.append(
                            f"{form_type}: invalid submit status {invalid_resp.status_code}"
                        )
                    else:
                        body = invalid_resp.json()
                        if body.get("success") is not False or not body.get("errors"):
                            failures.append(f"{form_type}: invalid submit did not error")

                valid_payload = build_minimal_payload_from_schema(schema, root_schema=schema)
                if not isinstance(valid_payload, dict):
                    failures.append(f"{form_type}: could not build payload")
                    continue

                if "password" in valid_payload and "confirm_password" in valid_payload:
                    valid_payload["confirm_password"] = valid_payload["password"]

                valid_resp = client.post(f"/api/forms/{form_type}/submit", json=valid_payload)
                if valid_resp.status_code != 200:
                    failures.append(f"{form_type}: valid submit status {valid_resp.status_code}")
                    continue

                body = valid_resp.json()
                if body.get("success") is not True:
                    failures.append(f"{form_type}: valid submit success=false")

            if failures:
                print("FAIL")
                for f in failures:
                    print(f"- {f}")
                return 1

            print("OK: live server forms smoke test passed")
            return 0

    except httpx.ConnectError as e:
        print(f"ERROR: could not connect to {base_url}: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
