import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.main import _form_mapping, app


client = TestClient(app)


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
        m = re.fullmatch(r"\^\[A-Z\]\{(\d+)\}\$", pattern)
        if m:
            return "A" * int(m.group(1))

        m = re.fullmatch(r"\^\[A-Z\]\{(\d+),(\d+)\}\$", pattern)
        if m:
            return "A" * int(m.group(1))

        m = re.fullmatch(r"\^\[A-Z\]\{(\d+)\}\$", pattern)
        if m:
            return "A" * int(m.group(1))

        m = re.fullmatch(r"\^\[A-Za-z\]\{(\d+)\}\$", pattern)
        if m:
            return "a" * int(m.group(1))

        m = re.fullmatch(r"\^\[0-9\]\{(\d+)\}\$", pattern)
        if m:
            return "0" * int(m.group(1))

        m = re.fullmatch(r"\^\[0-9\]\{(\d+),(\d+)\}\$", pattern)
        if m:
            return "0" * int(m.group(1))

        if pattern == r"^[A-Z]{2}$":
            return "AA"
        if pattern == r"^\d{5}$":
            return "00000"

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
        # allOf often used for objects; fall back to object handling below if needed
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

        # If there are no required fields, we still want to produce *something* stable.
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

    # Default to string for unknown / missing types.
    return _string_for_schema(schema)


def make_invalid_payload(root_schema: dict[str, Any]) -> dict[str, Any] | None:
    required = root_schema.get("required")
    properties = root_schema.get("properties")
    if not required or not properties:
        return None

    field_name = required[0]
    field_schema = properties.get(field_name, {})

    # Pick a value that is very unlikely to coerce.
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


FORM_TYPES = sorted(_form_mapping().keys())


@pytest.mark.parametrize("form_type", FORM_TYPES)
def test_forms_schema_render_and_validation_smoke(form_type: str):
    schema_resp = client.get(f"/api/forms/{form_type}/schema")
    assert schema_resp.status_code == 200

    schema_body = schema_resp.json()
    assert schema_body["form_type"] == form_type
    assert schema_body["framework"] == "fastapi"
    assert "schema" in schema_body

    schema = schema_body["schema"]
    assert isinstance(schema, dict)

    render_resp = client.get(
        f"/api/forms/{form_type}/render",
        params={
            "style": "bootstrap",
            "debug": "false",
            "include_assets": "false",
            "asset_mode": "vendored",
        },
    )
    assert render_resp.status_code == 200
    render_body = render_resp.json()
    html = render_body["html"]
    assert isinstance(html, str)
    assert len(html) > 100

    invalid_payload = make_invalid_payload(schema)
    if invalid_payload is not None:
        invalid_resp = client.post(f"/api/forms/{form_type}/submit", json=invalid_payload)
        assert invalid_resp.status_code == 200
        invalid_body = invalid_resp.json()
        assert invalid_body["framework"] == "fastapi"
        assert invalid_body["success"] is False
        assert invalid_body["errors"]

    valid_payload = build_minimal_payload_from_schema(schema, root_schema=schema)
    assert isinstance(valid_payload, dict)

    # Some demo forms include cross-field validation that JSON Schema cannot express.
    # Ensure the generated payload satisfies the common "confirm password" constraint.
    if "password" in valid_payload and "confirm_password" in valid_payload:
        valid_payload["confirm_password"] = valid_payload["password"]

    valid_resp = client.post(f"/api/forms/{form_type}/submit", json=valid_payload)
    assert valid_resp.status_code == 200
    valid_body = valid_resp.json()
    assert valid_body["framework"] == "fastapi"
    assert valid_body["success"] is True
    assert valid_body["data"] is not None
