"""Onboarding — smart detect (path/upload) + register jobs."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.deps import AuthUser, DbSession
from app.schemas.onboarding import (
    CatalogSyncRequest,
    CatalogSyncResult,
    CiRegisterRequest,
    CiRegisterResult,
    OnboardingJobCreate,
    OnboardingJobResult,
    PathDetectRequest,
    ProjectOnboardRequest,
)
from app.services import onboarding as onboarding_service
from app.services import project_ingest
from app.services.framework_detector import detect_framework_at_path

router = APIRouter()


@router.get("/frameworks")
async def list_frameworks(user: AuthUser) -> dict:
    return onboarding_service.supported_frameworks()


@router.post(
    "/ci/register",
    response_model=CiRegisterResult,
    status_code=status.HTTP_201_CREATED,
    summary="Post-deploy CI registration (upsert by external_id)",
)
async def ci_register(
    body: CiRegisterRequest,
    db: DbSession,
    user: AuthUser,
) -> CiRegisterResult:
    """Enterprise path: call from GitHub Actions / Azure DevOps / Jenkins after deploy."""
    try:
        return await onboarding_service.register_from_ci(
            db,
            tenant_id=user.tenant_id,
            body=body,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/catalog/sync",
    response_model=CatalogSyncResult,
    status_code=status.HTTP_201_CREATED,
    summary="Sync deployed agent catalog after release",
)
async def catalog_sync(
    body: CatalogSyncRequest,
    db: DbSession,
    user: AuthUser,
) -> CatalogSyncResult:
    """Discover and/or upsert agents from a running catalog base URL + optional manifest."""
    result = await onboarding_service.sync_catalog(
        db,
        tenant_id=user.tenant_id,
        body=body,
        actor_id=user.user_id,
        actor_email=user.email,
    )
    if result.status == "failed":
        raise HTTPException(status_code=400, detail=result.error or "Catalog sync failed")
    return result


@router.post("/detect/path")
async def detect_path(body: PathDetectRequest, user: AuthUser) -> dict:
    try:
        result = project_ingest.detect_path(body.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.to_dict()


@router.post("/detect/upload")
async def detect_upload(
    user: AuthUser,
    file: UploadFile = File(...),
) -> dict:
    content = await file.read()
    try:
        upload_id, project_root = project_ingest.save_upload_zip(
            str(user.tenant_id), file.filename or "project.zip", content
        )
        detection = detect_framework_at_path(project_root).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Upload analysis failed: {exc}") from exc

    detection["upload_id"] = upload_id
    detection["project_root"] = str(project_root)
    return detection


@router.post("/projects", response_model=OnboardingJobResult, status_code=status.HTTP_201_CREATED)
async def smart_project_onboard(
    body: ProjectOnboardRequest,
    db: DbSession,
    user: AuthUser,
) -> OnboardingJobResult:
    try:
        return await onboarding_service.run_smart_project_onboard(
            db,
            tenant_id=user.tenant_id,
            body=body,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, PermissionError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs", response_model=OnboardingJobResult, status_code=status.HTTP_201_CREATED)
async def create_onboarding_job(
    body: OnboardingJobCreate,
    db: DbSession,
    user: AuthUser,
) -> OnboardingJobResult:
    return await onboarding_service.run_onboarding_job(
        db,
        tenant_id=user.tenant_id,
        job=body,
        actor_id=user.user_id,
        actor_email=user.email,
    )
