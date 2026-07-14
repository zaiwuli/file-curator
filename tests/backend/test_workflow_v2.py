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


def scan_source(client: TestClient, media_root: Path) -> str:
    source = client.post(
        "/api/sources", json={"name": "Rules", "root_path": str(media_root)}
    ).json()
    scan = client.post("/api/scans", json={"source_id": source["id"]}).json()
    for _ in range(100):
        current = next(item for item in client.get("/api/scans").json() if item["id"] == scan["id"])
        if current["status"] == "completed":
            break
        __import__("time").sleep(0.02)
    return source["id"]


def import_and_run(client: TestClient, source_id: str, template: WorkflowTemplateV2) -> dict:
    workflow = client.post(
        "/api/workflow-templates/import",
        json={"content": dump_template(template, "json"), "format": "json"},
    ).json()
    run = client.post(
        "/api/pipeline-runs",
        json={"source_id": source_id, "workflow_id": workflow["id"]},
    ).json()
    return {"workflow": workflow, "run": run}


def test_quarantine_review_accept_creates_operation(client: TestClient, media_root: Path) -> None:
    (media_root / "advert.tmp").write_text("junk")
    source_id = scan_source(client, media_root)
    template = template_with(("target", RuleCard(
        id="quarantine",
        name="Quarantine",
        actions=[WorkflowAction(kind="quarantine")],
    )))
    values = import_and_run(client, source_id, template)
    reviews = client.get("/api/reviews", params={"run_id": values["run"]["id"]}).json()
    assert len(reviews) == 1
    client.put(
        f"/api/reviews/{values['run']['id']}/{reviews[0]['file_entry_id']}",
        json={"action": "accept"},
    )
    plan = client.post("/api/plans", json={"run_id": values["run"]["id"]}).json()
    assert plan["operations"][0]["kind"] == "quarantine"
    assert plan["operations"][0]["source_relative_path"] == "advert.tmp"


def conflict_template(policy: str) -> WorkflowTemplateV2:
    template = template_with(("clean", RuleCard(
        id="fixed",
        name="Fixed target",
        actions=[WorkflowAction(kind="render_name", options={"name_template": "fixed.mp4"})],
    )))
    return template.model_copy(update={"conflict_policy": policy})


def test_append_number_conflict_policy(client: TestClient, media_root: Path) -> None:
    (media_root / "source.mp4").write_text("source")
    (media_root / "fixed.mp4").write_text("existing")
    source_id = scan_source(client, media_root)
    values = import_and_run(client, source_id, conflict_template("append_number"))
    plan = client.post("/api/plans", json={"run_id": values["run"]["id"]}).json()
    targets = [item["target_relative_path"] for item in plan["operations"]]
    assert "fixed (1).mp4" in targets


def test_skip_and_stop_conflict_policies(client: TestClient, media_root: Path) -> None:
    (media_root / "source.mp4").write_text("source")
    (media_root / "fixed.mp4").write_text("existing")
    source_id = scan_source(client, media_root)
    skipped = import_and_run(client, source_id, conflict_template("skip"))
    plan = client.post("/api/plans", json={"run_id": skipped["run"]["id"]}).json()
    assert plan["summary"]["conflict_count"] >= 1
    stopped = import_and_run(client, source_id, conflict_template("stop"))
    response = client.post("/api/plans", json={"run_id": stopped["run"]["id"]})
    assert response.status_code == 400
    assert response.json()["detail"] == "operation.target_conflict"


def test_workflow_update_invalidates_draft_plans(client: TestClient, media_root: Path) -> None:
    (media_root / "source.mp4").write_text("source")
    source_id = scan_source(client, media_root)
    template = conflict_template("append_number")
    values = import_and_run(client, source_id, template)
    plan = client.post("/api/plans", json={"run_id": values["run"]["id"]}).json()
    template.name = "Updated template"
    response = client.put(
        f"/api/workflow-templates/{values['workflow']['id']}", json={"template": template.model_dump(mode="json")}
    )
    assert response.status_code == 200
    plans = client.get("/api/plans").json()
    assert next(item for item in plans if item["id"] == plan["id"])["status"] == "invalidated"


def test_unmatched_later_rule_does_not_erase_prior_action(
    client: TestClient, media_root: Path
) -> None:
    (media_root / "episode_2026-01-05.mp4").write_text("media")
    source_id = scan_source(client, media_root)
    template = template_with(
        ("clean", RuleCard(
            id="rename",
            name="Rename",
            actions=[WorkflowAction(kind="render_name", options={"name_template": "renamed.mp4"})],
        )),
        ("target", RuleCard(
            id="only-tmp",
            name="Only temporary files",
            conditions=ConditionGroup(conditions=[Condition(field="extension", operator="equals", value=".tmp")]),
            actions=[WorkflowAction(kind="quarantine")],
        )),
    )
    values = import_and_run(client, source_id, template)
    plan = client.post("/api/plans", json={"run_id": values["run"]["id"]}).json()
    assert plan["operations"][0]["target_relative_path"] == "renamed.mp4"


def test_full_workflow_simulation_returns_step_by_step_archive(client: TestClient) -> None:
    template = template_with(
        ("extract", RuleCard(id="dates", name="Dates", actions=[WorkflowAction(kind="extract_dates")])),
        ("clean", RuleCard(id="clean", name="Clean", actions=[WorkflowAction(kind="clean_name", options={"remove_words": ["AD"], "prepend_dates": True})])),
        ("target", RuleCard(id="archive", name="Archive", actions=[WorkflowAction(kind="archive", options={"path_template": "{year}/{month}"})])),
    )
    response = client.post("/api/workflow-templates/simulate", json={
        "template": template.model_dump(mode="json"),
        "relative_path": "parent/AD_movie_2026.1.5.mp4",
        "size": 100,
    })
    assert response.status_code == 200
    result = response.json()
    assert result["action"] == "archive"
    assert result["proposed_path"] == "2026/01/2026-01-05 movie.mp4"
    assert [step["rule_id"] for step in result["steps"]] == ["dates", "clean", "archive"]


def test_workflow_diagnostics_find_missing_dependencies(client: TestClient) -> None:
    template = template_with(
        ("clean", RuleCard(id="numbers", name="Numbers", actions=[WorkflowAction(kind="remove_number_patterns", options={"patterns": [r"\d{6}"]})])),
        ("target", RuleCard(id="archive", name="Archive", actions=[WorkflowAction(kind="archive", options={"path_template": "{year}/{month}"})])),
        ("target", RuleCard(id="quarantine", name="Quarantine", order=1, actions=[WorkflowAction(kind="quarantine")])),
    )
    response = client.post(
        "/api/workflow-templates/diagnostics", json=template.model_dump(mode="json")
    )
    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is False
    codes = {item["code"] for item in result["diagnostics"]}
    assert "workflow.archive_missing_date" in codes
    assert "workflow.quarantine_without_review" in codes
    assert "workflow.numbers_unprotected" in codes
