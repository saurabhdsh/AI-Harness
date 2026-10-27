"""Workflow Orchestration API."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.deps import AuthUser, DbSession
from app.models.workflow import WorkflowDefinition, WorkflowRun
from app.schemas.workflow import (
    WorkflowDefinitionOut,
    WorkflowRunOut,
    WorkflowSeedResult,
    WorkflowStartRequest,
    WorkflowStepOut,
)
from app.services.audit import record_audit
from app.workflows import service as wf_svc

router = APIRouter()


def _defn_out(d: WorkflowDefinition) -> WorkflowDefinitionOut:
    extra = wf_svc.enrich_definition(d)
    item = WorkflowDefinitionOut.model_validate(d)
    return item.model_copy(update=extra)


def _run_out(run: WorkflowRun) -> WorkflowRunOut:
    item = WorkflowRunOut.model_validate(run)
    steps = [WorkflowStepOut.model_validate(s) for s in (run.steps or [])]
    steps.sort(key=lambda s: s.seq)
    defn = run.definition
    return item.model_copy(
        update={
            "steps": steps,
            "definition_name": defn.name if defn else None,
            "definition_slug": defn.slug if defn else None,
            "definition_domain": defn.domain if defn else None,
        }
    )


async def _seed_if_empty(db: DbSession, tenant_id: UUID) -> None:
    count = await db.scalar(
        select(func.count())
        .select_from(WorkflowDefinition)
        .where(WorkflowDefinition.tenant_id == tenant_id)
    )
    if not count:
        await wf_svc.ensure_builtin_workflows(db, tenant_id)


@router.get("/definitions", response_model=list[WorkflowDefinitionOut])
async def list_definitions(
    db: DbSession,
    user: AuthUser,
    domain: str | None = None,
) -> list[WorkflowDefinitionOut]:
    await _seed_if_empty(db, user.tenant_id)
    q = select(WorkflowDefinition).where(
        WorkflowDefinition.tenant_id == user.tenant_id,
        WorkflowDefinition.is_active.is_(True),
    )
    if domain:
        q = q.where(WorkflowDefinition.domain == domain.upper())
    q = q.order_by(WorkflowDefinition.domain, WorkflowDefinition.name)
    rows = (await db.execute(q)).scalars().all()
    return [_defn_out(d) for d in rows]


@router.post("/seed", response_model=WorkflowSeedResult)
async def seed_workflows(db: DbSession, user: AuthUser) -> WorkflowSeedResult:
    created = await wf_svc.ensure_builtin_workflows(db, user.tenant_id)
    total = await db.scalar(
        select(func.count())
        .select_from(WorkflowDefinition)
        .where(WorkflowDefinition.tenant_id == user.tenant_id)
    )
    return WorkflowSeedResult(created=created, total=int(total or 0))


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionOut)
async def get_definition(
    definition_id: UUID, db: DbSession, user: AuthUser
) -> WorkflowDefinitionOut:
    d = await db.get(WorkflowDefinition, definition_id)
    if d is None or d.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return _defn_out(d)


@router.get("/runs", response_model=list[WorkflowRunOut])
async def list_runs(
    db: DbSession,
    user: AuthUser,
    limit: int = Query(40, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
) -> list[WorkflowRunOut]:
    q = (
        select(WorkflowRun)
        .where(WorkflowRun.tenant_id == user.tenant_id)
        .options(
            selectinload(WorkflowRun.steps),
            selectinload(WorkflowRun.definition),
        )
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        q = q.where(WorkflowRun.status == status_filter)
    rows = (await db.execute(q)).scalars().all()
    return [_run_out(r) for r in rows]


@router.get("/runs/{run_id}", response_model=WorkflowRunOut)
async def get_run(run_id: UUID, db: DbSession, user: AuthUser) -> WorkflowRunOut:
    try:
        run = await wf_svc._load_run(db, run_id, user.tenant_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _run_out(run)


@router.post("/runs", response_model=WorkflowRunOut, status_code=status.HTTP_201_CREATED)
async def start_workflow(
    body: WorkflowStartRequest,
    db: DbSession,
    user: AuthUser,
) -> WorkflowRunOut:
    await _seed_if_empty(db, user.tenant_id)
    definition: WorkflowDefinition | None = None
    if body.definition_id:
        definition = await db.get(WorkflowDefinition, body.definition_id)
    elif body.slug:
        definition = await db.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.tenant_id == user.tenant_id,
                WorkflowDefinition.slug == body.slug,
                WorkflowDefinition.is_active.is_(True),
            )
        )
    if definition is None or definition.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Workflow definition not found")

    try:
        run = await wf_svc.start_run(
            db,
            tenant_id=user.tenant_id,
            definition=definition,
            input_payload=body.input,
            agent_bindings=body.agent_bindings,
            name=body.name,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _run_out(run)


@router.post("/runs/{run_id}/cancel", response_model=WorkflowRunOut)
async def cancel_run(run_id: UUID, db: DbSession, user: AuthUser) -> WorkflowRunOut:
    try:
        run = await wf_svc._load_run(db, run_id, user.tenant_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if run.status in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Run already {run.status}")
    run.status = "cancelled"
    run.error = "Cancelled by user"
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="workflow.cancelled",
        resource_type="workflow_run",
        resource_id=str(run.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={},
    )
    return _run_out(await wf_svc._load_run(db, run.id, user.tenant_id))
