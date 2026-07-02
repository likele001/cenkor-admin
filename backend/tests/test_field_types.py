"""字段类型校验单元测试"""
import pytest

from cenkor_admin.apps.cms.field_types import (
    FIELD_TYPES,
    FIELD_DEFAULTS,
    VALIDATION_RULES,
    NEEDS_OPTIONS,
    SINGLE_VALUE_TYPES,
    ARRAY_VALUE_TYPES,
    validate_field_value,
)


class TestFieldTypes:
    """字段类型枚举完整性"""

    def test_field_types_count(self):
        """共 21 种字段类型"""
        assert len(FIELD_TYPES) == 21

    def test_field_types_required(self):
        """必须的字段类型都在"""
        required = {"text", "longtext", "richtext", "markdown", "number", "boolean",
                    "date", "datetime", "url", "email", "phone", "image", "images",
                    "file", "files", "select", "multiselect", "color", "json",
                    "repeater", "relation"}
        assert set(FIELD_TYPES) == required

    def test_field_types_partition(self):
        """字段类型正确分类为单值 / 多值"""
        assert "text" in SINGLE_VALUE_TYPES
        assert "boolean" in SINGLE_VALUE_TYPES
        assert "select" in SINGLE_VALUE_TYPES
        assert "images" in ARRAY_VALUE_TYPES
        assert "files" in ARRAY_VALUE_TYPES
        assert "multiselect" in ARRAY_VALUE_TYPES
        assert "repeater" in ARRAY_VALUE_TYPES
        # 不重叠
        assert SINGLE_VALUE_TYPES & ARRAY_VALUE_TYPES == set()

    def test_needs_options(self):
        """只有 select/multiselect 需要选项"""
        assert NEEDS_OPTIONS == {"select", "multiselect"}


class TestFieldDefaults:
    """字段默认值"""

    def test_text_default(self):
        assert FIELD_DEFAULTS["text"] == ""

    def test_number_default(self):
        assert FIELD_DEFAULTS["number"] == 0

    def test_boolean_default(self):
        assert FIELD_DEFAULTS["boolean"] is False

    def test_array_defaults_are_empty_list(self):
        for ft in ("images", "files", "multiselect", "repeater"):
            assert FIELD_DEFAULTS[ft] == []

    def test_date_defaults_none(self):
        assert FIELD_DEFAULTS["date"] is None
        assert FIELD_DEFAULTS["datetime"] is None

    def test_color_default(self):
        assert FIELD_DEFAULTS["color"] == "#000000"


class TestValidationRules:
    """校验规则映射"""

    def test_text_has_max_length(self):
        assert "max_length" in VALIDATION_RULES["text"]
        assert VALIDATION_RULES["text"]["max_length"]["type"] == "int"

    def test_number_has_min_max_step(self):
        rules = VALIDATION_RULES["number"]
        assert "min" in rules
        assert "max" in rules
        assert "step" in rules

    def test_phone_has_pattern(self):
        assert "pattern" in VALIDATION_RULES["phone"]
        assert VALIDATION_RULES["phone"]["pattern"]["default"].startswith("^1")

    def test_repeater_has_min_max_rows(self):
        rules = VALIDATION_RULES["repeater"]
        assert "min_rows" in rules
        assert "max_rows" in rules

    def test_relation_requires_target(self):
        rules = VALIDATION_RULES["relation"]
        assert rules["target_content_type"]["required"] is True


class TestValidateFieldValue:
    """字段值校验函数"""

    def test_unknown_field_type(self):
        errors = validate_field_value("nonexistent_type", "value")
        assert any("Unknown field type" in e for e in errors)

    def test_none_value_skips_validation(self):
        for ft in FIELD_TYPES:
            assert validate_field_value(ft, None) == []

    def test_number_valid(self):
        assert validate_field_value("number", 42) == []
        assert validate_field_value("number", 3.14) == []

    def test_number_with_min_max(self):
        # 低于 min
        errors = validate_field_value("number", -1, {"min": 0})
        assert any("minimum" in e for e in errors)
        # 高于 max
        errors = validate_field_value("number", 200, {"max": 100})
        assert any("maximum" in e for e in errors)
        # 在范围内
        assert validate_field_value("number", 50, {"min": 0, "max": 100}) == []

    def test_number_wrong_type(self):
        errors = validate_field_value("number", "not a number")
        assert any("numeric" in e for e in errors)

    def test_text_with_max_length(self):
        # 超出 max_length
        errors = validate_field_value("text", "x" * 100, {"max_length": 10})
        assert any("max length" in e for e in errors)
        # 在范围内
        assert validate_field_value("text", "x" * 5, {"max_length": 10}) == []

    def test_text_wrong_type(self):
        errors = validate_field_value("text", 123)
        assert any("string" in e for e in errors)

    def test_boolean_wrong_type(self):
        errors = validate_field_value("boolean", "true")
        assert any("bool" in e for e in errors)
        # 合法
        assert validate_field_value("boolean", True) == []
        assert validate_field_value("boolean", False) == []

    def test_color_valid(self):
        # 合法 6 位 hex
        assert validate_field_value("color", "#3b82f6") == []
        assert validate_field_value("color", "#FFFFFF") == []
        # 非法
        errors = validate_field_value("color", "red")
        assert len(errors) > 0
        errors = validate_field_value("color", "#xxxxxx")
        assert len(errors) > 0
        errors = validate_field_value("color", "#FFF")  # 3 位不算（仅 6 位）
        assert len(errors) > 0

    def test_array_must_be_list(self):
        for ft in ("images", "files", "multiselect", "repeater"):
            errors = validate_field_value(ft, "not a list")
            assert any("list" in e for e in errors), f"{ft} 错误信息: {errors}"
            # 合法空数组
            assert validate_field_value(ft, []) == []


class TestFieldTypeSchemas:
    """Pydantic schemas 校验"""

    def test_content_type_key_pattern(self):
        from cenkor_admin.apps.cms.schemas import ContentTypeCreate
        from pydantic import ValidationError

        # 合法 key
        ct = ContentTypeCreate(key="my_type", name="My Type")
        assert ct.key == "my_type"

        # 非法：以数字开头
        with pytest.raises(ValidationError):
            ContentTypeCreate(key="123abc", name="Bad")

        # 非法：含大写
        with pytest.raises(ValidationError):
            ContentTypeCreate(key="MyType", name="Bad")

        # 非法：含连字符
        with pytest.raises(ValidationError):
            ContentTypeCreate(key="my-type", name="Bad")

    def test_field_definition_validates_field_type(self):
        from cenkor_admin.apps.cms.schemas import FieldDefinitionCreate
        from pydantic import ValidationError

        # 合法
        fd = FieldDefinitionCreate(
            field_key="price", label="Price", field_type="number"
        )
        assert fd.field_type == "number"

        # 非法 field_type
        with pytest.raises(ValidationError):
            FieldDefinitionCreate(
                field_key="bad", label="Bad", field_type="nonexistent"
            )

    def test_field_definition_invalid_field_type_via_update(self):
        from cenkor_admin.apps.cms.schemas import FieldDefinitionUpdate
        from pydantic import ValidationError

        # 合法
        fd = FieldDefinitionUpdate(field_type="text")
        assert fd.field_type == "text"

        # 非法
        with pytest.raises(ValidationError):
            FieldDefinitionUpdate(field_type="invalid_type_xyz")
