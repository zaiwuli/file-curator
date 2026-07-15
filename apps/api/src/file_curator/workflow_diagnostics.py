"""Static diagnostics for workflow templates."""

from typing import Any

from .schemas import ConditionGroup, WorkflowTemplateV2


def diagnose_workflow(template: WorkflowTemplateV2) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    enabled_actions: list[tuple[str, str, str, dict[str, Any]]] = []
    duplicate_review_rule: tuple[str, str] | None = None
    for stage in template.stages:
        if not stage.enabled:
            continue
        for rule in stage.rules:
            if not rule.enabled:
                continue
            if not rule.actions:
                diagnostics.append(_item("warning", "workflow.rule_no_action", stage.id, rule.id, "This rule has no action.", "Add an action or disable the rule."))
            if not rule.conditions.conditions and not rule.conditions.groups:
                diagnostics.append(_item("info", "workflow.rule_matches_all", stage.id, rule.id, "This rule applies to every file.", "Add conditions if the action should be scoped."))
            for action in rule.actions:
                enabled_actions.append((stage.id, rule.id, action.kind, action.options))
                if action.kind == "require_review" and _uses_field(rule.conditions, "duplicate_candidate"):
                    duplicate_review_rule = (stage.id, rule.id)

    action_kinds = [item[2] for item in enabled_actions]
    if "archive" in action_kinds:
        archive_options = [item[3] for item in enabled_actions if item[2] == "archive"]
        needs_date = any("{year}" in str(value.get("path_template", "")) or "{month}" in str(value.get("path_template", "")) for value in archive_options)
        if needs_date and "extract_dates" not in action_kinds and not _has_processor(enabled_actions, "extract_date"):
            diagnostics.append(_item("error", "workflow.archive_missing_date", "target", None, "Archive path uses date fields but no date extractor is enabled.", "Add Extract all dates before the archive rule."))
    if duplicate_review_rule and not _has_processor(enabled_actions, "detect_duplicates"):
        stage_id, rule_id = duplicate_review_rule
        diagnostics.append(_item("error", "workflow.duplicate_review_missing_detector", stage_id, rule_id, "Duplicate review is enabled without duplicate detection.", "Add the Detect duplicate groups processor before the review rule."))
    if "quarantine" in action_kinds and "require_review" not in action_kinds:
        diagnostics.append(_item("error", "workflow.quarantine_without_review", "target", None, "Quarantine is enabled without an explicit review action.", "Add Require review to the quarantine rule."))
    if "remove_number_patterns" in action_kinds and "extract_dates" not in action_kinds and not _has_processor(enabled_actions, "extract_identifier"):
        diagnostics.append(_item("warning", "workflow.numbers_unprotected", "clean", None, "Number cleanup runs without date or identifier extraction.", "Extract protected dates and identifiers before removing number patterns."))
    for stage_id, rule_id, kind, options in enabled_actions:
        if kind == "render_name":
            value = str(options.get("name_template", ""))
            if "{dates}" in value and "extract_dates" not in action_kinds:
                diagnostics.append(_item("error", "workflow.name_missing_dates", stage_id, rule_id, "Name template uses {dates} but no multi-date extractor is enabled.", "Add Extract all dates before rendering the name."))
        if kind in {"archive", "move"} and not str(options.get("path_template", "")).strip():
            diagnostics.append(_item("warning", "workflow.empty_destination", stage_id, rule_id, "Move or archive has an empty destination.", "Enter a relative destination folder template."))
    if not any(kind in {"clean_name", "render_name", "move", "archive", "quarantine"} for kind in action_kinds):
        diagnostics.append(_item("info", "workflow.no_file_changes", None, None, "This workflow does not propose file changes.", "Add a naming or target action if changes are intended."))
    return diagnostics


def _has_processor(actions: list[tuple[str, str, str, dict[str, Any]]], processor_id: str) -> bool:
    return any(kind == "run_processor" and options.get("processor_id") == processor_id for _, _, kind, options in actions)


def _uses_field(group: ConditionGroup, field: str) -> bool:
    return any(condition.field == field for condition in group.conditions) or any(
        _uses_field(child, field) for child in group.groups
    )


def _item(severity: str, code: str, stage_id: str | None, rule_id: str | None, message: str, suggestion: str) -> dict[str, Any]:
    return {"severity": severity, "code": code, "stage_id": stage_id, "rule_id": rule_id, "message": message, "suggestion": suggestion}
