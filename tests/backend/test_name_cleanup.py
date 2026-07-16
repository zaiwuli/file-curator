from fastapi.testclient import TestClient

from file_curator.name_cleanup import apply_cleanup_packs, validate_cleanup_pack
from file_curator.processors import ProcessingContext, create_default_registry
from file_curator.schemas import (
    NameCleanupPack,
    NameCleanupRule,
    RuleCard,
    WorkflowAction,
    WorkflowStage,
    WorkflowTemplateV2,
)
from file_curator.workflow_engine import run_template_entry
from file_curator.workflow_templates import dump_template


def rule(id: str, kind: str, pattern: str, order: int, replacement: str = ""):
    return NameCleanupRule(
        id=id, name=id, kind=kind, pattern=pattern,
        replacement=replacement, order=order,
    )


def pack(*rules: NameCleanupRule) -> NameCleanupPack:
    return NameCleanupPack(id="test-cleanup", name="Test cleanup", rules=list(rules))


def template(options: dict) -> WorkflowTemplateV2:
    stages = [
        WorkflowStage(id=stage, rules=[])
        for stage in ("scope", "filter", "extract", "clean", "classify", "target", "review", "execute")
    ]
    stages[3].rules.append(RuleCard(
        id="clean", name="Clean", actions=[WorkflowAction(kind="clean_name", options=options)]
    ))
    return WorkflowTemplateV2(name="Cleanup", stages=stages)


def test_cleanup_actions_scope_order_and_protection() -> None:
    value = pack(
        rule("prefix", "remove_prefix", "[site]", 0),
        rule("contains", "remove_contains", "advert", 1),
        rule("literal", "literal_replace", "_", 2, " "),
        rule("regex", "regex_replace", r"\s+", 3, "-"),
        rule("suffix", "remove_suffix", "-copy", 4),
    )
    result, reasons, warnings = apply_cleanup_packs(
        "[site]advert_movie-copy", "downloads/file.mp4", ".mp4",
        [value.model_dump(mode="json")],
    )
    assert result == "movie"
    assert len(reasons) == 5
    assert warnings == []
    value.protected_keywords = ["favorite"]
    protected, reasons, _ = apply_cleanup_packs(
        "favorite_advert", "favorite.mp4", ".mp4", [value.model_dump(mode="json")]
    )
    assert protected == "favorite_advert"
    assert reasons == ["cleanup.protected:test-cleanup"]


def test_cleanup_validation_detects_regex_and_conflicts() -> None:
    value = pack(
        rule("one", "regex_replace", "[", 0, "a"),
        rule("two", "regex_replace", "[", 1, "b"),
    )
    result = validate_cleanup_pack(value)
    assert result.valid is False
    assert "cleanup.invalid_regex:one" in result.errors
    assert "cleanup.conflicting_replacement:two" in result.warnings


def test_cleanup_packs_run_before_workflow_words_and_keep_extension() -> None:
    value = pack(rule("site", "remove_contains", "site", 0))
    workflow = template({
        "cleanup_packs": [value.model_dump(mode="json")],
        "remove_words": ["private"],
    })
    context = ProcessingContext(
        entry_id="1", relative_path="downloads/site_private_movie.MKV",
        original_name="site_private_movie.MKV", parent_path="downloads",
        extension=".mkv", size=1, mtime_ns=1,
    )
    traces = run_template_entry(workflow, context, create_default_registry())
    assert context.proposed_name == "movie.mkv"
    assert "cleanup.rule:test-cleanup:1:site" in traces[0].reasons


def test_cleanup_regex_cannot_remove_protected_date() -> None:
    value = pack(rule("digits", "regex_replace", r"\d+", 0, ""))
    workflow = template({"cleanup_packs": [value.model_dump(mode="json")]})
    context = ProcessingContext(
        entry_id="1", relative_path="movie_2026-01-05.mp4",
        original_name="movie_2026-01-05.mp4", parent_path="",
        extension=".mp4", size=1, mtime_ns=1,
    )
    run_template_entry(workflow, context, create_default_registry())
    assert context.proposed_name == "movie 2026-01-05.mp4"


def test_cleanup_pack_version_api_and_workflow_snapshot(client: TestClient) -> None:
    payload = {
        "name": "Personal cleanup", "description": "",
        "protected_names": [], "protected_keywords": [], "protected_regex": [],
        "normalize_separators": True, "normalize_width": False,
        "deduplicate_words": True, "max_name_length": 240,
        "rules": [rule("ad", "remove_contains", "advert", 0).model_dump(mode="json")],
        "change_note": "initial",
    }
    created = client.post("/api/name-cleanup-packs", json=payload)
    assert created.status_code == 201, created.text
    item = created.json()
    payload["description"] = "updated"
    payload["change_note"] = "second"
    updated = client.put(f"/api/name-cleanup-packs/{item['id']}", json=payload)
    assert updated.json()["current_version"] == 2
    versions = client.get(f"/api/name-cleanup-packs/{item['id']}/versions").json()
    assert [row["version"] for row in versions] == [2, 1]
    workflow = client.post("/api/workflows", json={"name": "Cleanup workflow"}).json()
    applied = client.post(
        f"/api/name-cleanup-packs/{item['id']}/apply",
        json={"workflow_id": workflow["id"], "version": 1},
    )
    assert applied.status_code == 200, applied.text
    exported = client.get(
        f"/api/workflow-templates/{workflow['id']}/export?format=json"
    ).json()
    action = next(
        action for stage in exported["stages"] for rule_value in stage["rules"]
        for action in rule_value["actions"] if action["kind"] == "clean_name"
    )
    assert action["options"]["cleanup_pack_refs"] == [{"pack_id": item["id"], "version": 1}]
    assert action["options"]["cleanup_packs"][0]["description"] == ""


def test_cleanup_reference_resolves_and_missing_version_blocks_import(client: TestClient) -> None:
    workflow = template({
        "cleanup_pack_refs": [{"pack_id": "bt-name-cleanup", "version": 1}]
    })
    content = dump_template(workflow, "json")
    resolved = client.post("/api/workflow-templates/resolve", json={
        "content": content, "format": "json",
    }).json()
    assert resolved["ready_to_import"] is True
    assert resolved["template"]["stages"][3]["rules"][0]["actions"][0]["options"]["cleanup_packs"][0]["id"] == "bt-name-cleanup"
    workflow.stages[3].rules[0].actions[0].options["cleanup_pack_refs"] = [
        {"pack_id": "bt-name-cleanup", "version": 99}
    ]
    rejected = client.post("/api/workflow-templates/import", json={
        "content": dump_template(workflow, "json"), "format": "json",
    })
    assert rejected.status_code == 422
