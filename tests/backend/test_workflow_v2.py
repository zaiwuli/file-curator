import json
from pathlib import Path

from fastapi.testclient import TestClient

from file_curator.processors import ProcessingContext, create_default_registry
from file_curator.schemas import (
    Condition,
    ConditionGroup,
    RuleCard,
    WorkflowAction,
    WorkflowStage,
    WorkflowTemplateV2,
)
from file_curator.workflow_engine import conditions_match, run_template_entry
from file_curator.workflow_templates import dump_template, parse_template_text, validate_template


def context(name: str, parent: str = "你好") -> ProcessingContext:
    return ProcessingContext(
        entry_id="1",
        relative_path=f"{parent}/{name}",
        original_name=name,
        parent_path=parent,
        extension=Path(name).suffix.lower(),
        size=10,
        mtime_ns=1,
    )


def template_with(*rules: tuple[str, RuleCard]) -> WorkflowTemplateV2:
    stages = []
    for stage_id in ("scope", "filter", "extract", "clean", "classify", "target", "review", "execute"):
        stages.append(WorkflowStage(id=stage_id, rules=[rule for stage, rule in rules if stage == stage_id]))
    return WorkflowTemplateV2(name="Test", stages=stages)


def test_yaml_json_roundtrip_and_validation() -> None:
    template = template_with(("clean", RuleCard(id="clean", name="Clean", actions=[WorkflowAction(kind="clean_name")])))
    yaml_value = parse_template_text(dump_template(template, "yaml"), "yaml")
    json_value = parse_template_text(dump_template(template, "json"), "json")
    assert yaml_value == json_value
    result = validate_template(json_value, create_default_registry(), "1.0.0")
    assert result.valid is True
    assert result.template == template


def test_v1_template_is_converted_to_rule_cards() -> None:
    legacy = {"schema_version": 1, "name": "Legacy", "processors": [{"id": "normalize_name"}]}
    result = validate_template(legacy, create_default_registry(), "1.0.0")
    assert result.valid is True
    assert result.template is not None
    assert result.template.schema_version == 2
    assert any(rule.id == "legacy.normalize_name" for stage in result.template.stages for rule in stage.rules)


def test_unknown_processor_and_unsafe_path_are_rejected() -> None:
    value = json.loads(dump_template(template_with(("extract", RuleCard(
        id="bad",
        name="Bad",
        actions=[WorkflowAction(kind="run_processor", options={"processor_id": "missing"})],
    )), ("target", RuleCard(
        id="unsafe",
        name="Unsafe",
        actions=[WorkflowAction(kind="archive", options={"path_template": "../outside"})],
    ))), "json"))
    result = validate_template(value, create_default_registry(), "1.0.0")
    assert result.valid is False
    assert result.missing_processors == ["missing"]
    assert "template.unsafe_path:unsafe" in result.errors


def test_nested_conditions_support_all_any_and_not() -> None:
    item = context("movie-2026-01-05.mp4")
    group = ConditionGroup(mode="all", conditions=[
        Condition(field="extension", operator="equals", value=".mp4"),
    ], groups=[ConditionGroup(mode="not", conditions=[Condition(field="filename", operator="contains", value="sample")])])
    assert conditions_match(group, item) is True


def test_multiple_dates_parent_inheritance_and_archive() -> None:
    template = template_with(
        ("extract", RuleCard(id="dates", name="Dates", actions=[WorkflowAction(kind="extract_dates")])),
        ("clean", RuleCard(id="clean", name="Clean", order=1, actions=[WorkflowAction(kind="clean_name", options={
            "remove_words": ["广告"], "prepend_dates": True,
        })])),
        ("clean", RuleCard(id="parent", name="Parent", order=2, actions=[WorkflowAction(kind="inherit_parent")])),
        ("target", RuleCard(id="archive", name="Archive", actions=[WorkflowAction(kind="archive", options={
            "path_template": "{year}/{month}",
        })])),
    )
    item = context("广告好的_2026.1.5_2025-12-08.mp4")
    traces = run_template_entry(template, item, create_default_registry())
    assert item.fields["date_list"] == ["2025-12-08", "2026-01-05"]
    assert item.proposed_name == "你好2025-12-08 2026-01-05 好的.mp4"
    assert item.proposed_parent == "2025/12"
    assert traces[-1].reasons == ["rule.conditions_matched", "action.archive"]


def test_number_cleanup_only_uses_explicit_patterns() -> None:
    template = template_with(("clean", RuleCard(
        id="numbers",
        name="Numbers",
        actions=[WorkflowAction(kind="remove_number_patterns", options={"patterns": [r"(?<!\d)998877(?!\d)"]})],
    )))
    item = context("ABC-123 2026-01-05 998877.mp4")
    run_template_entry(template, item, create_default_registry())
    assert item.proposed_name == "ABC-123 2026-01-05.mp4"


def test_template_api_yaml_import_export_and_impact(
    client: TestClient, media_root: Path
) -> None:
    (media_root / "parent").mkdir()
    (media_root / "parent" / "广告_good_2026.1.5_2025-12-08.MP4").write_text("x")
    source = client.post("/api/sources", json={"name": "V2", "root_path": str(media_root)}).json()
    scan = client.post("/api/scans", json={"source_id": source["id"]}).json()
    for _ in range(100):
        jobs = client.get("/api/scans").json()
        current = next(item for item in jobs if item["id"] == scan["id"])
        if current["status"] == "completed":
            break
        __import__("time").sleep(0.02)
    template = template_with(
        ("extract", RuleCard(id="dates", name="Dates", actions=[WorkflowAction(kind="extract_dates")])),
        ("clean", RuleCard(id="clean", name="Clean", actions=[WorkflowAction(kind="clean_name", options={"remove_words": ["广告"], "prepend_dates": True})])),
        ("target", RuleCard(id="archive", name="Archive", actions=[WorkflowAction(kind="archive", options={"path_template": "{year}/{month}"})])),
    )
    yaml_content = dump_template(template, "yaml")
    validation = client.post("/api/workflow-templates/validate", json={"content": yaml_content, "format": "yaml"})
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    imported = client.post("/api/workflow-templates/import", json={"content": yaml_content, "format": "yaml"})
    assert imported.status_code == 201, imported.text
    workflow_id = imported.json()["id"]
    exported = client.get(f"/api/workflow-templates/{workflow_id}/export?format=json")
    assert exported.status_code == 200
    assert json.loads(exported.text)["schema_version"] == 2
    impact = client.post(f"/api/workflows/{workflow_id}/impact?source_id={source['id']}")
    assert impact.status_code == 200, impact.text
    assert impact.json()["archive"] == 1
