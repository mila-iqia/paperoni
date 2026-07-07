"""Bridge serieux-generated JSON schemas into the FastAPI/OpenAPI docs.

FastAPI/pydantic infers schemas from type hints but does not pick up the
inline ``# comment`` field docs that serieux uses. For endpoints where the
serieux schema is richer (parameter descriptions, formats, etc.), register the
serieux type here and it will replace the auto-generated schema for that
operation:

- ``use_query_schema`` for GET-style query parameters.
- ``use_body_schema`` for POST/PUT/DELETE JSON request bodies.

``apply_serieux_schemas`` is called from the app's custom ``openapi()`` and
rewrites every registered operation.
"""

import warnings

from fastapi.encoders import jsonable_encoder
from serieux import schema

# (path, http_method) -> serieux type whose compiled schema documents the
# operation's query parameters.
_QUERY_PARAM_SCHEMAS: dict[tuple[str, str], type] = {}

# (path, http_method) -> serieux type whose compiled schema documents the
# operation's JSON request body.
_BODY_SCHEMAS: dict[tuple[str, str], type] = {}


def use_query_schema(path: str, method: str, typ: type) -> None:
    """Register a serieux type as the query-parameter docs for an operation."""
    _QUERY_PARAM_SCHEMAS[(path, method.lower())] = typ


def use_body_schema(path: str, method: str, typ: type) -> None:
    """Register a serieux type as the JSON request-body docs for an operation."""
    _BODY_SCHEMAS[(path, method.lower())] = typ


def _compiled(typ: type) -> dict:
    """Compile a serieux schema with everything inlined, minus JSON-Schema meta keys."""
    # ref_policy="never" inlines all $ref so the schema is self-contained; OpenAPI
    # tooling does not resolve serieux's internal (non-#/components) refs.
    compiled = schema(typ).compile(ref_policy="never")
    compiled.pop("$schema", None)
    # serieux embeds raw Python default values (timedelta, date, ...); make them
    # JSON-native so the OpenAPI document stays serializable.
    return jsonable_encoder(compiled)


def _to_query_parameters(typ: type) -> list[dict]:
    """Turn a serieux object schema into a list of OpenAPI query parameters."""
    compiled = _compiled(typ)
    required = set(compiled.get("required", []))

    parameters = []
    for name, prop in compiled.get("properties", {}).items():
        prop = dict(prop)
        # In OpenAPI, a parameter's description lives on the parameter, not its schema.
        description = prop.pop("description", None)
        parameter = {
            "name": name,
            "in": "query",
            "required": name in required,
            "schema": prop,
        }
        if description:
            parameter["description"] = description
        parameters.append(parameter)
    return parameters


def apply_serieux_schemas(openapi_schema: dict) -> None:
    """Rewrite registered operations' params/bodies with serieux-derived schemas.

    A type serieux cannot compile (e.g. a bare ``dict`` field) is skipped with a
    warning, leaving FastAPI's inferred schema in place rather than breaking the
    whole document.
    """
    paths = openapi_schema.get("paths", {})

    for (path, method), typ in _QUERY_PARAM_SCHEMAS.items():
        operation = paths.get(path, {}).get(method)
        if operation is None:
            continue
        try:
            parameters = _to_query_parameters(typ)
        except Exception as exc:  # noqa: BLE001 — never let docs generation fail
            warnings.warn(
                f"serieux query schema for {method.upper()} {path} failed: {exc}"
            )
            continue
        # Keep any path/header/cookie params FastAPI generated; swap out query ones.
        kept = [p for p in operation.get("parameters", []) if p.get("in") != "query"]
        operation["parameters"] = kept + parameters

    for (path, method), typ in _BODY_SCHEMAS.items():
        operation = paths.get(path, {}).get(method)
        if operation is None:
            continue
        try:
            body_schema = _compiled(typ)
        except Exception as exc:  # noqa: BLE001 — never let docs generation fail
            warnings.warn(
                f"serieux body schema for {method.upper()} {path} failed: {exc}"
            )
            continue
        # Preserve FastAPI's requestBody envelope (required flag, other media types)
        # and only replace the application/json schema.
        request_body = operation.setdefault("requestBody", {})
        content = request_body.setdefault("content", {})
        json_content = content.setdefault("application/json", {})
        json_content["schema"] = body_schema
