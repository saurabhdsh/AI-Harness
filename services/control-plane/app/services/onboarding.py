"""Onboarding: detect projects, create connections, discover agents, register."""

from __future__ import annotations

from typing import Any
from uuid import UUID
from urllib.parse import urljoin

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import get_connector, list_connector_types
from app.models.connection import PlatformConnection
from app.schemas.agent import AgentCreate
from app.schemas.onboarding import (
    CatalogSyncRequest,
    CatalogSyncResult,
    CiRegisterRequest,
    CiRegisterResult,
    OnboardingJobCreate,
    OnboardingJobResult,
    ProjectOnboardRequest,
)
from app.services import project_ingest
from app.services import registry as agent_registry
from app.services.audit import record_audit
from app.services.framework_detector import CONNECTOR_FOR_FRAMEWORK


async def create_connection(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    name: str,
    connector_type: str,
    base_url: str,
    secret_ref: str | None = None,
    metadata: dict | None = None,
) -> PlatformConnection:
    connector = get_connector(connector_type, base_url=base_url or "", secret_ref=secret_ref)
    caps = await connector.get_capabilities()

    conn = PlatformConnection(
        tenant_id=tenant_id,
        name=name,
        connector_type=connector_type,
        base_url=(base_url or "").rstrip("/") or f"connector://{connector_type}",
        secret_ref=secret_ref,
        capabilities=caps.model_dump(),
        status="created",
        metadata_=metadata or {},
    )
    db.add(conn)
    await db.flush()
    return conn


async def validate_connection(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    connection_id: UUID,
) -> tuple[bool, dict, int | None, str | None]:
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.tenant_id != tenant_id:
        raise LookupError("Connection not found")

    connector = get_connector(
        conn.connector_type,
        base_url=conn.base_url if not conn.base_url.startswith("connector://") else "",
        secret_ref=conn.secret_ref,
    )
    try:
        await connector.authenticate()
        caps = await connector.get_capabilities()
        discovered = await connector.discover_agents()
        conn.capabilities = caps.model_dump()
        conn.status = "validated"
        conn.last_error = None
        await db.flush()
        return True, caps.model_dump(), len(discovered), None
    except Exception as exc:
        conn.status = "error"
        conn.last_error = str(exc)
        await db.flush()
        return False, conn.capabilities or {}, None, str(exc)


def _connector_base(url: str) -> str:
    if not url or url.startswith("connector://"):
        return ""
    return url


async def run_onboarding_job(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    job: OnboardingJobCreate,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
    detection: dict[str, Any] | None = None,
) -> OnboardingJobResult:
    meta = {
        **(job.metadata or {}),
        **({"project_root": job.project_root} if job.project_root else {}),
        **({"detected_framework": job.detected_framework} if job.detected_framework else {}),
    }
    conn = await create_connection(
        db,
        tenant_id=tenant_id,
        name=job.name,
        connector_type=job.connector_type,
        base_url=job.base_url or "",
        secret_ref=job.secret_ref,
        metadata=meta,
    )

    connector = get_connector(
        job.connector_type,
        base_url=_connector_base(job.base_url or ""),
        secret_ref=job.secret_ref,
    )

    registered_ids: list[UUID] = []
    discovered_dump: list[dict] = []

    try:
        await connector.authenticate()
        discovered = await connector.discover_agents()
        caps = await connector.get_capabilities()
        conn.capabilities = caps.model_dump()
        conn.status = "validated"
        discovered_dump = [d.model_dump() for d in discovered]

        # Manual cloud / single-agent registration when discovery empty but external_id given
        if not discovered_dump and job.external_id:
            invoke = None
            if job.base_url and not job.base_url.startswith("connector://"):
                invoke = urljoin(job.base_url.rstrip("/") + "/", "invoke")
            discovered_dump = [
                {
                    "external_id": job.external_id,
                    "name": job.name,
                    "framework": job.detected_framework or job.connector_type,
                    "invoke_url": invoke,
                    "metadata": {"manual": True, **meta},
                }
            ]

        # CI path may supply a single invoke_url override
        invoke_override = meta.get("invoke_url_override")
        if invoke_override and not discovered_dump and job.external_id:
            discovered_dump = [
                {
                    "external_id": job.external_id,
                    "name": job.name,
                    "framework": job.detected_framework or job.connector_type,
                    "invoke_url": invoke_override,
                    "metadata": {"source": meta.get("source") or "ci", **meta},
                }
            ]

        if job.auto_register:
            for item in discovered_dump:
                invoke_url = item.get("invoke_url") or invoke_override
                if not invoke_url and job.base_url and not str(job.base_url).startswith("connector://"):
                    invoke_url = urljoin(job.base_url.rstrip("/") + "/", "invoke")
                agent, _created = await agent_registry.upsert_agent_by_external_id(
                    db,
                    tenant_id=tenant_id,
                    data=AgentCreate(
                        name=str(item.get("name") or job.name),
                        platform=job.connector_type,
                        framework=str(item.get("framework") or job.detected_framework or job.connector_type),
                        external_id=str(item.get("external_id") or job.external_id or ""),
                        owner=job.owner,
                        team=job.team,
                        domain=job.domain,
                        environment=job.environment,
                        lifecycle_state="registered",
                        connection_id=conn.id,
                        invoke_url=invoke_url,
                        metadata={**(item.get("metadata") or {}), **meta},
                    ),
                    actor_id=actor_id,
                    actor_email=actor_email,
                )
                registered_ids.append(agent.id)

        await record_audit(
            db,
            tenant_id=tenant_id,
            action="onboarding.completed",
            resource_type="platform_connection",
            resource_id=str(conn.id),
            actor_id=actor_id,
            actor_email=actor_email,
            detail={
                "discovered": len(discovered_dump),
                "registered": len(registered_ids),
                "connector": job.connector_type,
            },
        )
        await db.flush()
        return OnboardingJobResult(
            connection_id=conn.id,
            discovered=discovered_dump,
            registered_agent_ids=registered_ids,
            status="completed",
            detection=detection,
        )
    except Exception as exc:
        conn.status = "error"
        conn.last_error = str(exc)
        await db.flush()
        await record_audit(
            db,
            tenant_id=tenant_id,
            action="onboarding.failed",
            resource_type="platform_connection",
            resource_id=str(conn.id),
            actor_id=actor_id,
            actor_email=actor_email,
            detail={"error": str(exc)},
        )
        return OnboardingJobResult(
            connection_id=conn.id,
            discovered=discovered_dump,
            registered_agent_ids=registered_ids,
            status="failed",
            error=str(exc),
            detection=detection,
        )


async def run_smart_project_onboard(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    body: ProjectOnboardRequest,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> OnboardingJobResult:
    detection: dict[str, Any] | None = None
    project_root: str | None = body.project_root

    if body.source == "path":
        if not body.project_root:
            raise ValueError("project_root is required for source=path")
        detection = project_ingest.detect_path(body.project_root).to_dict()
        project_root = detection["root"]
    elif body.source == "upload":
        if not body.upload_id:
            raise ValueError("upload_id is required for source=upload")
        detection = project_ingest.detect_upload(str(tenant_id), body.upload_id).to_dict()
        project_root = detection["root"]
    elif body.source == "cloud":
        detection = {
            "primary": body.connector_type,
            "recommended_connector": body.connector_type,
            "confidence": 1.0,
            "notes": ["Cloud connector selected explicitly by user"],
            "frameworks": [{"id": body.connector_type, "score": 1.0}] if body.connector_type else [],
        }
    elif body.source in {"ci", "catalog"}:
        # Enterprise path: Git-built, CI-deployed — onboard the *runtime*, not a local folder
        detection = {
            "primary": body.connector_type or "generic_rest",
            "recommended_connector": body.connector_type or "generic_rest",
            "confidence": 1.0,
            "notes": [
                "CI / catalog onboarding — agent was built from Git and registered after deploy.",
                "Harness connects to the deployed invoke URL; it does not clone the repo.",
            ],
            "frameworks": [
                {"id": body.connector_type or "generic_rest", "score": 1.0}
            ],
            "git_repo": body.git_repo,
            "git_ref": body.git_ref,
            "git_sha": body.git_sha,
        }
    else:
        raise ValueError("source must be path | upload | cloud | ci | catalog")

    connector_type = (
        body.connector_type
        or (detection or {}).get("recommended_connector")
        or CONNECTOR_FOR_FRAMEWORK.get((detection or {}).get("primary") or "", "generic_rest")
    )

    # Local frameworks require a reachable base_url (ci may use invoke_url alone)
    if (
        connector_type in {"langgraph", "crewai", "generic_rest", "rest", "generic"}
        and not body.base_url
        and not body.invoke_url
    ):
        raise ValueError(
            f"Detected connector '{connector_type}' requires base_url of the running agent HTTP service "
            "(example: http://127.0.0.1:8090). Start the project, then continue."
        )

    if connector_type in {"aws_bedrock", "azure_foundry"} and not (
        body.secret_ref or body.external_id or body.base_url
    ):
        raise ValueError(
            f"Cloud connector '{connector_type}' requires secret_ref and/or external_id "
            "(and endpoint for Azure Foundry). Harness will not invent cloud agents."
        )

    # Derive base_url from invoke_url when CI only provides the full invoke path
    base_url = body.base_url or ""
    if not base_url and body.invoke_url:
        base_url = body.invoke_url.rsplit("/", 1)[0]

    job = OnboardingJobCreate(
        name=body.name,
        connector_type=connector_type,
        base_url=base_url,
        secret_ref=body.secret_ref,
        auto_register=body.auto_register,
        owner=body.owner,
        team=body.team,
        domain=body.domain,
        environment=body.environment,
        metadata={
            **(body.metadata or {}),
            "source": body.source,
            "upload_id": body.upload_id,
            **({"git_repo": body.git_repo} if body.git_repo else {}),
            **({"git_ref": body.git_ref} if body.git_ref else {}),
            **({"git_sha": body.git_sha} if body.git_sha else {}),
            **({"invoke_url_override": body.invoke_url} if body.invoke_url else {}),
        },
        external_id=body.external_id,
        project_root=project_root,
        detected_framework=(detection or {}).get("primary"),
    )
    return await run_onboarding_job(
        db,
        tenant_id=tenant_id,
        job=job,
        actor_id=actor_id,
        actor_email=actor_email,
        detection=detection,
    )


def _git_meta_from_ci(body: CiRegisterRequest) -> dict[str, Any]:
    meta = {
        "source": "ci",
        **(body.metadata or {}),
    }
    for key in (
        "git_repo",
        "git_ref",
        "git_sha",
        "git_commit_url",
        "pipeline_id",
        "pipeline_url",
    ):
        val = getattr(body, key, None)
        if val:
            meta[key] = val
    return meta


async def _get_or_create_ci_connection(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    body: CiRegisterRequest,
) -> PlatformConnection | None:
    if not body.create_connection:
        return None
    base = (body.base_url or "").rstrip("/")
    if not base and body.invoke_url:
        base = body.invoke_url.rsplit("/", 1)[0]
    name = body.connection_name or f"ci-{body.external_id}"

    existing = await db.scalar(
        select(PlatformConnection).where(
            PlatformConnection.tenant_id == tenant_id,
            PlatformConnection.name == name,
        )
    )
    if existing:
        if base:
            existing.base_url = base
        existing.connector_type = body.connector_type
        if body.secret_ref is not None:
            existing.secret_ref = body.secret_ref
        meta = dict(existing.metadata_ or {})
        meta.update(_git_meta_from_ci(body))
        existing.metadata_ = meta
        existing.status = "validated"
        await db.flush()
        return existing

    return await create_connection(
        db,
        tenant_id=tenant_id,
        name=name,
        connector_type=body.connector_type,
        base_url=base or f"connector://{body.connector_type}",
        secret_ref=body.secret_ref,
        metadata=_git_meta_from_ci(body),
    )


async def register_from_ci(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    body: CiRegisterRequest,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> CiRegisterResult:
    """Idempotent post-deploy registration — preferred enterprise onboarding path."""
    conn = await _get_or_create_ci_connection(db, tenant_id=tenant_id, body=body)
    if conn:
        conn.status = "validated"
        await db.flush()

    agent, created = await agent_registry.upsert_agent_by_external_id(
        db,
        tenant_id=tenant_id,
        data=AgentCreate(
            name=body.name,
            platform=body.connector_type,
            framework=body.framework,
            external_id=body.external_id,
            owner=body.owner,
            team=body.team,
            domain=body.domain,
            environment=body.environment,
            lifecycle_state="registered",
            connection_id=conn.id if conn else None,
            invoke_url=body.invoke_url,
            description=body.description,
            metadata=_git_meta_from_ci(body),
        ),
        actor_id=actor_id,
        actor_email=actor_email,
    )
    await record_audit(
        db,
        tenant_id=tenant_id,
        action="onboarding.ci_register",
        resource_type="agent",
        resource_id=str(agent.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={
            "created": created,
            "external_id": body.external_id,
            "git_repo": body.git_repo,
            "git_sha": body.git_sha,
            "pipeline_id": body.pipeline_id,
        },
    )
    return CiRegisterResult(
        agent_id=agent.id,
        connection_id=conn.id if conn else None,
        created=created,
        external_id=body.external_id,
        invoke_url=body.invoke_url,
        status="registered",
    )


async def sync_catalog(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    body: CatalogSyncRequest,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> CatalogSyncResult:
    """Sync agents from a deployed catalog endpoint and/or an explicit agent list."""
    git_meta = {
        "source": "catalog",
        **(body.metadata or {}),
        **({"git_repo": body.git_repo} if body.git_repo else {}),
        **({"git_ref": body.git_ref} if body.git_ref else {}),
        **({"git_sha": body.git_sha} if body.git_sha else {}),
    }

    conn = await create_connection(
        db,
        tenant_id=tenant_id,
        name=body.name,
        connector_type=body.connector_type,
        base_url=body.base_url,
        secret_ref=body.secret_ref,
        metadata=git_meta,
    )

    discovered_dump: list[dict[str, Any]] = []
    registered: list[UUID] = []
    updated: list[UUID] = []

    try:
        connector = get_connector(
            body.connector_type,
            base_url=_connector_base(body.base_url),
            secret_ref=body.secret_ref,
        )
        if body.discover:
            await connector.authenticate()
            discovered = await connector.discover_agents()
            caps = await connector.get_capabilities()
            conn.capabilities = caps.model_dump()
            discovered_dump.extend(d.model_dump() for d in discovered)

        for entry in body.agents:
            invoke = entry.invoke_url
            if not invoke:
                invoke = urljoin(body.base_url.rstrip("/") + "/", f"agents/{entry.external_id}/invoke")
            discovered_dump.append(
                {
                    "external_id": entry.external_id,
                    "name": entry.name,
                    "framework": entry.framework or body.connector_type,
                    "invoke_url": invoke,
                    "domain": entry.domain or body.domain,
                    "description": entry.description,
                    "metadata": {**git_meta, **(entry.metadata or {})},
                }
            )

        # Deduplicate by external_id (explicit catalog wins over discover)
        by_ext: dict[str, dict] = {}
        for item in discovered_dump:
            ext = str(item.get("external_id") or "")
            if not ext:
                continue
            by_ext[ext] = item
        discovered_dump = list(by_ext.values()) if by_ext else discovered_dump

        for item in discovered_dump:
            invoke_url = item.get("invoke_url")
            if not invoke_url:
                invoke_url = urljoin(body.base_url.rstrip("/") + "/", "invoke")
            agent, created = await agent_registry.upsert_agent_by_external_id(
                db,
                tenant_id=tenant_id,
                data=AgentCreate(
                    name=str(item.get("name") or body.name),
                    platform=body.connector_type,
                    framework=str(item.get("framework") or body.connector_type),
                    external_id=str(item.get("external_id") or ""),
                    owner=body.owner,
                    team=body.team,
                    domain=item.get("domain") or body.domain,
                    environment=body.environment,
                    lifecycle_state="registered",
                    connection_id=conn.id,
                    invoke_url=invoke_url,
                    description=item.get("description"),
                    metadata={**git_meta, **(item.get("metadata") or {})},
                ),
                actor_id=actor_id,
                actor_email=actor_email,
            )
            if created:
                registered.append(agent.id)
            else:
                updated.append(agent.id)

        conn.status = "validated"
        await db.flush()
        await record_audit(
            db,
            tenant_id=tenant_id,
            action="onboarding.catalog_sync",
            resource_type="platform_connection",
            resource_id=str(conn.id),
            actor_id=actor_id,
            actor_email=actor_email,
            detail={
                "discovered": len(discovered_dump),
                "created": len(registered),
                "updated": len(updated),
                "git_repo": body.git_repo,
            },
        )
        return CatalogSyncResult(
            connection_id=conn.id,
            discovered=discovered_dump,
            registered_agent_ids=registered,
            updated_agent_ids=updated,
            status="completed",
        )
    except Exception as exc:  # noqa: BLE001
        conn.status = "error"
        conn.last_error = str(exc)
        await db.flush()
        return CatalogSyncResult(
            connection_id=conn.id,
            discovered=discovered_dump,
            registered_agent_ids=registered,
            updated_agent_ids=updated,
            status="failed",
            error=str(exc),
        )


def supported_frameworks() -> dict[str, Any]:
    return {
        "connectors": list_connector_types(),
        "frameworks": sorted(set(CONNECTOR_FOR_FRAMEWORK.keys())),
        "mapping": CONNECTOR_FOR_FRAMEWORK,
        "enterprise_sources": ["ci", "catalog"],
    }
