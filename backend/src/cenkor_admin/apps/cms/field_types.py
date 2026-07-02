"""CMS 字段类型枚举 + 校验规则映射"""
from __future__ import annotations

from typing import Any

FIELD_TYPES: list[str] = [
    "text",
    "longtext",
    "richtext",
    "markdown",
    "number",
    "boolean",
    "date",
    "datetime",
    "url",
    "email",
    "phone",
    "image",
    "images",
    "file",
    "files",
    "select",
    "multiselect",
    "color",
    "json",
    "repeater",
    "relation",
]

SINGLE_VALUE_TYPES: set[str] = {
    "text", "longtext", "richtext", "markdown", "number", "boolean",
    "date", "datetime", "url", "email", "phone", "image", "file",
    "select", "color", "json", "relation",
}

ARRAY_VALUE_TYPES: set[str] = {
    "images", "files", "multiselect", "repeater",
}

FIELD_DEFAULTS: dict[str, Any] = {
    "text": "",
    "longtext": "",
    "richtext": "",
    "markdown": "",
    "number": 0,
    "boolean": False,
    "date": None,
    "datetime": None,
    "url": "",
    "email": "",
    "phone": "",
    "image": "",
    "images": [],
    "file": "",
    "files": [],
    "select": "",
    "multiselect": [],
    "color": "#000000",
    "json": None,
    "repeater": [],
    "relation": None,
}

VALIDATION_RULES: dict[str, dict[str, Any]] = {
    "text": {"max_length": {"type": "int", "min": 1, "max": 1000, "default": 200}},
    "longtext": {"max_length": {"type": "int", "min": 1, "max": 100000, "default": 10000}},
    "richtext": {"max_length": {"type": "int", "min": 1, "max": 1000000, "default": 100000}},
    "markdown": {"max_length": {"type": "int", "min": 1, "max": 1000000, "default": 100000}},
    "number": {
        "min": {"type": "number", "default": None},
        "max": {"type": "number", "default": None},
        "step": {"type": "number", "default": 1},
    },
    "boolean": {},
    "date": {"format": {"type": "str", "default": "YYYY-MM-DD"}},
    "datetime": {"format": {"type": "str", "default": "YYYY-MM-DDTHH:mm:ssZ"}},
    "url": {"max_length": {"type": "int", "default": 500}},
    "email": {"max_length": {"type": "int", "default": 120}},
    "phone": {"pattern": {"type": "str", "default": r"^1[3-9]\d{9}$"}},
    "image": {},
    "images": {"max_count": {"type": "int", "min": 1, "max": 50, "default": 10}},
    "file": {},
    "files": {"max_count": {"type": "int", "min": 1, "max": 50, "default": 10}},
    "select": {},
    "multiselect": {},
    "color": {"pattern": {"type": "str", "default": r"^#[0-9a-fA-F]{6}$"}},
    "json": {},
    "repeater": {
        "min_rows": {"type": "int", "min": 0, "max": 100, "default": 0},
        "max_rows": {"type": "int", "min": 1, "max": 100, "default": 20},
    },
    "relation": {
        "target_content_type": {"type": "str", "required": True},
        "multiple": {"type": "bool", "default": False},
    },
}

NEEDS_OPTIONS: set[str] = {"select", "multiselect"}


def validate_field_value(field_type: str, value: Any, validation: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if field_type not in FIELD_TYPES:
        errors.append(f"Unknown field type: {field_type}")
        return errors

    if value is None:
        return errors

    rules = validation or {}

    if field_type == "number":
        if not isinstance(value, (int, float)):
            errors.append(f"Field type 'number' expects numeric value, got {type(value).__name__}")
        else:
            if "min" in rules and rules["min"] is not None and value < rules["min"]:
                errors.append(f"Value {value} is less than minimum {rules['min']}")
            if "max" in rules and rules["max"] is not None and value > rules["max"]:
                errors.append(f"Value {value} exceeds maximum {rules['max']}")

    elif field_type in ("text", "longtext", "richtext", "markdown", "url", "email", "phone"):
        if not isinstance(value, str):
            errors.append(f"Field type '{field_type}' expects string value, got {type(value).__name__}")
        elif "max_length" in rules and len(value) > rules["max_length"]:
            errors.append(f"Value exceeds max length {rules['max_length']}")

    elif field_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"Field type 'boolean' expects bool value, got {type(value).__name__}")

    elif field_type in ("images", "files", "multiselect"):
        if not isinstance(value, list):
            errors.append(f"Field type '{field_type}' expects list value, got {type(value).__name__}")

    elif field_type == "color":
        import re
        if not isinstance(value, str) or not re.match(r"^#[0-9a-fA-F]{6}$", value):
            errors.append(f"Invalid color format: {value}")

    elif field_type == "repeater":
        if not isinstance(value, list):
            errors.append(f"Field type 'repeater' expects list value, got {type(value).__name__}")

    return errors
