"""Onboarding: detect projects, create connections, discover agents, register."""

from __future__ import annotations

from typing import Any
from uuid import UUID
from urllib.parse import urljoin

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import get_connector, list_connector_types
from app.models.connection import PlatformConnection
from app.schemas.agent import AgentCreate
from app.schemas.onboarding import (
    OnboardingJobCreate,
    OnboardingJobResult,
    ProjectOnboardRequest,
)
from app.services import registry as agent_registry
from app.services.audit import record_audit
from app.services import project_ingest
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

        if job.auto_register:
            for item in discovered_dump:
                invoke_url = item.get("invoke_url")
                if not invoke_url and job.base_url and not str(job.base_url).startswith("connector://"):
                    invoke_url = urljoin(job.base_url.rstrip("/") + "/", "invoke")
                agent = await agent_registry.create_agent(
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
    else:
        raise ValueError("source must be path | upload | cloud")

    connector_type = (
        body.connector_type
        or (detection or {}).get("recommended_connector")
        or CONNECTOR_FOR_FRAMEWORK.get((detection or {}).get("primary") or "", "generic_rest")
    )

    # Local frameworks require a reachable base_url
    if connector_type in {"langgraph", "crewai", "generic_rest", "rest", "generic"} and not body.base_url:
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

    job = OnboardingJobCreate(
        name=body.name,
        connector_type=connector_type,
        base_url=body.base_url or "",
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


def supported_frameworks() -> dict[str, Any]:
    return {
        "connectors": list_connector_types(),
        "frameworks": sorted(set(CONNECTOR_FOR_FRAMEWORK.keys())),
        "mapping": CONNECTOR_FOR_FRAMEWORK,
    }
