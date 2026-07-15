import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from .processors import ProcessorRegistry
from .schemas import (
    Condition,
    ConditionGroup,
    ProcessorConfig,
    RuleCard,
    TemplateValidationResult,
    WorkflowAction,
    WorkflowStage,
    WorkflowTemplateV2,
)

STAGE_ORDER = ["scope", "filter", "extract", "clean", "classify", "target", "review", "execute"]
ACTION_STAGES = {
    "run_processor": {"extract", "clean", "classify"},
    "extract_dates": {"extract"},
    "clean_name": {"clean"},
    "remove_number_patterns": {"clean"},
    "inherit_parent": {"clean"},
    "render_name": {"clean", "target"},
    "keep": {"target"},
    "move": {"target"},
    "archive": {"target"},
    "quarantine": {"target"},
    "skip": {"filter", "target"},
    "require_review": {"review", "target"},
}
ALLOWED_TEMPLATE_FIELDS = {
    "name", "clean_name", "original_stem", "extension", "parent_name", "parent_path",
    "dates", "earliest_date", "latest_date", "year", "month", "day", "identifier",
    "sequence", "resolution", "language", "category",
}


def parse_template_text(content: str, format_name: str = "auto") -> dict[str, Any]:
    try:
        if format_name == "json" or (format_name == "auto" and content.lstrip().startswith(("{", "["))):
            value = json.loads(content)
        else:
            value = yaml.safe_load(content)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError("template.parse_failed") from exc
    if not isinstance(value, dict):
        raise ValueError("template.root_must_be_object")
    return value


def _processor_rule(config: ProcessorConfig, order: int) -> RuleCard:
    return RuleCard(
        id=f"legacy.{config.id}",
        name=config.id.replace("_", " ").title(),
        enabled=config.enabled,
        order=order,
        conditions=ConditionGroup(),
        actions=[WorkflowAction(kind="run_processor", options={"processor_id": config.id, **config.options})],
    )


def convert_v1_template(value: dict[str, Any]) -> WorkflowTemplateV2:
    processors = [ProcessorConfig.model_validate(item) for item in value.get("processors", [])]
    grouped: dict[str, list[RuleCard]] = {stage: [] for stage in STAGE_ORDER}
    for order, config in enumerate(processors):
        category = config.id.split("_", 1)[0]
        stage = "extract" if category in {"extract", "detect"} else "classify" if category == "classify" else "target" if category == "target" else "clean"
        grouped[stage].append(_processor_rule(config, order))
    return WorkflowTemplateV2(
        name=value.get("name", "Imported workflow"),
        description="Converted from workflow schema v1.",
        preset=value.get("preset", "rename_only"),
        review_policy=value.get("review_policy", "balanced"),
        stages=[WorkflowStage(id=stage, rules=grouped[stage]) for stage in STAGE_ORDER],
    )


def normalize_template(value: dict[str, Any]) -> WorkflowTemplateV2:
    if value.get("schema_version", 1) == 1:
        return convert_v1_template(value)
    return WorkflowTemplateV2.model_validate(value)


def _template_variables(value: str) -> set[str]:
    return set(re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", value))


def validate_template(value: dict[str, Any], registry: ProcessorRegistry, version: str) -> TemplateValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    risks: list[str] = []
    try:
        template = normalize_template(value)
    except (ValidationError, ValueError) as exc:
        return TemplateValidationResult(valid=False, errors=[f"template.schema_invalid:{exc}"])
    seen_stages: set[str] = set()
    seen_rules: set[str] = set()
    manifests = {item.id: item for item in registry.manifests()}
    for stage in template.stages:
        if stage.id in seen_stages:
            errors.append(f"template.duplicate_stage:{stage.id}")
        seen_stages.add(stage.id)
        for rule in stage.rules:
            if rule.id in seen_rules:
                errors.append(f"template.duplicate_rule:{rule.id}")
            seen_rules.add(rule.id)
            for action in rule.actions:
                if stage.id not in ACTION_STAGES[action.kind]:
                    errors.append(f"template.action_wrong_stage:{rule.id}:{action.kind}:{stage.id}")
                if action.kind == "run_processor":
                    processor_id = str(action.options.get("processor_id", ""))
                    if processor_id not in manifests:
                        missing.append(processor_id or "<empty>")
                for option_name in ("name_template", "parent_template", "path_template"):
                    option = action.options.get(option_name)
                    if isinstance(option, str):
                        unknown = _template_variables(option) - ALLOWED_TEMPLATE_FIELDS
                        errors.extend(f"template.unknown_variable:{rule.id}:{field}" for field in sorted(unknown))
                        if Path(option).is_absolute() or ".." in Path(option).parts or ":" in option:
                            errors.append(f"template.unsafe_path:{rule.id}")
                if action.kind == "quarantine":
                    risks.append(f"template.quarantine_action:{rule.id}")
    if set(STAGE_ORDER) - seen_stages:
        warnings.append("template.missing_optional_stages")
    if template.minimum_version > version:
        errors.append(f"template.minimum_version:{template.minimum_version}")
    for processor_id, minimum in template.required_processors.items():
        manifest = manifests.get(processor_id)
        if not manifest:
            missing.append(processor_id)
        elif manifest.version < minimum:
            errors.append(f"template.processor_version:{processor_id}:{minimum}")
    if missing:
        errors.append("template.missing_processors")
    return TemplateValidationResult(
        valid=not errors,
        template=template,
        errors=errors,
        warnings=warnings,
        missing_processors=sorted(set(missing)),
        risks=risks,
    )


def dump_template(template: WorkflowTemplateV2, format_name: str) -> str:
    value = template.model_dump(mode="json")
    if format_name == "json":
        return json.dumps(value, indent=2, ensure_ascii=False)
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)


def processors_from_template(template: WorkflowTemplateV2) -> list[ProcessorConfig]:
    processors: list[ProcessorConfig] = []
    for stage in template.stages:
        for rule in sorted(stage.rules, key=lambda item: item.order):
            if not rule.enabled:
                continue
            for action in rule.actions:
                if action.kind != "run_processor":
                    continue
                options = deepcopy(action.options)
                processor_id = str(options.pop("processor_id"))
                processors.append(ProcessorConfig(id=processor_id, options=options))
    return processors


def template_from_revision(name: str, preset: str, review_policy: str, config: dict[str, Any]) -> WorkflowTemplateV2:
    if "template" in config:
        return WorkflowTemplateV2.model_validate(config["template"])
    return convert_v1_template({
        "schema_version": 1,
        "name": name,
        "preset": preset,
        "review_policy": review_policy,
        "processors": config.get("processors", []),
    })


def builtin_templates() -> list[WorkflowTemplateV2]:
    def stages(*rules: tuple[str, RuleCard]) -> list[WorkflowStage]:
        grouped: dict[str, list[RuleCard]] = {stage: [] for stage in STAGE_ORDER}
        for stage, rule in rules:
            grouped[stage].append(rule)
        return [WorkflowStage(id=stage, rules=grouped[stage]) for stage in STAGE_ORDER]

    clean = RuleCard(id="clean.names", name="Clean file names", actions=[WorkflowAction(kind="clean_name", options={"normalize_separators": True})])
    dates = RuleCard(id="extract.dates", name="Extract all dates", actions=[WorkflowAction(kind="extract_dates")])
    parent = RuleCard(id="clean.parent", name="Inherit parent name", actions=[WorkflowAction(kind="inherit_parent")])
    archive = RuleCard(id="target.archive", name="Archive by year and month", actions=[WorkflowAction(kind="archive", options={"path_template": "{year}/{month}", "missing_date": "keep"})])
    junk_detect = RuleCard(
        id="classify.junk",
        name="Detect BT advertisements and junk",
        actions=[WorkflowAction(kind="run_processor", options={"processor_id": "detect_junk"})],
    )
    quarantine = RuleCard(
        id="target.junk",
        name="Quarantine junk candidates",
        conditions=ConditionGroup(
            conditions=[Condition(field="junk_action", operator="equals", value="quarantine")]
        ),
        actions=[WorkflowAction(kind="quarantine"), WorkflowAction(kind="require_review")],
    )
    image_filter = ConditionGroup(mode="any", conditions=[Condition(
        field="extension", operator="in", value=[".jpg", ".jpeg", ".png", ".webp", ".heic"]
    )])
    media_filter = ConditionGroup(mode="any", conditions=[Condition(
        field="extension", operator="in", value=[".mp4", ".mkv", ".avi", ".mov", ".srt", ".ass"]
    )])
    media_classify = RuleCard(
        id="classify.media", name="Classify media files", conditions=media_filter,
        actions=[WorkflowAction(kind="run_processor", options={"processor_id": "classify_extension"})],
    )
    media_target = RuleCard(
        id="target.media", name="Organize by media category", conditions=media_filter,
        actions=[WorkflowAction(kind="archive", options={"path_template": "{category}", "missing_date": "keep"})],
    )
    image_dates = RuleCard(id="extract.image_dates", name="Extract image dates", conditions=image_filter, actions=[WorkflowAction(kind="extract_dates")])
    image_archive = RuleCard(id="target.image_archive", name="Archive dated images", conditions=image_filter, actions=[WorkflowAction(kind="archive", options={"path_template": "{year}/{month}", "missing_date": "review"})])
    duplicates = RuleCard(
        id="review.duplicates", name="Review duplicate candidates",
        conditions=ConditionGroup(conditions=[Condition(field="duplicate_candidate", operator="is_true")]),
        actions=[WorkflowAction(kind="require_review")],
    )
    duplicate_detect = RuleCard(
        id="classify.duplicates", name="Detect indexed duplicate groups",
        actions=[WorkflowAction(kind="run_processor", options={"processor_id": "detect_duplicates"})],
    )
    return [
        WorkflowTemplateV2(name="Clean file names", description="Normalize names without moving files.", stages=stages(("clean", clean))),
        WorkflowTemplateV2(name="Archive by year and month", description="Extract dates and archive within the source.", preset="rename_and_organize", stages=stages(("extract", dates), ("target", archive))),
        WorkflowTemplateV2(name="Inherit parent folder", description="Prefix names with the direct parent folder.", stages=stages(("clean", parent))),
        WorkflowTemplateV2(name="Image date archive", description="Archive dated images by year and month.", preset="rename_and_organize", stages=stages(("extract", image_dates), ("target", image_archive))),
        WorkflowTemplateV2(name="Media organization", description="Classify and organize common media and sidecar files.", preset="rename_and_organize", stages=stages(("classify", media_classify), ("clean", clean), ("target", media_target))),
        WorkflowTemplateV2(name="Downloads cleanup", description="Clean download names and review incomplete files.", stages=stages(("classify", junk_detect), ("clean", clean), ("target", quarantine))),
        WorkflowTemplateV2(name="Ads and temporary file quarantine", description="Detect BT advertisements and quarantine candidates for review.", stages=stages(("classify", junk_detect), ("target", quarantine))),
        WorkflowTemplateV2(name="Duplicate file review", description="Detect indexed duplicate groups and send candidates to review.", stages=stages(("classify", duplicate_detect), ("review", duplicates))),
    ]
