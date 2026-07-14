import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .processors import ProcessingContext, ProcessorRegistry
from .schemas import Condition, ConditionGroup, WorkflowAction, WorkflowTemplateV2

DATE_PATTERN = re.compile(
    r"(?<!\d)(20\d{2})(?:[-_.]|年)(\d{1,2})(?:[-_.]|月)(\d{1,2})(?:日)?(?!\d)"
)
INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class RuleTrace:
    rule_id: str
    status: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _field(context: ProcessingContext, name: str) -> Any:
    values = {
        "filename": context.original_name,
        "name": context.proposed_name or context.original_name,
        "relative_path": context.relative_path,
        "parent_path": context.parent_path,
        "parent_name": Path(context.parent_path).name if context.parent_path else "",
        "extension": context.extension,
        "size": context.size,
        "mtime_ns": context.mtime_ns,
        "is_empty": context.size == 0,
    }
    return context.fields.get(name, values.get(name))


def _condition_matches(condition: Condition, context: ProcessingContext) -> bool:
    actual = _field(context, condition.field)
    expected = condition.value
    operator = condition.operator
    if operator == "is_true":
        return bool(actual)
    if operator == "is_false":
        return not actual
    if operator == "in":
        return actual in (expected or [])
    if operator == "greater_than":
        return actual is not None and actual > expected
    if operator == "less_than":
        return actual is not None and actual < expected
    actual_text = "" if actual is None else str(actual)
    expected_text = "" if expected is None else str(expected)
    if operator == "equals":
        return actual_text.casefold() == expected_text.casefold()
    if operator == "not_equals":
        return actual_text.casefold() != expected_text.casefold()
    if operator == "contains":
        return expected_text.casefold() in actual_text.casefold()
    if operator == "not_contains":
        return expected_text.casefold() not in actual_text.casefold()
    if operator == "starts_with":
        return actual_text.casefold().startswith(expected_text.casefold())
    if operator == "ends_with":
        return actual_text.casefold().endswith(expected_text.casefold())
    if operator == "regex":
        return re.search(expected_text, actual_text) is not None
    return False


def conditions_match(group: ConditionGroup, context: ProcessingContext) -> bool:
    values = [_condition_matches(item, context) for item in group.conditions]
    values.extend(conditions_match(child, context) for child in group.groups)
    matched = all(values) if group.mode == "all" else any(values)
    if not values:
        matched = True
    return not matched if group.mode == "not" else matched


def _values(context: ProcessingContext) -> dict[str, Any]:
    name = context.proposed_name or context.original_name
    return {
        **context.fields,
        "name": name,
        "clean_name": Path(name).stem,
        "original_stem": Path(context.original_name).stem,
        "extension": context.extension.lstrip("."),
        "parent_name": Path(context.parent_path).name if context.parent_path else "",
        "parent_path": context.parent_path,
    }


def _render(template: str, context: ProcessingContext) -> str:
    return template.format_map(_values(context))


def _extract_dates(context: ProcessingContext) -> tuple[list[str], list[str]]:
    values: set[date] = set()
    warnings: list[str] = []
    for match in DATE_PATTERN.finditer(Path(context.original_name).stem):
        try:
            values.add(date(*(int(part) for part in match.groups())))
        except ValueError:
            warnings.append("date.invalid")
    ordered = sorted(values)
    formatted = [value.isoformat() for value in ordered]
    if formatted:
        earliest = ordered[0]
        latest = ordered[-1]
        context.fields.update({
            "dates": " ".join(formatted),
            "date_list": formatted,
            "earliest_date": earliest.isoformat(),
            "latest_date": latest.isoformat(),
            "year": f"{earliest.year:04d}",
            "month": f"{earliest.month:02d}",
            "day": f"{earliest.day:02d}",
        })
    return formatted, warnings


def _clean_name(context: ProcessingContext, options: dict[str, Any]) -> None:
    current = Path(context.proposed_name or context.original_name)
    stem = unicodedata.normalize("NFC", current.stem)
    protected_dates = [match.group(0) for match in DATE_PATTERN.finditer(stem)]
    if options.get("prepend_dates", False):
        for raw in protected_dates:
            stem = stem.replace(raw, " ")
    for word in options.get("remove_words", []):
        stem = re.sub(re.escape(str(word)), "", stem, flags=re.IGNORECASE)
    for prefix in options.get("remove_prefixes", []):
        if stem.casefold().startswith(str(prefix).casefold()):
            stem = stem[len(str(prefix)) :]
    for suffix in options.get("remove_suffixes", []):
        if stem.casefold().endswith(str(suffix).casefold()):
            stem = stem[: -len(str(suffix))]
    for replacement in options.get("replacements", []):
        stem = re.sub(replacement.get("pattern", "(?!)"), replacement.get("replacement", ""), stem)
    if options.get("normalize_separators", True):
        stem = re.sub(r"[._]+", " ", stem)
    if options.get("prepend_dates", False) and protected_dates:
        dates = context.fields.get("dates", "")
        stem = f"{dates} {stem}"
    stem = re.sub(r"\s+", " ", stem).strip(" ._-")
    stem = INVALID_NAME.sub(options.get("invalid_replacement", "_"), stem)
    context.proposed_name = stem + current.suffix.lower()


def _apply_action(
    action: WorkflowAction, context: ProcessingContext, registry: ProcessorRegistry
) -> tuple[str, list[str], list[str]]:
    options = action.options
    reasons = [f"action.{action.kind}"]
    warnings: list[str] = []
    status = "matched"
    if action.kind == "run_processor":
        processor_id = str(options.get("processor_id"))
        processor_options = {key: value for key, value in options.items() if key != "processor_id"}
        result = registry.get(processor_id).process(context, processor_options)
        context.fields.update(result.fields)
        context.proposed_name = result.proposed_name or context.proposed_name
        context.proposed_parent = result.proposed_parent or context.proposed_parent
        context.confidence += result.confidence_delta
        return result.status, result.reasons, result.warnings
    if action.kind == "extract_dates":
        dates, warnings = _extract_dates(context)
        status = "matched" if dates else "skipped"
    elif action.kind == "clean_name":
        _clean_name(context, options)
    elif action.kind == "remove_number_patterns":
        current = Path(context.proposed_name or context.original_name)
        stem = current.stem
        for pattern in options.get("patterns", []):
            stem = re.sub(pattern, "", stem)
        context.proposed_name = re.sub(r"\s+", " ", stem).strip(" ._-") + current.suffix
    elif action.kind == "inherit_parent":
        parent = Path(context.parent_path).name if context.parent_path else ""
        current = Path(context.proposed_name or context.original_name)
        if parent and not current.stem.casefold().startswith(parent.casefold()):
            separator = str(options.get("separator", ""))
            context.proposed_name = f"{parent}{separator}{current.stem}{current.suffix}"
    elif action.kind == "render_name":
        name = _render(str(options.get("name_template", "{name}")), context)
        if not Path(name).suffix:
            name += context.extension
        context.proposed_name = name
    elif action.kind in {"move", "archive"}:
        path_template = str(options.get("path_template", ""))
        try:
            context.proposed_parent = _render(path_template, context).strip("/\\")
            context.fields["operation_kind"] = "archive" if action.kind == "archive" else "move"
        except KeyError as exc:
            missing_policy = options.get("missing_date", "review")
            if missing_policy == "keep":
                status = "skipped"
            else:
                status = "review"
                warnings.append(f"template.missing_field:{exc.args[0]}")
    elif action.kind == "quarantine":
        context.fields["operation_kind"] = "quarantine"
        status = "review"
        warnings.append("quarantine.review_required")
    elif action.kind == "skip":
        context.fields["skip"] = True
        status = "skipped"
    elif action.kind == "require_review":
        status = "review"
        warnings.append("rule.review_required")
    return status, reasons, warnings


def run_template_entry(
    template: WorkflowTemplateV2, context: ProcessingContext, registry: ProcessorRegistry
) -> list[RuleTrace]:
    traces: list[RuleTrace] = []
    stop = False
    for stage in template.stages:
        if not stage.enabled or stop:
            continue
        for rule in sorted(stage.rules, key=lambda item: item.order):
            if not rule.enabled or stop:
                continue
            input_data = {"name": context.proposed_name or context.original_name, "parent": context.proposed_parent or context.parent_path, "fields": dict(context.fields)}
            if not conditions_match(rule.conditions, context):
                traces.append(RuleTrace(rule.id, "skipped", input_data, input_data, ["rule.conditions_not_matched"]))
                continue
            statuses: list[str] = []
            reasons: list[str] = ["rule.conditions_matched"]
            warnings: list[str] = []
            for action in rule.actions:
                status, action_reasons, action_warnings = _apply_action(action, context, registry)
                statuses.append(status)
                reasons.extend(action_reasons)
                warnings.extend(action_warnings)
            status = "review" if "review" in statuses else "warning" if "warning" in statuses else "matched"
            if rule.on_match == "review":
                status = "review"
                warnings.append("rule.review_required")
            elif rule.on_match == "skip":
                context.fields["skip"] = True
                status = "skipped"
                stop = True
            elif rule.on_match == "stop":
                stop = True
            context.reasons.extend(reasons)
            context.warnings.extend(warnings)
            traces.append(RuleTrace(rule.id, status, input_data, {
                "fields": dict(context.fields),
                "proposed_name": context.proposed_name,
                "proposed_parent": context.proposed_parent,
            }, reasons, warnings))
    return traces
