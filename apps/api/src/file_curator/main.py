import os
import re
import secrets
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .db import (
    AuditLog,
    Database,
    ExecutionBatch,
    FileEntry,
    FileGroup,
    JunkRulePackRecord,
    JunkRulePackVersion,
    PipelineRun,
    Plan,
    ReviewDecision,
    ScanJob,
    Schedule,
    Source,
    StageResult,
    Workflow,
    WorkflowRevision,
)
from .filesystem import FileSafetyError, normalize_root, probe_capabilities, resolve_inside
from .junk_rules import DEFAULT_JUNK_PACK, junk_pack_dict
from .processors import ProcessingContext, create_default_registry
from .schemas import (
    AuditRead,
    BackupRead,
    BatchRead,
    Condition,
    ConditionGroup,
    DiagnosticsRead,
    DuplicateCandidate,
    FileGroupRead,
    FilePage,
    FileRead,
    JunkRulePack,
    JunkRulePackApply,
    JunkRulePackValidation,
    JunkRulePackVersionRead,
    JunkRulePackWrite,
    ManualPlanCreate,
    PipelineRunCreate,
    PipelineRunRead,
    PlanCreate,
    PlanRead,
    PreflightRead,
    ReviewDecisionRead,
    ReviewDecisionUpsert,
    ReviewItemRead,
    RollbackPreview,
    RuleCard,
    RuleTestInput,
    RuleTestResult,
    ScanCreate,
    ScanRead,
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
    SourceCreate,
    SourceRead,
    SourceUpdate,
    StageResultRead,
    TemplateImportInput,
    TemplateTextInput,
    TemplateValidationResult,
    WorkflowAction,
    WorkflowCompare,
    WorkflowCreate,
    WorkflowDependency,
    WorkflowDiagnosticsResult,
    WorkflowImpactSummary,
    WorkflowPortable,
    WorkflowRead,
    WorkflowRevisionCreate,
    WorkflowRevisionRead,
    WorkflowSimulationInput,
    WorkflowSimulationResult,
    WorkflowStage,
    WorkflowTemplateUpdate,
    WorkflowTemplateV2,
)
from .services import (
    DEFAULT_PROCESSORS,
    DomainError,
    confirm_plan,
    create_backup,
    create_manual_plan,
    create_plan_from_pipeline,
    freeze_plan,
    get_revision,
    preflight_plan,
    queue_plan_execution,
    rollback_batch,
    run_pipeline,
)
from .workers import WorkerService
from .workflow_capabilities import workflow_capability_manifest
from .workflow_diagnostics import diagnose_workflow
from .workflow_engine import run_template_entry
from .workflow_templates import (
    builtin_templates,
    dump_template,
    parse_template_text,
    processors_from_template,
    scan_requirements,
    template_from_revision,
    validate_template,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.resolved_database_url)
    registry = create_default_registry()
    worker = WorkerService(database, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.config_dir.mkdir(parents=True, exist_ok=True)
        database.create_all()
        if settings.worker_enabled:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        root_path=settings.base_path.rstrip("/"),
    )
    app.state.settings = settings
    app.state.database = database
    app.state.registry = registry
    app.state.worker = worker

    @app.middleware("http")
    async def token_auth(request, call_next):
        if settings.admin_token and request.url.path.startswith("/api"):
            authorization = request.headers.get("authorization", "")
            bearer = authorization[7:] if authorization.lower().startswith("bearer ") else ""
            supplied = bearer or request.headers.get("x-api-token", "")
            if not secrets.compare_digest(supplied, settings.admin_token):
                from fastapi.responses import JSONResponse

                return JSONResponse(status_code=401, content={"detail": "auth.invalid_token"})
        return await call_next(request)

    def session_dependency():
        yield from database.session()

    def require(model: Any, identifier: str, session: Session):
        instance = session.get(model, identifier)
        if not instance:
            raise HTTPException(404, detail=f"{model.__tablename__}.not_found")
        return instance

    @app.exception_handler(DomainError)
    async def domain_error_handler(_, exc: DomainError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content={"detail": exc.code})

    @app.exception_handler(FileSafetyError)
    async def file_error_handler(_, exc: FileSafetyError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": exc.code})

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "version": settings.version}

    @app.get("/health/ready")
    def health_ready(session: Session = Depends(session_dependency)) -> dict[str, str]:
        session.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ready"}

    @app.get("/api/processors")
    def processors() -> list[dict[str, Any]]:
        return [manifest.__dict__ for manifest in registry.manifests()]

    @app.get("/api/workflow-capabilities")
    def workflow_capabilities() -> dict[str, Any]:
        return workflow_capability_manifest(registry)

    def personal_junk_pack(
        record: JunkRulePackRecord, version: JunkRulePackVersion
    ) -> dict[str, Any]:
        return {
            **version.payload,
            "id": record.id,
            "version": str(version.version),
            "source": "personal",
            "read_only": False,
            "current_version": record.current_version,
        }

    def junk_pack_version(
        pack_id: str, version: int | None, session: Session
    ) -> dict[str, Any]:
        if pack_id == DEFAULT_JUNK_PACK.id:
            if version not in {None, 1}:
                raise HTTPException(404, detail="junk_rule_pack_versions.not_found")
            return junk_pack_dict(DEFAULT_JUNK_PACK)
        record = require(JunkRulePackRecord, pack_id, session)
        selected_version = version or record.current_version
        row = session.query(JunkRulePackVersion).filter_by(
            pack_id=record.id, version=selected_version
        ).one_or_none()
        if row is None:
            raise HTTPException(404, detail="junk_rule_pack_versions.not_found")
        return personal_junk_pack(record, row)

    def validate_junk_pack(payload: JunkRulePack) -> JunkRulePackValidation:
        errors: list[str] = []
        warnings: list[str] = []
        seen: set[str] = set()
        for rule in payload.rules:
            if rule.id in seen:
                errors.append(f"junk.duplicate_rule:{rule.id}")
            seen.add(rule.id)
            for pattern in rule.filename_regex:
                try:
                    re.compile(pattern)
                except re.error:
                    errors.append(f"junk.invalid_regex:{rule.id}")
            bounded = (
                rule.extensions or rule.filename_contains or rule.filename_regex
                or rule.path_contains or rule.empty_only
                or rule.max_size is not None or rule.min_size is not None
            )
            if not bounded:
                if rule.action == "quarantine":
                    errors.append(f"junk.unbounded_quarantine_rule:{rule.id}")
                else:
                    warnings.append(f"junk.unbounded_rule:{rule.id}")
            if rule.min_size is not None and rule.max_size is not None and rule.min_size > rule.max_size:
                errors.append(f"junk.invalid_size_range:{rule.id}")
        if not payload.rules:
            errors.append("junk.empty_pack")
        return JunkRulePackValidation(
            valid=not errors,
            errors=sorted(set(errors)),
            warnings=sorted(set(warnings)),
            rule_count=len(payload.rules),
        )

    def write_junk_pack_payload(
        pack_id: str, version: int, payload: JunkRulePackWrite
    ) -> dict[str, Any]:
        value = JunkRulePack(
            id=pack_id,
            version=str(version),
            name=payload.name,
            description=payload.description,
            protected_extensions=payload.protected_extensions,
            protected_names=payload.protected_names,
            protected_paths=payload.protected_paths,
            rules=payload.rules,
            source="personal",
            read_only=False,
            current_version=version,
        )
        validation = validate_junk_pack(value)
        if not validation.valid:
            raise HTTPException(
                422, detail={"code": "junk.pack_invalid", "errors": validation.errors}
            )
        return value.model_dump(mode="json", exclude={"read_only", "current_version"})

    @app.get("/api/junk-rule-packs", response_model=list[JunkRulePack])
    def junk_rule_packs(session: Session = Depends(session_dependency)):
        values = [junk_pack_dict(DEFAULT_JUNK_PACK)]
        records = session.query(JunkRulePackRecord).order_by(JunkRulePackRecord.name).all()
        for record in records:
            version = session.query(JunkRulePackVersion).filter_by(
                pack_id=record.id, version=record.current_version
            ).one()
            values.append(personal_junk_pack(record, version))
        return values

    @app.post("/api/junk-rule-packs/validate", response_model=JunkRulePackValidation)
    def validate_junk_rule_pack(payload: JunkRulePack):
        return validate_junk_pack(payload)

    @app.post("/api/junk-rule-packs", response_model=JunkRulePack, status_code=201)
    def create_junk_rule_pack(
        payload: JunkRulePackWrite, session: Session = Depends(session_dependency)
    ):
        record = JunkRulePackRecord(name=payload.name, description=payload.description)
        session.add(record)
        session.flush()
        value = write_junk_pack_payload(record.id, 1, payload)
        version = JunkRulePackVersion(
            pack_id=record.id, version=1, payload=value, change_note=payload.change_note
        )
        session.add(version)
        session.commit()
        return personal_junk_pack(record, version)

    @app.get(
        "/api/junk-rule-packs/{pack_id}/versions",
        response_model=list[JunkRulePackVersionRead],
    )
    def list_junk_rule_pack_versions(
        pack_id: str, session: Session = Depends(session_dependency)
    ):
        if pack_id == DEFAULT_JUNK_PACK.id:
            return [{
                "pack_id": pack_id, "version": 1, "change_note": "Built-in version",
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            }]
        require(JunkRulePackRecord, pack_id, session)
        return session.query(JunkRulePackVersion).filter_by(pack_id=pack_id).order_by(
            JunkRulePackVersion.version.desc()
        ).all()

    @app.get("/api/junk-rule-packs/{pack_id}", response_model=JunkRulePack)
    def get_junk_rule_pack(
        pack_id: str,
        version: int | None = Query(default=None, ge=1),
        session: Session = Depends(session_dependency),
    ):
        return junk_pack_version(pack_id, version, session)

    @app.put("/api/junk-rule-packs/{pack_id}", response_model=JunkRulePack)
    def update_junk_rule_pack(
        pack_id: str,
        payload: JunkRulePackWrite,
        session: Session = Depends(session_dependency),
    ):
        if pack_id == DEFAULT_JUNK_PACK.id:
            raise HTTPException(400, detail="junk.builtin_read_only")
        record = require(JunkRulePackRecord, pack_id, session)
        next_version = record.current_version + 1
        value = write_junk_pack_payload(record.id, next_version, payload)
        record.name = payload.name
        record.description = payload.description
        record.current_version = next_version
        version = JunkRulePackVersion(
            pack_id=record.id,
            version=next_version,
            payload=value,
            change_note=payload.change_note,
        )
        session.add(version)
        session.commit()
        return personal_junk_pack(record, version)

    @app.post("/api/junk-rule-packs/{pack_id}/copy", response_model=JunkRulePack, status_code=201)
    def copy_junk_rule_pack(
        pack_id: str, session: Session = Depends(session_dependency)
    ):
        source = junk_pack_version(pack_id, None, session)
        payload = JunkRulePackWrite.model_validate({
            **source,
            "name": f"{source['name']} copy",
            "change_note": f"Copied from {pack_id}",
        })
        record = JunkRulePackRecord(name=payload.name, description=payload.description)
        session.add(record)
        session.flush()
        value = write_junk_pack_payload(record.id, 1, payload)
        version = JunkRulePackVersion(
            pack_id=record.id, version=1, payload=value, change_note=payload.change_note
        )
        session.add(version)
        session.commit()
        return personal_junk_pack(record, version)

    @app.delete("/api/junk-rule-packs/{pack_id}", status_code=204)
    def delete_junk_rule_pack(
        pack_id: str, session: Session = Depends(session_dependency)
    ):
        if pack_id == DEFAULT_JUNK_PACK.id:
            raise HTTPException(400, detail="junk.builtin_read_only")
        session.delete(require(JunkRulePackRecord, pack_id, session))
        session.commit()

    @app.post("/api/junk-rule-packs/{pack_id}/apply", response_model=WorkflowRead)
    def apply_junk_rule_pack(
        pack_id: str,
        payload: JunkRulePackApply,
        session: Session = Depends(session_dependency),
    ):
        snapshot = junk_pack_version(pack_id, payload.version, session)
        snapshot["source"] = "snapshot"
        snapshot["read_only"] = True
        workflow = require(Workflow, payload.workflow_id, session)
        revision = get_revision(session, workflow)
        template = template_from_revision(
            workflow.name, workflow.preset, workflow.review_policy, revision.config
        )
        detector: Any = None
        for stage in template.stages:
            for rule in stage.rules:
                for action in rule.actions:
                    if action.kind == "run_processor" and action.options.get("processor_id") == "detect_junk":
                        detector = action
                        break
        if detector is None:
            classify_stage = next(
                (item for item in template.stages if item.id == "classify"), None
            )
            if classify_stage is None:
                classify_stage = WorkflowStage(id="classify")
                template.stages.append(classify_stage)
            rule = RuleCard(
                id=f"classify.junk.{len(classify_stage.rules)}",
                name="Detect junk and advertisements",
                order=len(classify_stage.rules),
                actions=[WorkflowAction(kind="run_processor", options={"processor_id": "detect_junk"})],
            )
            classify_stage.rules.append(rule)
            detector = rule.actions[0]
        legacy_extensions = list(detector.options.get("extensions", []))
        legacy_keywords = list(detector.options.get("filename_contains", []))
        legacy_protected = list(detector.options.get("protected_extensions", []))
        snapshots = [
            item for item in detector.options.get("rule_packs", [])
            if isinstance(item, dict) and item.get("id") != pack_id
        ]
        legacy_id = f"workflow-legacy-{workflow.id}"
        if (legacy_extensions or legacy_keywords or legacy_protected) and not any(
            item.get("id") == legacy_id for item in snapshots
        ):
            legacy_rules: list[dict[str, Any]] = []
            if legacy_extensions:
                legacy_rules.append({
                    "id": "legacy.extensions", "name": "Migrated extensions",
                    "description": "Migrated from workflow processor options.",
                    "enabled": True, "order": 0, "action": "quarantine", "score": 70,
                    "extensions": legacy_extensions, "filename_contains": [],
                    "filename_regex": [], "path_contains": [], "max_size": None,
                    "min_size": None, "empty_only": False, "stop_on_match": False,
                })
            if legacy_keywords:
                legacy_rules.append({
                    "id": "legacy.keywords", "name": "Migrated keywords",
                    "description": "Migrated from workflow processor options.",
                    "enabled": True, "order": len(legacy_rules), "action": "quarantine",
                    "score": 55, "extensions": [], "filename_contains": legacy_keywords,
                    "filename_regex": [], "path_contains": [], "max_size": None,
                    "min_size": None, "empty_only": False, "stop_on_match": False,
                })
            snapshots.append({
                "id": legacy_id, "version": "1", "name": "Migrated workflow junk rules",
                "description": "Compatibility snapshot for legacy processor options.",
                "protected_extensions": legacy_protected,
                "protected_names": [], "protected_paths": [], "rules": legacy_rules,
                "source": "snapshot", "read_only": True, "current_version": 1,
            })
        detector.options["rule_packs"] = [*snapshots, snapshot]
        detector.options["rule_pack_refs"] = [
            {"id": item.get("id"), "version": item.get("version")}
            for item in detector.options["rule_packs"]
        ]
        target = next((item for item in template.stages if item.id == "target"), None)
        if target is None:
            target = WorkflowStage(id="target")
            template.stages.append(target)
        if not any(rule.id.startswith("target.junk") for rule in target.rules):
            target.rules.append(RuleCard(
                id=f"target.junk.{len(target.rules)}",
                name="Quarantine junk candidates",
                order=len(target.rules),
                conditions=ConditionGroup(conditions=[
                    Condition(field="junk_action", operator="equals", value="quarantine")
                ]),
                actions=[WorkflowAction(kind="quarantine"), WorkflowAction(kind="require_review")],
            ))
        workflow.current_revision += 1
        session.add(WorkflowRevision(
            workflow_id=workflow.id,
            revision=workflow.current_revision,
            config={
                "template": template.model_dump(mode="json"),
                "processors": [item.model_dump() for item in processors_from_template(template)],
            },
        ))
        stale_runs = select(PipelineRun.id).where(PipelineRun.workflow_id == workflow.id)
        session.query(Plan).filter(
            Plan.run_id.in_(stale_runs), Plan.status == "draft"
        ).update({"status": "invalidated"}, synchronize_session=False)
        session.commit()
        return workflow

    @app.get("/api/workflow-templates", response_model=list[WorkflowTemplateV2])
    def list_builtin_templates():
        return builtin_templates()

    @app.post("/api/workflow-templates/validate", response_model=TemplateValidationResult)
    def validate_workflow_template(payload: TemplateTextInput):
        try:
            value = parse_template_text(payload.content, payload.format)
        except ValueError as exc:
            return TemplateValidationResult(valid=False, errors=[str(exc)])
        return validate_template(value, registry, settings.version)

    @app.post("/api/workflow-templates/import", response_model=WorkflowRead, status_code=201)
    def import_workflow_template(
        payload: TemplateImportInput, session: Session = Depends(session_dependency)
    ):
        try:
            value = parse_template_text(payload.content, payload.format)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        validation = validate_template(value, registry, settings.version)
        if not validation.valid or not validation.template:
            raise HTTPException(422, detail={"code": "template.invalid", "errors": validation.errors})
        template = validation.template
        workflow = Workflow(
            name=template.name,
            preset=template.preset,
            review_policy=template.review_policy,
        )
        session.add(workflow)
        session.flush()
        processors = processors_from_template(template)
        session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                revision=1,
                config={
                    "template": template.model_dump(mode="json"),
                    "processors": [item.model_dump() for item in processors],
                },
            )
        )
        session.commit()
        return workflow

    @app.get("/api/workflow-templates/{workflow_id}/export", response_class=PlainTextResponse)
    def export_workflow_template(
        workflow_id: str,
        format: str = Query("yaml", pattern="^(yaml|json)$"),
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        revision = session.query(WorkflowRevision).filter_by(
            workflow_id=workflow.id, revision=workflow.current_revision
        ).one()
        template = template_from_revision(
            workflow.name, workflow.preset, workflow.review_policy, revision.config
        )
        return PlainTextResponse(
            dump_template(template, format),
            media_type="application/json" if format == "json" else "application/yaml",
        )

    @app.put("/api/workflow-templates/{workflow_id}", response_model=WorkflowRead)
    def update_workflow_template(
        workflow_id: str,
        payload: WorkflowTemplateUpdate,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        validation = validate_template(payload.template.model_dump(mode="json"), registry, settings.version)
        if not validation.valid or not validation.template:
            raise HTTPException(422, detail={"code": "template.invalid", "errors": validation.errors})
        template = validation.template
        workflow.current_revision += 1
        workflow.name = template.name
        workflow.preset = template.preset
        workflow.review_policy = template.review_policy
        processors = processors_from_template(template)
        session.add(WorkflowRevision(
            workflow_id=workflow.id,
            revision=workflow.current_revision,
            config={
                "template": template.model_dump(mode="json"),
                "processors": [item.model_dump() for item in processors],
            },
        ))
        stale_runs = select(PipelineRun.id).where(PipelineRun.workflow_id == workflow.id)
        session.query(Plan).filter(
            Plan.run_id.in_(stale_runs), Plan.status == "draft"
        ).update({"status": "invalidated"}, synchronize_session=False)
        session.commit()
        return workflow

    @app.post(
        "/api/workflow-templates/{workflow_id}/test-rule", response_model=RuleTestResult
    )
    def test_workflow_rule(
        workflow_id: str,
        payload: RuleTestInput,
        session: Session = Depends(session_dependency),
    ):
        require(Workflow, workflow_id, session)
        path = Path(payload.relative_path)
        context = ProcessingContext(
            entry_id="test",
            relative_path=payload.relative_path,
            original_name=path.name,
            parent_path=path.parent.as_posix() if path.parent != Path(".") else "",
            extension=path.suffix.lower(),
            size=payload.size,
            mtime_ns=payload.mtime_ns,
        )
        template = WorkflowTemplateV2(
            name="Rule test",
            stages=[
                WorkflowStage(id="clean", rules=[payload.rule])
            ],
        )
        trace = run_template_entry(template, context, registry)[0]
        return {
            "matched": trace.status != "skipped",
            "status": trace.status,
            "input": trace.input_data,
            "output": trace.output_data,
            "reasons": trace.reasons,
            "warnings": trace.warnings,
        }

    @app.post(
        "/api/workflow-templates/simulate", response_model=WorkflowSimulationResult
    )
    def simulate_workflow(payload: WorkflowSimulationInput):
        path = Path(payload.relative_path)
        context = ProcessingContext(
            entry_id="simulation",
            relative_path=payload.relative_path,
            original_name=path.name,
            parent_path=path.parent.as_posix() if path.parent != Path(".") else "",
            extension=path.suffix.lower(),
            size=payload.size,
            mtime_ns=payload.mtime_ns,
            fields=dict(payload.fields),
        )
        steps = run_template_entry(payload.template, context, registry)
        name = context.proposed_name or context.original_name
        parent = context.proposed_parent
        if parent is None:
            parent = context.parent_path
        proposed_path = (Path(parent) / name).as_posix() if parent else name
        operation_kind = context.fields.get("operation_kind")
        if operation_kind == "quarantine":
            action = "quarantine"
        elif proposed_path == payload.relative_path:
            action = "unchanged"
        elif parent == context.parent_path:
            action = "rename"
        elif operation_kind == "archive":
            action = "archive"
        else:
            action = "move"
        return {
            "original_path": payload.relative_path,
            "proposed_path": proposed_path,
            "action": action,
            "requires_review": any(step.status in {"review", "warning"} for step in steps),
            "fields": context.fields,
            "steps": [
                {
                    "rule_id": step.rule_id,
                    "status": step.status,
                    "input": step.input_data,
                    "output": step.output_data,
                    "reasons": step.reasons,
                    "warnings": step.warnings,
                }
                for step in steps
            ],
        }

    @app.post(
        "/api/workflow-templates/diagnostics", response_model=WorkflowDiagnosticsResult
    )
    def workflow_diagnostics(payload: WorkflowTemplateV2):
        diagnostics = diagnose_workflow(payload)
        errors = sum(item["severity"] == "error" for item in diagnostics)
        warnings = sum(item["severity"] == "warning" for item in diagnostics)
        return {
            "valid": errors == 0,
            "errors": errors,
            "warnings": warnings,
            "diagnostics": diagnostics,
        }

    @app.get("/api/workflows/{workflow_id}/dependencies", response_model=list[WorkflowDependency])
    def workflow_dependencies(
        workflow_id: str,
        source_id: str | None = None,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        template = template_from_revision(workflow.name, workflow.preset, workflow.review_policy, get_revision(session, workflow).config)
        enabled_actions = [
            action
            for stage in template.stages
            if stage.enabled
            for rule in stage.rules
            if rule.enabled
            for action in rule.actions
        ]
        actions = {action.kind for action in enabled_actions}
        dependencies: list[dict[str, Any]] = []
        archive_uses_dates = any(
            action.kind == "archive"
            and any(
                field in str(action.options.get("path_template", ""))
                for field in ("{year}", "{month}", "{day}")
            )
            for action in enabled_actions
        )
        if archive_uses_dates:
            dependencies.append({"feature": "archive_by_date", "requires": ["extract_dates"], "satisfied": "extract_dates" in actions, "message": "Date archive needs multi-date extraction."})
        render_uses_dates = any(
            action.kind == "render_name"
            and "{dates}" in str(action.options.get("name_template", ""))
            for action in enabled_actions
        )
        if render_uses_dates:
            dependencies.append({"feature": "render_dates", "requires": ["extract_dates"], "satisfied": "extract_dates" in actions, "message": "Name templates using dates need date extraction."})
        if "remove_number_patterns" in actions:
            dependencies.append({"feature": "number_cleanup", "requires": ["extract_dates", "extract_identifier", "extract_sequence"], "satisfied": any(value in actions for value in ("extract_dates", "extract_identifier", "extract_sequence")), "message": "Number cleanup needs protected metadata first."})

        requirements = scan_requirements(template)
        hash_required = requirements["hash_contents"]
        text_required = requirements["inspect_small_text"]
        hash_ready = text_ready = False
        if source_id:
            require(Source, source_id, session)
            completed_scans = session.query(ScanJob).filter_by(
                source_id=source_id, status="completed"
            )
            hash_ready = completed_scans.filter(ScanJob.hash_contents.is_(True)).first() is not None
            text_ready = completed_scans.filter(ScanJob.inspect_small_text.is_(True)).first() is not None
        if hash_required:
            dependencies.append({"feature": "hash_duplicate_detection", "requires": ["hash_contents_scan"], "satisfied": hash_ready, "message": "Run a content-hash scan before hash duplicate evidence is available."})
        if text_required:
            dependencies.append({"feature": "small_text_detection", "requires": ["inspect_small_text_scan"], "satisfied": text_ready, "message": "Run small-text inspection before text signals are available."})
        return dependencies

    @app.post("/api/sources", response_model=SourceRead, status_code=201)
    def create_source(payload: SourceCreate, session: Session = Depends(session_dependency)):
        root = normalize_root(payload.root_path)
        if settings.source_roots and not any(
            root == allowed.resolve() or root.is_relative_to(allowed.resolve())
            for allowed in settings.source_roots
        ):
            raise HTTPException(400, detail="source.outside_allowed_roots")
        if session.query(Source).filter_by(root_path=str(root)).one_or_none():
            raise HTTPException(409, detail="source.already_exists")
        source = Source(
            name=payload.name,
            root_path=str(root),
            read_only=payload.read_only,
            exclusions=payload.exclusions,
            protected_paths=payload.protected_paths,
            capabilities=probe_capabilities(root, payload.read_only),
        )
        session.add(source)
        session.commit()
        return source

    @app.get("/api/sources", response_model=list[SourceRead])
    def list_sources(session: Session = Depends(session_dependency)):
        return session.query(Source).order_by(Source.name).all()

    @app.get("/api/sources/{source_id}", response_model=SourceRead)
    def get_source(source_id: str, session: Session = Depends(session_dependency)):
        return require(Source, source_id, session)

    @app.patch("/api/sources/{source_id}", response_model=SourceRead)
    def update_source(
        source_id: str, payload: SourceUpdate, session: Session = Depends(session_dependency)
    ):
        source = require(Source, source_id, session)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(source, key, value)
        source.capabilities = probe_capabilities(Path(source.root_path), source.read_only)
        session.commit()
        return source

    @app.delete("/api/sources/{source_id}", status_code=204)
    def delete_source(source_id: str, session: Session = Depends(session_dependency)):
        source = require(Source, source_id, session)
        session.delete(source)
        session.commit()

    @app.post("/api/scans", response_model=ScanRead, status_code=201)
    def create_scan(payload: ScanCreate, session: Session = Depends(session_dependency)):
        source = require(Source, payload.source_id, session)
        job = ScanJob(
            source_id=source.id,
            mode=payload.mode,
            hash_contents=payload.hash_contents,
            inspect_small_text=payload.inspect_small_text,
            status="queued",
        )
        session.add(job)
        session.commit()
        return job

    @app.get("/api/scans", response_model=list[ScanRead])
    def list_scans(session: Session = Depends(session_dependency)):
        return session.query(ScanJob).order_by(ScanJob.created_at.desc()).all()

    @app.get("/api/scans/{scan_id}", response_model=ScanRead)
    def get_scan(scan_id: str, session: Session = Depends(session_dependency)):
        return require(ScanJob, scan_id, session)

    @app.post("/api/scans/{scan_id}/pause", response_model=ScanRead)
    def pause_scan(scan_id: str, session: Session = Depends(session_dependency)):
        job = require(ScanJob, scan_id, session)
        if job.status not in {"queued", "running"}:
            raise HTTPException(409, detail="scan.not_pauseable")
        job.status = "paused" if job.status == "queued" else "pause_requested"
        session.commit()
        return job

    @app.post("/api/scans/{scan_id}/cancel", response_model=ScanRead)
    def cancel_scan(scan_id: str, session: Session = Depends(session_dependency)):
        job = require(ScanJob, scan_id, session)
        if job.status not in {"queued", "running", "paused", "pause_requested"}:
            raise HTTPException(409, detail="scan.not_cancellable")
        job.status = (
            "cancel_requested" if job.status in {"running", "pause_requested"} else "cancelled"
        )
        session.commit()
        return job

    @app.post("/api/scans/{scan_id}/retry", response_model=ScanRead)
    def retry_scan(scan_id: str, session: Session = Depends(session_dependency)):
        job = require(ScanJob, scan_id, session)
        if job.status not in {"failed", "partial", "paused", "cancelled"}:
            raise HTTPException(409, detail="scan.not_retryable")
        job.status = "queued"
        job.completed_at = None
        session.commit()
        return job

    @app.get("/api/files", response_model=list[FileRead])
    def list_files(
        source_id: str,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: Session = Depends(session_dependency),
    ):
        return (
            session.query(FileEntry)
            .filter_by(source_id=source_id, active=True)
            .order_by(FileEntry.relative_path)
            .offset(offset)
            .limit(limit)
            .all()
        )

    @app.get("/api/files/page", response_model=FilePage)
    def page_files(
        source_id: str,
        search: str | None = None,
        extension: str | None = None,
        min_size: int | None = Query(default=None, ge=0),
        max_size: int | None = Query(default=None, ge=0),
        include_directories: bool = False,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: Session = Depends(session_dependency),
    ):
        require(Source, source_id, session)
        query = session.query(FileEntry).filter_by(source_id=source_id, active=True)
        if not include_directories:
            query = query.filter_by(is_dir=False)
        if search:
            query = query.filter(FileEntry.relative_path.ilike(f"%{search}%"))
        if extension:
            normalized_extension = extension if extension.startswith(".") else f".{extension}"
            query = query.filter(func.lower(FileEntry.extension) == normalized_extension.lower())
        if min_size is not None:
            query = query.filter(FileEntry.size >= min_size)
        if max_size is not None:
            query = query.filter(FileEntry.size <= max_size)
        total = query.count()
        items = query.order_by(FileEntry.relative_path).offset(offset).limit(limit).all()
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/file-groups", response_model=list[FileGroupRead])
    def list_file_groups(
        source_id: str,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: Session = Depends(session_dependency),
    ):
        require(Source, source_id, session)
        return (
            session.query(FileGroup)
            .filter_by(source_id=source_id)
            .order_by(FileGroup.group_key)
            .offset(offset)
            .limit(limit)
            .all()
        )

    @app.post("/api/workflows", response_model=WorkflowRead, status_code=201)
    def create_workflow(payload: WorkflowCreate, session: Session = Depends(session_dependency)):
        workflow = Workflow(
            name=payload.name, preset=payload.preset, review_policy=payload.review_policy
        )
        session.add(workflow)
        session.flush()
        processors_config = payload.processors or DEFAULT_PROCESSORS
        revision = WorkflowRevision(
            workflow_id=workflow.id,
            revision=1,
            config={"processors": [item.model_dump() for item in processors_config]},
        )
        session.add(revision)
        session.commit()
        return workflow

    @app.get("/api/workflows", response_model=list[WorkflowRead])
    def list_workflows(session: Session = Depends(session_dependency)):
        return session.query(Workflow).order_by(Workflow.name).all()

    @app.get(
        "/api/workflows/{workflow_id}/revisions",
        response_model=list[WorkflowRevisionRead],
    )
    def list_workflow_revisions(
        workflow_id: str, session: Session = Depends(session_dependency)
    ):
        require(Workflow, workflow_id, session)
        return (
            session.query(WorkflowRevision)
            .filter_by(workflow_id=workflow_id)
            .order_by(WorkflowRevision.revision.desc())
            .all()
        )

    @app.get("/api/workflows/{workflow_id}/export", response_model=WorkflowPortable)
    def export_workflow(workflow_id: str, session: Session = Depends(session_dependency)):
        workflow = require(Workflow, workflow_id, session)
        revision = (
            session.query(WorkflowRevision)
            .filter_by(workflow_id=workflow.id, revision=workflow.current_revision)
            .one()
        )
        return {
            "schema_version": 1,
            "name": workflow.name,
            "preset": workflow.preset,
            "review_policy": workflow.review_policy,
            "processors": revision.config.get("processors", []),
        }

    @app.post("/api/workflows/import", response_model=WorkflowRead, status_code=201)
    def import_workflow(payload: WorkflowPortable, session: Session = Depends(session_dependency)):
        registry.validate_order([item.id for item in payload.processors if item.enabled])
        workflow = Workflow(
            name=payload.name,
            preset=payload.preset,
            review_policy=payload.review_policy,
        )
        session.add(workflow)
        session.flush()
        session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                revision=1,
                config={"processors": [item.model_dump() for item in payload.processors]},
            )
        )
        session.commit()
        return workflow

    @app.get("/api/workflows/{workflow_id}/compare", response_model=WorkflowCompare)
    def compare_workflow_revisions(
        workflow_id: str,
        from_revision: int = Query(ge=1),
        to_revision: int = Query(ge=1),
        session: Session = Depends(session_dependency),
    ):
        require(Workflow, workflow_id, session)
        revisions = (
            session.query(WorkflowRevision)
            .filter(
                WorkflowRevision.workflow_id == workflow_id,
                WorkflowRevision.revision.in_([from_revision, to_revision]),
            )
            .all()
        )
        by_number = {revision.revision: revision for revision in revisions}
        if from_revision not in by_number or to_revision not in by_number:
            raise HTTPException(404, detail="workflow.revision_not_found")
        def comparable_items(item: WorkflowRevision) -> dict[str, Any]:
            template_data = item.config.get("template")
            if not isinstance(template_data, dict):
                return {
                    processor["id"]: processor
                    for processor in item.config.get("processors", [])
                }
            values: dict[str, Any] = {
                "settings:scope": template_data.get("scope", {}),
                "settings:association": template_data.get("association_policy", {}),
                "settings:impact_threshold": template_data.get("impact_threshold", {}),
                "settings:conflict_policy": template_data.get("conflict_policy"),
                "settings:review_policy": template_data.get("review_policy"),
            }
            for stage in template_data.get("stages", []):
                values[f"stage:{stage.get('id')}"] = {
                    "enabled": stage.get("enabled", True)
                }
                for rule in stage.get("rules", []):
                    values[f"rule:{stage.get('id')}:{rule.get('id')}"] = rule
            return values

        before = comparable_items(by_number[from_revision])
        after = comparable_items(by_number[to_revision])
        before_ids, after_ids = set(before), set(after)
        shared = before_ids & after_ids
        return {
            "workflow_id": workflow_id,
            "from_revision": from_revision,
            "to_revision": to_revision,
            "added": sorted(after_ids - before_ids),
            "removed": sorted(before_ids - after_ids),
            "changed": sorted(identifier for identifier in shared if before[identifier] != after[identifier]),
            "unchanged": sorted(identifier for identifier in shared if before[identifier] == after[identifier]),
        }

    @app.post("/api/workflows/{workflow_id}/restore/{revision}", response_model=WorkflowRead)
    def restore_workflow_revision(
        workflow_id: str,
        revision: int,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        selected = session.query(WorkflowRevision).filter_by(
            workflow_id=workflow.id, revision=revision
        ).one_or_none()
        if selected is None:
            raise DomainError("workflow.revision_not_found", 404)
        restored = template_from_revision(
            workflow.name, workflow.preset, workflow.review_policy, selected.config
        )
        workflow.current_revision += 1
        workflow.name = restored.name
        workflow.preset = restored.preset
        workflow.review_policy = restored.review_policy
        session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                revision=workflow.current_revision,
                config=deepcopy(selected.config),
            )
        )
        stale_runs = select(PipelineRun.id).where(PipelineRun.workflow_id == workflow.id)
        session.query(Plan).filter(
            Plan.run_id.in_(stale_runs), Plan.status == "draft"
        ).update({"status": "invalidated"}, synchronize_session=False)
        session.commit()
        return workflow

    @app.post("/api/workflows/{workflow_id}/impact", response_model=WorkflowImpactSummary)
    def workflow_impact(
        workflow_id: str,
        source_id: str,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        source = require(Source, source_id, session)
        run = run_pipeline(session, source, workflow, registry)
        plan = create_plan_from_pipeline(session, run)
        kinds = [operation.kind for operation in plan.operations]
        archive = 0
        for operation in plan.operations:
            if any(reason == "action.archive" for reason in operation.reasons):
                archive += 1
        total = int(run.summary.get("files", 0))
        conflicts = 0
        try:
            preflight_plan(session, plan)
        except (DomainError, FileSafetyError):
            conflicts = 1
        return {
            "workflow_id": workflow_id,
            "source_id": source_id,
            "total": total,
            "rename": kinds.count("rename"),
            "move": kinds.count("move") - archive,
            "archive": archive,
            "quarantine": kinds.count("quarantine"),
            "unchanged": max(0, total - len(plan.operations)),
            "conflicts": conflicts,
            "review": int(plan.summary.get("unresolved_review_count", 0)),
        }

    @app.post("/api/workflows/{workflow_id}/revisions", response_model=WorkflowRead)
    def revise_workflow(
        workflow_id: str,
        payload: WorkflowRevisionCreate,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        stale_runs = select(PipelineRun.id).where(PipelineRun.workflow_id == workflow.id)
        session.query(Plan).filter(
            Plan.run_id.in_(stale_runs), Plan.status == "draft"
        ).update({"status": "invalidated"}, synchronize_session=False)
        workflow.current_revision += 1
        if payload.review_policy:
            workflow.review_policy = payload.review_policy
        session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                revision=workflow.current_revision,
                config={"processors": [item.model_dump() for item in payload.processors]},
            )
        )
        session.commit()
        return workflow

    @app.post("/api/pipeline-runs", response_model=PipelineRunRead, status_code=201)
    def create_pipeline_run(
        payload: PipelineRunCreate, session: Session = Depends(session_dependency)
    ):
        source = require(Source, payload.source_id, session)
        workflow = require(Workflow, payload.workflow_id, session)
        return run_pipeline(session, source, workflow, registry)

    @app.get("/api/pipeline-runs", response_model=list[PipelineRunRead])
    def list_pipeline_runs(session: Session = Depends(session_dependency)):
        return session.query(PipelineRun).order_by(PipelineRun.created_at.desc()).all()

    @app.get("/api/pipeline-runs/{run_id}/trace", response_model=list[StageResultRead])
    def pipeline_trace(
        run_id: str,
        file_entry_id: str | None = None,
        session: Session = Depends(session_dependency),
    ):
        query = session.query(StageResult).filter_by(run_id=run_id)
        if file_entry_id:
            query = query.filter_by(file_entry_id=file_entry_id)
        return query.order_by(StageResult.created_at).all()

    @app.get("/api/reviews", response_model=list[ReviewItemRead])
    def reviews(
        run_id: str | None = None,
        limit: int = Query(200, ge=1, le=1000),
        session: Session = Depends(session_dependency),
    ):
        query = session.query(StageResult).filter(StageResult.status.in_(["review", "warning"]))
        if run_id:
            query = query.filter_by(run_id=run_id)
        flagged = query.order_by(StageResult.created_at.desc()).all()
        keys: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for result in flagged:
            key = (result.run_id, result.file_entry_id)
            if key not in seen:
                keys.append(key)
                seen.add(key)
            if len(keys) >= limit:
                break
        items: list[dict[str, Any]] = []
        for item_run_id, file_entry_id in keys:
            entry = session.get(FileEntry, file_entry_id)
            if not entry:
                continue
            results = (
                session.query(StageResult)
                .filter_by(run_id=item_run_id, file_entry_id=file_entry_id)
                .order_by(StageResult.created_at)
                .all()
            )
            latest = results[-1]
            proposed_name = latest.output_data.get("proposed_name") or entry.name
            proposed_parent = latest.output_data.get("proposed_parent")
            if proposed_parent is None:
                proposed_parent = entry.parent_path
            proposed_path = (
                (Path(proposed_parent) / proposed_name).as_posix()
                if proposed_parent
                else proposed_name
            )
            decision = (
                session.query(ReviewDecision)
                .filter_by(run_id=item_run_id, file_entry_id=file_entry_id)
                .one_or_none()
            )
            items.append(
                {
                    "run_id": item_run_id,
                    "file_entry_id": file_entry_id,
                    "relative_path": entry.relative_path,
                    "proposed_relative_path": proposed_path,
                    "confidence": latest.confidence,
                    "reasons": [reason for result in results for reason in result.reasons],
                    "warnings": [warning for result in results for warning in result.warnings],
                    "processors": [result.processor_id for result in results],
                    "decision": decision,
                }
            )
        return items

    @app.put(
        "/api/reviews/{run_id}/{file_entry_id}",
        response_model=ReviewDecisionRead,
    )
    def decide_review(
        run_id: str,
        file_entry_id: str,
        payload: ReviewDecisionUpsert,
        session: Session = Depends(session_dependency),
    ):
        run = require(PipelineRun, run_id, session)
        entry = require(FileEntry, file_entry_id, session)
        if entry.source_id != run.source_id:
            raise HTTPException(400, detail="review.file_outside_run_source")
        flagged = (
            session.query(StageResult)
            .filter_by(run_id=run_id, file_entry_id=file_entry_id)
            .filter(StageResult.status.in_(["review", "warning"]))
            .first()
        )
        if not flagged:
            raise HTTPException(409, detail="review.not_required")
        decision = (
            session.query(ReviewDecision)
            .filter_by(run_id=run_id, file_entry_id=file_entry_id)
            .one_or_none()
        )
        if decision is None:
            decision = ReviewDecision(run_id=run_id, file_entry_id=file_entry_id, action="keep")
            session.add(decision)
        decision.action = payload.action
        decision.target_relative_path = payload.target_relative_path
        decision.note = payload.note
        session.commit()
        return decision

    @app.post("/api/plans", response_model=PlanRead, status_code=201)
    def create_plan(payload: PlanCreate, session: Session = Depends(session_dependency)):
        run = require(PipelineRun, payload.run_id, session)
        return create_plan_from_pipeline(session, run)

    @app.post("/api/plans/manual", response_model=PlanRead, status_code=201)
    def manual_plan(payload: ManualPlanCreate, session: Session = Depends(session_dependency)):
        return create_manual_plan(session, payload)

    @app.get("/api/plans", response_model=list[PlanRead])
    def list_plans(session: Session = Depends(session_dependency)):
        return session.query(Plan).order_by(Plan.created_at.desc()).all()

    @app.post("/api/plans/{plan_id}/freeze", response_model=PlanRead)
    def freeze(plan_id: str, session: Session = Depends(session_dependency)):
        return freeze_plan(session, require(Plan, plan_id, session))

    @app.get("/api/plans/{plan_id}/preflight", response_model=PreflightRead)
    def preflight(plan_id: str, session: Session = Depends(session_dependency)):
        return preflight_plan(session, require(Plan, plan_id, session))

    @app.post("/api/plans/{plan_id}/confirm", response_model=PlanRead)
    def confirm(plan_id: str, session: Session = Depends(session_dependency)):
        return confirm_plan(session, require(Plan, plan_id, session))

    @app.post("/api/batches", response_model=BatchRead, status_code=201)
    def create_batch(plan_id: str, session: Session = Depends(session_dependency)):
        return queue_plan_execution(session, require(Plan, plan_id, session))

    @app.get("/api/batches", response_model=list[BatchRead])
    def list_batches(session: Session = Depends(session_dependency)):
        return session.query(ExecutionBatch).order_by(ExecutionBatch.created_at.desc()).all()

    @app.get("/api/batches/{batch_id}", response_model=BatchRead)
    def get_batch(batch_id: str, session: Session = Depends(session_dependency)):
        return require(ExecutionBatch, batch_id, session)

    @app.post("/api/batches/{batch_id}/pause", response_model=BatchRead)
    def pause_batch(batch_id: str, session: Session = Depends(session_dependency)):
        batch = require(ExecutionBatch, batch_id, session)
        if batch.status not in {"queued", "running"}:
            raise HTTPException(409, detail="batch.not_pauseable")
        batch.status = "paused" if batch.status == "queued" else "pause_requested"
        session.commit()
        return batch

    @app.post("/api/batches/{batch_id}/cancel", response_model=BatchRead)
    def cancel_batch(batch_id: str, session: Session = Depends(session_dependency)):
        batch = require(ExecutionBatch, batch_id, session)
        if batch.status not in {"queued", "running", "paused", "pause_requested"}:
            raise HTTPException(409, detail="batch.not_cancellable")
        batch.status = (
            "cancel_requested" if batch.status in {"running", "pause_requested"} else "cancelled"
        )
        session.commit()
        return batch

    @app.post("/api/batches/{batch_id}/retry", response_model=BatchRead)
    def retry_batch(batch_id: str, session: Session = Depends(session_dependency)):
        batch = require(ExecutionBatch, batch_id, session)
        if batch.status not in {"failed", "paused", "cancelled"}:
            raise HTTPException(409, detail="batch.not_retryable")
        plan = require(Plan, batch.plan_id, session)
        batch.status = "queued"
        batch.failed = 0
        batch.error = None
        batch.completed_at = None
        plan.status = "queued"
        session.commit()
        return batch

    @app.post("/api/batches/{batch_id}/rollback", response_model=BatchRead)
    def rollback(batch_id: str, session: Session = Depends(session_dependency)):
        return rollback_batch(session, require(ExecutionBatch, batch_id, session))

    @app.get("/api/batches/{batch_id}/rollback-preview", response_model=RollbackPreview)
    def rollback_preview(batch_id: str, session: Session = Depends(session_dependency)):
        batch = require(ExecutionBatch, batch_id, session)
        plan = require(Plan, batch.plan_id, session)
        source = require(Source, plan.source_id, session)
        root = normalize_root(source.root_path)
        successful_ids = {
            log.operation_id
            for log in session.query(AuditLog)
            .filter_by(batch_id=batch.id, event="operation.executed", status="success")
            .all()
        }
        items: list[dict[str, Any]] = []
        for operation in reversed(plan.operations):
            if operation.id not in successful_ids:
                continue
            current_relative = operation.target_relative_path
            if operation.kind == "quarantine":
                current_relative = (
                    Path(settings.quarantine_name) / Path(operation.target_relative_path).name
                ).as_posix()
            current = resolve_inside(root, current_relative)
            original = resolve_inside(root, operation.source_relative_path)
            conflict = None
            if not current.exists():
                conflict = "rollback.current_missing"
            elif original.exists():
                conflict = "rollback.target_exists"
            items.append(
                {
                    "operation_id": operation.id,
                    "source_relative_path": current_relative,
                    "target_relative_path": operation.source_relative_path,
                    "ready": conflict is None,
                    "conflict": conflict,
                }
            )
        return {"batch_id": batch.id, "ready": all(item["ready"] for item in items), "operations": items}

    @app.get("/api/history", response_model=list[AuditRead])
    def history(
        limit: int = Query(200, ge=1, le=1000), session: Session = Depends(session_dependency)
    ):
        return session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()

    @app.post("/api/backups")
    def backup(session: Session = Depends(session_dependency)):
        path = create_backup(session, settings)
        return {"status": "completed", "filename": path.name}

    @app.get("/api/backups", response_model=list[BackupRead])
    def list_backups():
        directory = settings.config_dir / "backups"
        if not directory.exists():
            return []
        return [
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "created_at": datetime.fromtimestamp(path.stat().st_mtime, UTC),
            }
            for path in sorted(directory.glob("file-curator-*.db"), reverse=True)
            if path.is_file()
        ]

    @app.get("/api/backups/{filename}", response_class=FileResponse)
    def download_backup(filename: str):
        if Path(filename).name != filename:
            raise HTTPException(400, detail="backup.invalid_filename")
        path = settings.config_dir / "backups" / filename
        if not path.is_file():
            raise HTTPException(404, detail="backup.not_found")
        return FileResponse(path, filename=filename, media_type="application/vnd.sqlite3")

    @app.get("/api/diagnostics", response_model=DiagnosticsRead)
    def diagnostics(session: Session = Depends(session_dependency)):
        return {
            "version": settings.version,
            "worker_alive": worker.is_alive if settings.worker_enabled else False,
            "database": Path(database.engine.url.database or "memory").name,
            "config_writable": settings.config_dir.exists()
            and os.access(settings.config_dir, os.W_OK),
            "webhook_configured": bool(settings.webhook_url),
            "counts": {
                "sources": session.query(Source).count(),
                "files": session.query(FileEntry).filter_by(active=True).count(),
                "workflows": session.query(Workflow).count(),
                "plans": session.query(Plan).count(),
                "batches": session.query(ExecutionBatch).count(),
            },
        }

    @app.post("/api/schedules", response_model=ScheduleRead, status_code=201)
    def create_schedule(payload: ScheduleCreate, session: Session = Depends(session_dependency)):
        require(Source, payload.source_id, session)
        if payload.workflow_id:
            require(Workflow, payload.workflow_id, session)
        if payload.generate_preview and not payload.workflow_id:
            raise DomainError("schedule.workflow_required")
        schedule = Schedule(
            name=payload.name,
            source_id=payload.source_id,
            workflow_id=payload.workflow_id,
            generate_preview=payload.generate_preview,
            enabled=payload.enabled,
            interval_minutes=payload.interval_minutes,
            next_run_at=datetime.now(UTC) + timedelta(minutes=payload.interval_minutes),
        )
        session.add(schedule)
        session.commit()
        return schedule

    @app.get("/api/schedules", response_model=list[ScheduleRead])
    def list_schedules(session: Session = Depends(session_dependency)):
        return session.query(Schedule).order_by(Schedule.name).all()

    @app.patch("/api/schedules/{schedule_id}", response_model=ScheduleRead)
    def update_schedule(
        schedule_id: str,
        payload: ScheduleUpdate,
        session: Session = Depends(session_dependency),
    ):
        schedule = require(Schedule, schedule_id, session)
        if payload.workflow_id:
            require(Workflow, payload.workflow_id, session)
        next_workflow_id = (
            payload.workflow_id if "workflow_id" in payload.model_fields_set else schedule.workflow_id
        )
        next_generate_preview = (
            payload.generate_preview
            if payload.generate_preview is not None
            else schedule.generate_preview
        )
        if next_generate_preview and not next_workflow_id:
            raise DomainError("schedule.workflow_required")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(schedule, key, value)
        if payload.interval_minutes is not None:
            schedule.next_run_at = datetime.now(UTC) + timedelta(minutes=payload.interval_minutes)
        session.commit()
        return schedule

    @app.delete("/api/schedules/{schedule_id}", status_code=204)
    def delete_schedule(schedule_id: str, session: Session = Depends(session_dependency)):
        session.delete(require(Schedule, schedule_id, session))
        session.commit()

    @app.get("/api/duplicates", response_model=list[DuplicateCandidate])
    def duplicate_candidates(
        source_id: str,
        method: str = Query(
            "normalized_name_size", pattern="^(name_size|normalized_name_size|hash)$"
        ),
        session: Session = Depends(session_dependency),
    ):
        require(Source, source_id, session)
        groups: dict[str, list[FileEntry]] = {}
        entries = (
            session.query(FileEntry).filter_by(source_id=source_id, active=True, is_dir=False).all()
        )
        for entry in entries:
            if method == "hash":
                if not entry.content_hash:
                    continue
                key = entry.content_hash
            elif method == "name_size":
                key = f"{entry.name.casefold()}:{entry.size}"
            else:
                normalized = "".join(
                    character
                    for character in Path(entry.name).stem.casefold()
                    if character.isalnum()
                )
                key = f"{normalized}:{entry.size}"
            groups.setdefault(key, []).append(entry)
        return [
            {
                "key": key,
                "method": method,
                "members": [
                    {
                        "id": entry.id,
                        "relative_path": entry.relative_path,
                        "size": entry.size,
                        "content_hash": entry.content_hash,
                    }
                    for entry in members
                ],
            }
            for key, members in groups.items()
            if len(members) > 1
        ]

    if settings.serve_ui and settings.ui_dir.exists():
        assets = settings.ui_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            requested = settings.ui_dir / path
            if requested.is_file() and settings.ui_dir.resolve() in requested.resolve().parents:
                return FileResponse(requested)
            return FileResponse(settings.ui_dir / "index.html")

    return app


app = create_app()
