from pathlib import Path

from fastapi.testclient import TestClient

from file_curator.junk_rules import DEFAULT_JUNK_PACK, evaluate_junk
from file_curator.processors import ProcessingContext
from file_curator.schemas import (
    Condition,
    ConditionGroup,
    RuleCard,
    WorkflowAction,
    WorkflowStage,
    WorkflowTemplateV2,
)
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


def test_repeated_hash_across_directories_is_quarantine_evidence() -> None:
    context = item("poster.jpg", size=5000)
    context.fields.update({"hash_duplicate_count": 4, "hash_directory_count": 4})
    result = evaluate_junk(context, DEFAULT_JUNK_PACK)
    assert result.action == "quarantine"
    assert "repeated.hash" in {evidence.rule_id for evidence in result.evidence}


def test_small_text_scan_stores_signals_without_content(client: TestClient, media_root: Path) -> None:
    content = "更多资源请访问 https://example.com 并关注推广频道"
    (media_root / "说明.txt").write_text(content, encoding="utf-8")
    source = client.post(
        "/api/sources", json={"name": "Text fixture", "root_path": str(media_root)}
    ).json()
    scan = client.post(
        "/api/scans",
        json={
            "source_id": source["id"],
            "hash_contents": False,
            "inspect_small_text": True,
        },
    ).json()
    for _ in range(100):
        current = client.get(f"/api/scans/{scan['id']}").json()
        if current["status"] == "completed":
            break
        __import__("time").sleep(0.02)
    with client.app.state.database.session_factory() as session:
        from file_curator.db import FileEntry

        entry = session.query(FileEntry).filter_by(source_id=source["id"], is_dir=False).one()
        assert set(entry.text_signals) == {"url", "promotion"}
        assert content not in str(entry.text_signals)


def test_builtin_template_uses_repeated_hash_evidence(
    client: TestClient, media_root: Path
) -> None:
    payload = b"same promotion image"
    for folder in ("torrent-a", "torrent-b", "torrent-c"):
        directory = media_root / folder
        directory.mkdir()
        (directory / "banner.jpg").write_bytes(payload)
    source = client.post(
        "/api/sources", json={"name": "Hash fixture", "root_path": str(media_root)}
    ).json()
    scan = client.post(
        "/api/scans", json={"source_id": source["id"], "hash_contents": True}
    ).json()
    for _ in range(100):
        current = client.get(f"/api/scans/{scan['id']}").json()
        if current["status"] == "completed":
            break
        __import__("time").sleep(0.02)
    template = next(
        item
        for item in client.get("/api/workflow-templates").json()
        if item["name"] == "Ads and temporary file quarantine"
    )
    workflow = client.post(
        "/api/workflow-templates/import",
        json={
            "content": dump_template(WorkflowTemplateV2.model_validate(template), "json"),
            "format": "json",
        },
    ).json()
    run = client.post(
        "/api/pipeline-runs",
        json={"source_id": source["id"], "workflow_id": workflow["id"]},
    ).json()
    reviews = client.get("/api/reviews", params={"run_id": run["id"]}).json()
    assert len(reviews) == 3
    assert all("junk.repeated.hash" in item["reasons"] for item in reviews)


def test_duplicate_review_template_uses_hash_groups(
    client: TestClient, media_root: Path
) -> None:
    (media_root / "a.mp4").write_bytes(b"same-content")
    (media_root / "b.mp4").write_bytes(b"same-content")
    source = client.post(
        "/api/sources", json={"name": "Duplicate fixture", "root_path": str(media_root)}
    ).json()
    scan = client.post(
        "/api/scans", json={"source_id": source["id"], "hash_contents": True}
    ).json()
    for _ in range(100):
        current = client.get(f"/api/scans/{scan['id']}").json()
        if current["status"] == "completed":
            break
        __import__("time").sleep(0.02)
    template = next(
        item for item in client.get("/api/workflow-templates").json()
        if item["name"] == "Duplicate file review"
    )
    workflow = client.post(
        "/api/workflow-templates/import",
        json={
            "content": dump_template(WorkflowTemplateV2.model_validate(template), "json"),
            "format": "json",
        },
    ).json()
    run = client.post(
        "/api/pipeline-runs",
        json={"source_id": source["id"], "workflow_id": workflow["id"]},
    ).json()
    reviews = client.get("/api/reviews", params={"run_id": run["id"]}).json()
    assert len(reviews) == 2
    assert all("duplicate.hash_group_matched" in item["reasons"] for item in reviews)


def test_duplicate_detector_supports_normalized_name_and_reports_hash_readiness(
    client: TestClient, media_root: Path
) -> None:
    (media_root / "A-B.mp4").write_bytes(b"one")
    (media_root / "ab.mp4").write_bytes(b"two")
    source = client.post(
        "/api/sources", json={"name": "Duplicate methods", "root_path": str(media_root)}
    ).json()
    scan = client.post("/api/scans", json={"source_id": source["id"]}).json()
    for _ in range(100):
        if client.get(f"/api/scans/{scan['id']}").json()["status"] == "completed":
            break
        __import__("time").sleep(0.02)
    template = WorkflowTemplateV2(
        name="Normalized duplicate review",
        stages=[
            WorkflowStage(
                id="classify",
                rules=[
                    RuleCard(
                        id="classify.duplicates",
                        name="Detect duplicates",
                        actions=[
                            WorkflowAction(
                                kind="run_processor",
                                options={
                                    "processor_id": "detect_duplicates",
                                    "method": "normalized_name_size",
                                },
                            )
                        ],
                    )
                ],
            ),
            WorkflowStage(
                id="review",
                rules=[
                    RuleCard(
                        id="review.duplicates",
                        name="Review duplicates",
                        conditions=ConditionGroup(
                            conditions=[
                                Condition(field="duplicate_candidate", operator="is_true")
                            ]
                        ),
                        actions=[WorkflowAction(kind="require_review")],
                    )
                ],
            ),
        ],
    )
    workflow = client.post(
        "/api/workflow-templates/import",
        json={"content": dump_template(template, "json"), "format": "json"},
    ).json()
    run = client.post(
        "/api/pipeline-runs",
        json={"source_id": source["id"], "workflow_id": workflow["id"]},
    ).json()
    reviews = client.get("/api/reviews", params={"run_id": run["id"]}).json()
    assert len(reviews) == 2
    assert all(
        "duplicate.normalized_name_size_group_matched" in item["reasons"]
        for item in reviews
    )

    template.stages[0].rules[0].actions[0].options["method"] = "hash"
    hash_workflow = client.post(
        "/api/workflow-templates/import",
        json={"content": dump_template(template, "json"), "format": "json"},
    ).json()
    dependencies = client.get(
        f"/api/workflows/{hash_workflow['id']}/dependencies",
        params={"source_id": source["id"]},
    ).json()
    assert dependencies == [
        {
            "feature": "hash_duplicate_detection",
            "requires": ["hash_contents_scan"],
            "satisfied": False,
            "message": "Run a content-hash scan before hash duplicate evidence is available.",
        }
    ]
