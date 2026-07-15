"""UI-neutral workflow capability manifests."""

import re
from dataclasses import asdict
from typing import Any

from .processors import ProcessorRegistry

OPTION_UI: dict[str, dict[str, Any]] = {
    "extensions": {"title_key": "workflow.junk.extensions", "description_key": "workflow.junk.extensions_help", "control": "tags", "placeholder_key": "workflow.junk.extensions_placeholder", "examples": [".url", ".tmp"]},
    "filename_contains": {"title_key": "workflow.junk.keywords", "description_key": "workflow.junk.keywords_help", "control": "tags", "placeholder_key": "workflow.junk.keywords_placeholder", "examples": ["广告", "推广"]},
    "protected_extensions": {"title_key": "workflow.junk.protected", "description_key": "workflow.junk.protected_help", "control": "tags", "placeholder_key": "workflow.junk.protected_placeholder", "examples": [".srt", ".nfo"]},
    "require_hash_evidence": {"title_key": "workflow.junk.require_hash", "description_key": "workflow.junk.require_hash_help", "control": "toggle"},
    "require_small_text": {"title_key": "workflow.junk.inspect_text", "description_key": "workflow.junk.inspect_text_help", "control": "toggle"},
    "method": {"title_key": "workflow.duplicate.method", "description_key": "workflow.duplicate.method_help", "control": "segmented"},
    "minimum_count": {"title_key": "workflow.duplicate.minimum", "description_key": "workflow.duplicate.minimum_help", "control": "number", "minimum": 2, "maximum": 1000},
    "pattern": {"title_key": "workflow.regex.pattern", "description_key": "workflow.regex.pattern_help", "control": "regex", "placeholder_key": "workflow.regex.pattern_placeholder"},
    "field": {"title_key": "workflow.regex.field", "description_key": "workflow.regex.field_help", "control": "text"},
    "prefixes": {"title_key": "workflow.source_prefix.values", "description_key": "workflow.source_prefix.values_help", "control": "tags"},
    "markers": {"title_key": "workflow.language.markers", "description_key": "workflow.language.markers_help", "control": "key_value_tags"},
    "categories": {"title_key": "workflow.category.map", "description_key": "workflow.category.map_help", "control": "key_value_tags"},
    "remove_prefixes": {"title_key": "workflow.cleanup.prefixes", "description_key": "workflow.cleanup.prefixes_help", "control": "tags"},
    "replacements": {"title_key": "workflow.cleanup.replacements", "description_key": "workflow.cleanup.replacements_help", "control": "replacements"},
    "invalid_replacement": {"title_key": "workflow.cleanup.invalid_replacement", "description_key": "workflow.cleanup.invalid_replacement_help", "control": "text"},
    "name_template": {"title_key": "workflow.naming.template", "description_key": "workflow.naming.template_help", "control": "template"},
    "parent_template": {"title_key": "workflow.target.parent_template", "description_key": "workflow.target.parent_template_help", "control": "template"},
}


ACTION_CAPABILITIES: list[dict[str, Any]] = [
    {"kind": "run_processor", "stage": "extract", "title_key": "action.run_processor", "description_key": "action.run_processor.help", "risk": "normal", "option_schema": {"processor_id": {"type": "string", "title_key": "workflow.processor", "control": "processor"}}},
    {"kind": "extract_dates", "stage": "extract", "title_key": "action.extract_dates", "description_key": "action.extract_dates.help", "risk": "safe", "option_schema": {}},
    {"kind": "clean_name", "stage": "clean", "title_key": "action.clean_name", "description_key": "action.clean_name.help", "risk": "normal", "option_schema": {
        "remove_words": {"type": "array", "title_key": "workflow.cleanup.words", "description_key": "workflow.cleanup.words_help", "control": "tags", "examples": ["广告", "推广"]},
        "remove_prefixes": {"type": "array", "title_key": "workflow.cleanup.prefixes", "description_key": "workflow.cleanup.prefixes_help", "control": "tags"},
        "remove_suffixes": {"type": "array", "title_key": "workflow.cleanup.suffixes", "description_key": "workflow.cleanup.suffixes_help", "control": "tags"},
        "replacements": {"type": "array", "title_key": "workflow.cleanup.replacements", "description_key": "workflow.cleanup.replacements_help", "control": "replacements"},
        "prepend_dates": {"type": "boolean", "title_key": "workflow.cleanup.prepend_dates", "description_key": "workflow.cleanup.prepend_dates_help", "control": "toggle", "default": False},
        "normalize_separators": {"type": "boolean", "title_key": "workflow.cleanup.normalize_separators", "description_key": "workflow.cleanup.normalize_separators_help", "control": "toggle", "default": True},
    }},
    {"kind": "remove_number_patterns", "stage": "clean", "title_key": "action.remove_numbers", "description_key": "action.remove_numbers.help", "risk": "review", "option_schema": {"patterns": {"type": "array", "title_key": "workflow.cleanup.number_patterns", "description_key": "workflow.cleanup.number_patterns_help", "control": "tags"}}},
    {"kind": "inherit_parent", "stage": "clean", "title_key": "action.inherit_parent", "description_key": "action.inherit_parent.help", "risk": "normal", "option_schema": {"separator": {"type": "string", "title_key": "workflow.cleanup.parent_separator", "description_key": "workflow.cleanup.parent_separator_help", "control": "text", "default": ""}}},
    {"kind": "render_name", "stage": "clean", "title_key": "action.render_name", "description_key": "action.render_name.help", "risk": "review", "option_schema": {"name_template": {"type": "string", "title_key": "workflow.naming.template", "description_key": "workflow.naming.template_help", "control": "template", "default": "{name}"}}},
    {"kind": "keep", "stage": "target", "title_key": "action.keep", "description_key": "action.keep.help", "risk": "safe", "option_schema": {}},
    {"kind": "move", "stage": "target", "title_key": "action.move", "description_key": "action.move.help", "risk": "review", "option_schema": {"path_template": {"type": "string", "title_key": "workflow.target.path", "description_key": "workflow.target.path_help", "control": "template"}, "missing_date": {"type": "string", "enum": ["review", "keep"], "title_key": "workflow.target.missing", "description_key": "workflow.target.missing_help", "control": "select", "default": "review"}}},
    {"kind": "archive", "stage": "target", "title_key": "action.archive", "description_key": "action.archive.help", "risk": "review", "option_schema": {"path_template": {"type": "string", "title_key": "workflow.target.path", "description_key": "workflow.target.path_help", "control": "template", "default": "{year}/{month}"}, "missing_date": {"type": "string", "enum": ["review", "keep"], "title_key": "workflow.target.missing", "description_key": "workflow.target.missing_help", "control": "select", "default": "review"}}},
    {"kind": "quarantine", "stage": "target", "title_key": "action.quarantine", "description_key": "action.quarantine.help", "risk": "high", "option_schema": {}},
    {"kind": "skip", "stage": "review", "title_key": "action.skip", "description_key": "action.skip.help", "risk": "safe", "option_schema": {}},
    {"kind": "require_review", "stage": "review", "title_key": "action.require_review", "description_key": "action.require_review.help", "risk": "safe", "option_schema": {}},
]


def workflow_capability_manifest(registry: ProcessorRegistry) -> dict[str, Any]:
    processors = []
    for processor_manifest in registry.manifests():
        manifest = asdict(processor_manifest)
        schema: dict[str, Any] = {}
        for name, definition in manifest["option_schema"].items():
            schema[name] = {**definition, **OPTION_UI.get(name, {})}
        processors.append({**manifest, "title_key": f"processor.{manifest['id']}", "description_key": f"processor.{manifest['id']}.help", "option_schema": schema})
    return {"schema_version": 1, "actions": ACTION_CAPABILITIES, "processors": processors}


def validate_capability_options(
    options: dict[str, Any],
    schema: dict[str, dict[str, Any]],
    prefix: str,
    *,
    warn_unknown: bool = True,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for name, definition in schema.items():
        value = options.get(name, definition.get("default"))
        if definition.get("required") and (value is None or value == ""):
            errors.append(f"template.option_required:{prefix}:{name}")
            continue
        if value is None:
            continue
        expected = definition.get("type")
        valid_type = (
            expected == "array" and isinstance(value, list)
            or expected == "boolean" and isinstance(value, bool)
            or expected == "integer" and isinstance(value, int) and not isinstance(value, bool)
            or expected == "object" and isinstance(value, dict)
            or expected == "string" and isinstance(value, str)
        )
        if expected and not valid_type:
            errors.append(f"template.option_type:{prefix}:{name}:{expected}")
            continue
        if definition.get("enum") and value not in definition["enum"]:
            errors.append(f"template.option_enum:{prefix}:{name}")
        if isinstance(value, int):
            if definition.get("minimum") is not None and value < definition["minimum"]:
                errors.append(f"template.option_minimum:{prefix}:{name}")
            if definition.get("maximum") is not None and value > definition["maximum"]:
                errors.append(f"template.option_maximum:{prefix}:{name}")
        if definition.get("control") == "regex" and isinstance(value, str):
            try:
                re.compile(value)
            except re.error:
                errors.append(f"template.option_regex:{prefix}:{name}")
    if warn_unknown:
        warnings.extend(
            f"template.option_unknown:{prefix}:{name}"
            for name in sorted(set(options) - set(schema))
        )
    return errors, warnings
