from pathlib import Path

from fastapi.testclient import TestClient

from file_curator.junk_rules import DEFAULT_JUNK_PACK, evaluate_junk
from file_curator.processors import ProcessingContext
from file_curator.schemas import WorkflowTemplateV2
from file_curator.workflow_templates import dump_template


def item(name: str, size: int = 10, parent: str = "media") -> ProcessingContext:
    return ProcessingContext(
        entry_id="junk-test",
        relative_path=f"{parent}/{name}",
        original_name=name,
        parent_path=parent,
        extension=Path(name).suffix.lower(),
        size=size,
        mtime_ns=1,
    )


def test_bt_advertisement_keywords_and_links_are_quarantine_candidates() -> None:
    ad = evaluate_junk(item("更多资源_最新地址.url"), DEFAULT_JUNK_PACK)
    assert ad.action == "quarantine"
    assert {e.rule_id for e in ad.evidence} >= {"link.file", "ad.keyword"}


def test_protected_sidecar_is_not_marked_by_generic_rules() -> None:
    result = evaluate_junk(item("广告说明.nfo"), DEFAULT_JUNK_PACK)
    assert result.candidate is False
    assert result.protected is True


def test_tiny_text_and_empty_files_are_review_candidates() -> None:
    text = evaluate_junk(item("readme.txt", size=50), DEFAULT_JUNK_PACK)
    empty = evaluate_junk(item("unknown.bin", size=0), DEFAULT_JUNK_PACK)
    assert text.action == "review"
    assert empty.action == "review"


def test_junk_pack_endpoint_and_validation(client: TestClient) -> None:
    packs = client.get("/api/junk-rule-packs")
    assert packs.status_code == 200
    assert packs.json()[0]["id"] == "bt-advertisement-and-junk"
    invalid = {
        "id": "custom",
        "name": "Custom",
        "rules": [{"id": "bad", "name": "Bad", "filename_regex": ["["]}],
    }
    response = client.post("/api/junk-rule-packs/validate", json=invalid)
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert "junk.invalid_regex:bad" in response.json()["errors"]


def test_custom_junk_processor_options_are_supported() -> None:
    from file_curator.processors import create_default_registry

    context = item("release.notice")
    result = create_default_registry().get("detect_junk").process(
        context, {"extensions": [".notice"]}
    )
    assert result.fields["junk_candidate"] is True
    assert result.fields["junk_action"] == "quarantine"


def test_bt_rule_processor_records_explainable_evidence() -> None:
    from file_curator.processors import create_default_registry

    context = item("扫码关注_更多资源.url", size=512)
    result = create_default_registry().get("detect_junk").process(context, {})
    assert result.status == "matched"
    assert result.fields["junk_score"] == 100
    assert {item["rule_id"] for item in result.fields["junk_evidence"]} >= {
        "link.file",
        "ad.keyword",
    }
    assert "junk.link.file" in result.reasons


def test_builtin_bt_template_creates_explainable_quarantine_review(
    client: TestClient, media_root: Path
) -> None:
    (media_root / "movie.mkv").write_bytes(b"0" * 1_100_000)
    (media_root / "扫码关注_更多资源.url").write_text("shortcut")
    source = client.post(
        "/api/sources", json={"name": "BT fixture", "root_path": str(media_root)}
    ).json()
    scan = client.post("/api/scans", json={"source_id": source["id"]}).json()
    for _ in range(100):
        jobs = client.get("/api/scans").json()
        current = next(item for item in jobs if item["id"] == scan["id"])
        if current["status"] == "completed":
            break
        __import__("time").sleep(0.02)
    template = next(
        item
        for item in client.get("/api/workflow-templates").json()
        if item["name"] == "Ads and temporary file quarantine"
    )
    imported = client.post(
        "/api/workflow-templates/import",
        json={
            "content": dump_template(WorkflowTemplateV2.model_validate(template), "json"),
            "format": "json",
        },
    ).json()
    run = client.post(
        "/api/pipeline-runs",
        json={"source_id": source["id"], "workflow_id": imported["id"]},
    ).json()
    reviews = client.get("/api/reviews", params={"run_id": run["id"]}).json()
    assert len(reviews) == 1
    assert reviews[0]["relative_path"] == "扫码关注_更多资源.url"
    assert "junk.link.file" in reviews[0]["reasons"]
    assert "junk.ad.keyword" in reviews[0]["reasons"]
