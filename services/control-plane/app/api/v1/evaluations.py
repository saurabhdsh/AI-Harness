"""Evaluation endpoints — multi-dimension quality lab."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AuthUser, DbSession
from app.schemas.evaluation import EvaluationCreate, EvaluationRunOut
from app.services import evaluation as evaluation_service

router = APIRouter()


@router.get("/dimensions")
async def list_dimensions(user: AuthUser) -> dict:
    return {"dimensions": evaluation_service.dimension_catalog()}


@router.get("", response_model=list[EvaluationRunOut])
async def list_evaluations(
    db: DbSession,
    user: AuthUser,
    agent_id: UUID | None = None,
    limit: int = 30,
) -> list[EvaluationRunOut]:
    runs = await evaluation_service.list_evaluations(
        db, tenant_id=user.tenant_id, agent_id=agent_id, limit=limit
    )
    return [EvaluationRunOut.model_validate(r) for r in runs]


@router.post("", response_model=EvaluationRunOut, status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    body: EvaluationCreate,
    db: DbSession,
    user: AuthUser,
) -> EvaluationRunOut:
    try:
        run = await evaluation_service.run_evaluation(
            db,
            tenant_id=user.tenant_id,
            data=body,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Evaluation failed: {exc}",
        ) from exc
    return EvaluationRunOut.model_validate(run)


@router.get("/{run_id}", response_model=EvaluationRunOut)
async def get_evaluation(run_id: UUID, db: DbSession, user: AuthUser) -> EvaluationRunOut:
    try:
        run = await evaluation_service.get_evaluation(
            db, tenant_id=user.tenant_id, run_id=run_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EvaluationRunOut.model_validate(run)
