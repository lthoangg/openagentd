"""Tests for the capabilities system.

Tests cover:
1. YAML loading and caching
2. Input/Output dataclass behavior
3. Composite access patterns
4. Integration with get_capabilities()
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from app.agent.providers.capabilities import (
    ModelCapabilities,
    ModelInputCapabilities,
    ModelOutputCapabilities,
    get_capabilities,
    reload_capabilities,
)


# ─────────────────────────────────────────────────────────────────────────────
# ModelInputCapabilities Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestModelInputCapabilities:
    """Test ModelInputCapabilities dataclass."""

    def test_defaults(self):
        """ModelInputCapabilities has correct defaults."""
        caps = ModelInputCapabilities()
        assert caps.vision is False
        assert caps.document_text is True
        assert caps.audio is False
        assert caps.video is False

    def test_custom_values(self):
        """ModelInputCapabilities can be initialized with custom values."""
        caps = ModelInputCapabilities(
            vision=True,
            document_text=False,
            audio=True,
            video=True,
        )
        assert caps.vision is True
        assert caps.document_text is False
        assert caps.audio is True
        assert caps.video is True

    def test_partial_override(self):
        """ModelInputCapabilities can override specific fields."""
        caps = ModelInputCapabilities(vision=True)
        assert caps.vision is True
        assert caps.document_text is True  # default
        assert caps.audio is False  # default
        assert caps.video is False  # default

    def test_to_dict(self):
        """ModelInputCapabilities.to_dict() returns correct shape."""
        caps = ModelInputCapabilities(vision=True, document_text=False)
        d = caps.to_dict()
        assert d == {
            "vision": True,
            "document_text": False,
            "audio": False,
            "video": False,
        }

    def test_frozen_dataclass(self):
        """ModelInputCapabilities is frozen — cannot mutate fields."""
        caps = ModelInputCapabilities()
        with pytest.raises(AttributeError):
            caps.vision = True  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# ModelOutputCapabilities Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestModelOutputCapabilities:
    """Test ModelOutputCapabilities dataclass."""

    def test_defaults(self):
        """ModelOutputCapabilities has correct defaults."""
        caps = ModelOutputCapabilities()
        assert caps.text is True
        assert caps.image is False
        assert caps.audio is False

    def test_custom_values(self):
        """ModelOutputCapabilities can be initialized with custom values."""
        caps = ModelOutputCapabilities(
            text=False,
            image=True,
            audio=True,
        )
        assert caps.text is False
        assert caps.image is True
        assert caps.audio is True

    def test_partial_override(self):
        """ModelOutputCapabilities can override specific fields."""
        caps = ModelOutputCapabilities(image=True)
        assert caps.text is True  # default
        assert caps.image is True
        assert caps.audio is False  # default

    def test_to_dict(self):
        """ModelOutputCapabilities.to_dict() returns correct shape."""
        caps = ModelOutputCapabilities(text=False, image=True)
        d = caps.to_dict()
        assert d == {
            "text": False,
            "image": True,
            "audio": False,
        }

    def test_frozen_dataclass(self):
        """ModelOutputCapabilities is frozen — cannot mutate fields."""
        caps = ModelOutputCapabilities()
        with pytest.raises(AttributeError):
            caps.text = False  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# ModelCapabilities Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestModelCapabilities:
    """Test ModelCapabilities composite dataclass."""

    def test_defaults(self):
        """ModelCapabilities has correct default input and output."""
        caps = ModelCapabilities()
        assert isinstance(caps.input, ModelInputCapabilities)
        assert isinstance(caps.output, ModelOutputCapabilities)
        assert caps.input.vision is False
        assert caps.input.document_text is True
        assert caps.output.text is True
        assert caps.output.image is False

    def test_custom_input_output(self):
        """ModelCapabilities can be initialized with custom input/output."""
        input_caps = ModelInputCapabilities(vision=True)
        output_caps = ModelOutputCapabilities(image=True)
        caps = ModelCapabilities(input=input_caps, output=output_caps)
        assert caps.input.vision is True
        assert caps.output.image is True

    def test_to_dict(self):
        """ModelCapabilities.to_dict() returns nested structure."""
        caps = ModelCapabilities(
            input=ModelInputCapabilities(vision=True),
            output=ModelOutputCapabilities(image=True),
        )
        d = caps.to_dict()
        assert d == {
            "input": {
                "vision": True,
                "document_text": True,
                "audio": False,
                "video": False,
            },
            "output": {
                "text": True,
                "image": True,
                "audio": False,
            },
        }

    def test_frozen_dataclass(self):
        """ModelCapabilities is frozen — cannot mutate fields."""
        caps = ModelCapabilities()
        with pytest.raises(AttributeError):
            caps.input = ModelInputCapabilities(vision=True)  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# YAML Loading Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestYamlLoading:
    """Test YAML loading and caching."""

    def teardown_method(self):
        """Clear cache after each test."""
        reload_capabilities()

    def test_yaml_loads_successfully(self):
        """YAML loads successfully and returns correct capabilities."""
        caps = get_capabilities("zai:glm-5v-turbo")
        assert caps.input.vision is True

    def test_yaml_sparse_merge_inherits_defaults(self):
        """YAML sparse merge: entry with only input.vision inherits document_text."""
        # zai:glm-5v-turbo has only vision: true in YAML
        caps = get_capabilities("zai:glm-5v-turbo")
        assert caps.input.vision is True
        assert caps.input.document_text is True  # inherited default
        assert caps.input.audio is False  # inherited default
        assert caps.input.video is False  # inherited default

    def test_yaml_sparse_merge_output_inherits_defaults(self):
        """YAML sparse merge: entry with only input inherits output defaults."""
        caps = get_capabilities("openai:gpt-4.1")
        assert caps.input.vision is True
        assert caps.output.text is True  # inherited default
        assert caps.output.image is False  # inherited default
        assert caps.output.audio is False  # inherited default

    def test_reload_capabilities_clears_cache(self):
        """reload_capabilities() clears cache — next call reloads YAML."""
        # First call caches the result
        caps1 = get_capabilities("zai:glm-5v-turbo")
        assert caps1.input.vision is True

        # Clear cache
        reload_capabilities()

        # Next call should reload (we can't easily verify reload without mocking,
        # but we can verify the function doesn't error)
        caps2 = get_capabilities("zai:glm-5v-turbo")
        assert caps2.input.vision is True

    def test_missing_yaml_file_falls_through_to_prefix(self):
        """Missing YAML file gracefully falls through to prefix/default."""
        with patch(
            "app.agent.providers.capabilities._YAML_PATH",
            Path("/nonexistent/path/capabilities.yaml"),
        ):
            reload_capabilities()
            # Should fall through to prefix fallback
            caps = get_capabilities("googlegenai:some-model")
            assert caps.input.vision is True  # from prefix fallback

    def test_missing_yaml_file_falls_through_to_default(self):
        """Missing YAML file falls through to default for unknown provider."""
        with patch(
            "app.agent.providers.capabilities._YAML_PATH",
            Path("/nonexistent/path/capabilities.yaml"),
        ):
            reload_capabilities()
            caps = get_capabilities("unknown:model")
            assert caps.input.vision is False  # from default

    def test_malformed_yaml_non_dict_falls_through(self):
        """Malformed YAML (non-dict top level) falls through gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("- item1\n- item2\n")  # list, not dict
            f.flush()
            yaml_path = Path(f.name)

        try:
            with patch("app.agent.providers.capabilities._YAML_PATH", yaml_path):
                reload_capabilities()
                # Should fall through to prefix fallback
                caps = get_capabilities("googlegenai:some-model")
                assert caps.input.vision is True  # from prefix fallback
        finally:
            yaml_path.unlink()

    def test_malformed_yaml_invalid_syntax_falls_through(self):
        """Malformed YAML (invalid syntax) falls through gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: syntax: here:")
            f.flush()
            yaml_path = Path(f.name)

        try:
            with patch("app.agent.providers.capabilities._YAML_PATH", yaml_path):
                reload_capabilities()
                # Should fall through to prefix fallback
                caps = get_capabilities("googlegenai:some-model")
                assert caps.input.vision is True  # from prefix fallback
        finally:
            yaml_path.unlink()

    def test_yaml_case_insensitive_lookup(self):
        """YAML entries are case-insensitive."""
        caps_lower = get_capabilities("zai:glm-5v-turbo")
        reload_capabilities()
        caps_upper = get_capabilities("ZAI:GLM-5V-TURBO")
        assert caps_lower == caps_upper
        assert caps_lower.input.vision is True


# ─────────────────────────────────────────────────────────────────────────────
# get_capabilities Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetCapabilitiesIntegration:
    """Test get_capabilities() lookup order and behavior."""

    def teardown_method(self):
        """Clear cache after each test."""
        reload_capabilities()

    def test_none_returns_default(self):
        """None model_id returns default capabilities."""
        caps = get_capabilities(None)
        assert caps.input.vision is False
        assert caps.input.document_text is True
        assert caps.output.text is True

    def test_exact_match_from_yaml(self):
        """Model in YAML returns YAML capabilities (not prefix fallback)."""
        # zai:glm-5v-turbo is in YAML with vision: true
        caps = get_capabilities("zai:glm-5v-turbo")
        assert caps.input.vision is True

    def test_exact_match_overrides_prefix(self):
        """Exact YAML match takes precedence over prefix fallback."""
        # zai:glm-5v-turbo is in YAML with vision: true
        # zai: prefix would give vision: false
        caps = get_capabilities("zai:glm-5v-turbo")
        assert caps.input.vision is True  # from YAML, not prefix

    def test_prefix_fallback_when_no_exact_match(self):
        """Model NOT in YAML but matching prefix returns prefix fallback."""
        # googlegenai:unknown-future-model is not in YAML
        # but googlegenai: prefix gives vision: true
        caps = get_capabilities("googlegenai:unknown-future-model")
        assert caps.input.vision is True

    def test_default_when_no_match(self):
        """Model NOT in YAML and no prefix match returns default."""
        caps = get_capabilities("unknown_provider:some-model")
        assert caps.input.vision is False
        assert caps.input.document_text is True

    def test_longest_prefix_match(self):
        """Longest prefix match is used (not first match)."""
        # Both "openai:" and "openai:" would match "openai:gpt-5"
        # but we want the longest match (which is the same in this case)
        caps = get_capabilities("openai:gpt-5")
        assert caps.input.vision is True

    def test_case_insensitive_exact_match(self):
        """Exact match lookup is case-insensitive."""
        caps_lower = get_capabilities("zai:glm-5v-turbo")
        reload_capabilities()
        caps_upper = get_capabilities("ZAI:GLM-5V-TURBO")
        assert caps_lower == caps_upper

    def test_case_insensitive_prefix_match(self):
        """Prefix match lookup is case-insensitive."""
        caps_lower = get_capabilities("googlegenai:some-model")
        reload_capabilities()
        caps_upper = get_capabilities("GOOGLEGENAI:SOME-MODEL")
        assert caps_lower == caps_upper

    def test_all_prefix_fallbacks_work(self):
        """All defined prefix fallbacks return expected capabilities."""
        # googlegenai: → vision=True
        assert get_capabilities("googlegenai:test").input.vision is True

        # vertexai: → vision=True
        assert get_capabilities("vertexai:test").input.vision is True

        # geminicli: → vision=True
        assert get_capabilities("geminicli:test").input.vision is True

        # openai: → vision=True
        assert get_capabilities("openai:test").input.vision is True

        # copilot: → vision=False
        assert get_capabilities("copilot:test").input.vision is False

        # zai: → vision=False
        assert get_capabilities("zai:test").input.vision is False

        # openrouter: → vision=False
        assert get_capabilities("openrouter:test").input.vision is False

        # nvidia: → vision=False
        assert get_capabilities("nvidia:test").input.vision is False

        # xai: → vision=True (multimodal Grok models)
        assert get_capabilities("xai:test").input.vision is True

    def test_document_text_default_for_all_prefixes(self):
        """All prefix fallbacks inherit document_text=True default."""
        for prefix in [
            "googlegenai:",
            "vertexai:",
            "geminicli:",
            "openai:",
            "copilot:",
            "zai:",
            "openrouter:",
            "nvidia:",
            "xai:",
        ]:
            caps = get_capabilities(f"{prefix}test-model")
            assert caps.input.document_text is True

    def test_output_defaults_for_all_prefixes(self):
        """All prefix fallbacks inherit output defaults."""
        for prefix in [
            "googlegenai:",
            "vertexai:",
            "geminicli:",
            "openai:",
            "copilot:",
            "zai:",
            "openrouter:",
            "nvidia:",
            "xai:",
        ]:
            caps = get_capabilities(f"{prefix}test-model")
            assert caps.output.text is True
            assert caps.output.image is False
            assert caps.output.audio is False


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases and Boundary Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def teardown_method(self):
        """Clear cache after each test."""
        reload_capabilities()

    def test_empty_string_model_id(self):
        """Empty string model_id returns default."""
        caps = get_capabilities("")
        assert caps.input.vision is False

    def test_whitespace_only_model_id(self):
        """Whitespace-only model_id returns default."""
        caps = get_capabilities("   ")
        assert caps.input.vision is False

    def test_model_id_with_no_colon(self):
        """Model ID without colon returns default (no prefix match)."""
        caps = get_capabilities("just-a-model-name")
        assert caps.input.vision is False

    def test_model_id_with_multiple_colons(self):
        """Model ID with multiple colons uses longest prefix match."""
        # "openai:gpt:5" should match "openai:" prefix
        caps = get_capabilities("openai:gpt:5")
        assert caps.input.vision is True

    def test_yaml_entry_with_empty_input_dict(self):
        """YAML entry with empty input dict inherits all defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"test:model": {"input": {}}}, f)
            f.flush()
            yaml_path = Path(f.name)

        try:
            with patch("app.agent.providers.capabilities._YAML_PATH", yaml_path):
                reload_capabilities()
                caps = get_capabilities("test:model")
                assert caps.input.vision is False  # default
                assert caps.input.document_text is True  # default
        finally:
            yaml_path.unlink()

    def test_yaml_entry_with_empty_output_dict(self):
        """YAML entry with empty output dict inherits all defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"test:model": {"output": {}}}, f)
            f.flush()
            yaml_path = Path(f.name)

        try:
            with patch("app.agent.providers.capabilities._YAML_PATH", yaml_path):
                reload_capabilities()
                caps = get_capabilities("test:model")
                assert caps.output.text is True  # default
                assert caps.output.image is False  # default
        finally:
            yaml_path.unlink()

    def test_yaml_entry_with_output_override(self):
        """YAML entry with output override is applied correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"test:model": {"output": {"image": True}}}, f)
            f.flush()
            yaml_path = Path(f.name)

        try:
            with patch("app.agent.providers.capabilities._YAML_PATH", yaml_path):
                reload_capabilities()
                caps = get_capabilities("test:model")
                assert caps.output.text is True  # default
                assert caps.output.image is True  # overridden
                assert caps.output.audio is False  # default
        finally:
            yaml_path.unlink()

    def test_yaml_entry_with_null_values(self):
        """YAML entry with null values preserves None (not ideal, but current behavior)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"test:model": {"input": {"vision": None}}}, f)
            f.flush()
            yaml_path = Path(f.name)

        try:
            with patch("app.agent.providers.capabilities._YAML_PATH", yaml_path):
                reload_capabilities()
                caps = get_capabilities("test:model")
                # Note: .get("vision", default) returns None if key exists with None value
                # This is a potential edge case in the implementation
                assert caps.input.vision is None
        finally:
            yaml_path.unlink()

    def test_yaml_entry_with_non_dict_value(self):
        """YAML entry with non-dict value is skipped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "test:model": "not a dict",
                    "valid:model": {"input": {"vision": True}},
                },
                f,
            )
            f.flush()
            yaml_path = Path(f.name)

        try:
            with patch("app.agent.providers.capabilities._YAML_PATH", yaml_path):
                reload_capabilities()
                # Invalid entry is skipped, valid entry is loaded
                caps = get_capabilities("valid:model")
                assert caps.input.vision is True
        finally:
            yaml_path.unlink()


# ─────────────────────────────────────────────────────────────────────────────
# Composite Access Pattern Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCompositeAccessPatterns:
    """Test accessing capabilities through composite structure."""

    def teardown_method(self):
        """Clear cache after each test."""
        reload_capabilities()

    def test_input_vision_access(self):
        """caps.input.vision works for exact match models."""
        caps = get_capabilities("zai:glm-5v-turbo")
        assert caps.input.vision is True

    def test_input_document_text_access(self):
        """caps.input.document_text works and defaults to True."""
        caps = get_capabilities("zai:glm-5v-turbo")
        assert caps.input.document_text is True

    def test_output_text_access(self):
        """caps.output.text works and defaults to True."""
        caps = get_capabilities("zai:glm-5v-turbo")
        assert caps.output.text is True

    def test_output_image_access(self):
        """caps.output.image works and defaults to False."""
        caps = get_capabilities("zai:glm-5v-turbo")
        assert caps.output.image is False

    def test_all_input_fields_accessible(self):
        """All input fields are accessible."""
        caps = get_capabilities("googlegenai:test")
        _ = caps.input.vision
        _ = caps.input.document_text
        _ = caps.input.audio
        _ = caps.input.video
        # If we get here without AttributeError, all fields are accessible

    def test_all_output_fields_accessible(self):
        """All output fields are accessible."""
        caps = get_capabilities("googlegenai:test")
        _ = caps.output.text
        _ = caps.output.image
        _ = caps.output.audio
        # If we get here without AttributeError, all fields are accessible
