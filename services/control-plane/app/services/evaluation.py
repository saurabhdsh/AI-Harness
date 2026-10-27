"""Evaluation runner — real invoke + industry quality dimensions + custom assertions."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.evaluation import EvaluationResult, EvaluationRun
from app.schemas.evaluation import EvaluationCase, EvaluationCreate
from app.services import execution as execution_service
from app.services.audit import record_audit
from app.services.quality_dimensions import DIMENSION_CATALOG, evaluate_dimensions

# Critical safety dims — always must clear their thresholds when selected
_CRITICAL_DIMS = frozenset(
    {"toxicity", "bias", "pii_leakage", "security", "prompt_injection", "hallucination"}
)


def score_deterministic(
    actual: dict[str, Any] | None,
    expected: dict[str, Any] | None,
    match_mode: str = "contains",
) -> tuple[float, bool, dict[str, Any]]:
    if match_mode in {"none", "dimensions_only"}:
        return 1.0, True, {"mode": match_mode, "skipped": True}

    if expected is None:
        ok = bool(actual)
        return (1.0 if ok else 0.0), ok, {"mode": "presence"}

    if actual is None:
        return 0.0, False, {"mode": match_mode, "reason": "no_actual"}

    if match_mode == "exact":
        passed = actual == expected
        return (1.0 if passed else 0.0), passed, {"mode": "exact"}

    if match_mode == "keys":
        missing = [k for k in expected if k not in actual]
        passed = len(missing) == 0
        score = 1.0 - (len(missing) / max(len(expected), 1))
        return score, passed, {"mode": "keys", "missing": missing}

    actual_s = json.dumps(actual, sort_keys=True, default=str).lower()
    hits = 0
    checks: list[dict] = []
    for key, val in expected.items():
        if key in actual and actual[key] == val:
            hits += 1
            checks.append({"key": key, "hit": True, "via": "equality"})
        elif str(val).lower() in actual_s:
            hits += 1
            checks.append({"key": key, "hit": True, "via": "contains"})
        else:
            checks.append({"key": key, "hit": False})
    total = max(len(expected), 1)
    score = hits / total
    return score, score >= 1.0, {"mode": "contains", "checks": checks}


def run_custom_assertions(
    actual: dict[str, Any] | None,
    assertions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not assertions:
        return {"score": 1.0, "passed": True, "checks": [], "method": "n/a"}

    blob = json.dumps(actual or {}, default=str)
    checks: list[dict[str, Any]] = []
    hits = 0
    for i, assertion in enumerate(assertions):
        atype = str(assertion.get("type") or "contains")
        value = assertion.get("value")
        field = assertion.get("field")
        target = blob
        if field and isinstance(actual, dict):
            target = json.dumps(actual.get(field), default=str) if field in actual else ""
        ok = False
        detail = ""
        try:
            if atype == "contains":
                ok = str(value) in target
            elif atype == "not_contains":
                ok = str(value) not in target
            elif atype == "regex":
                ok = bool(re.search(str(value), target, re.I | re.S))
            elif atype == "json_equals":
                ok = actual is not None and actual.get(field) == value if field else actual == value
            elif atype == "min_length":
                ok = len(target) >= int(value)
            elif atype == "max_length":
                ok = len(target) <= int(value)
            else:
                detail = f"unknown_assertion_type:{atype}"
                ok = False
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail = str(exc)
        checks.append({"index": i, "type": atype, "passed": ok, "detail": detail, "value": value})
        if ok:
            hits += 1
    score = hits / max(len(assertions), 1)
    return {"score": score, "passed": score >= 1.0, "checks": checks, "method": "custom"}


async def optional_llm_judge(
    *,
    judge_url: str,
    case: EvaluationCase,
    actual: dict[str, Any] | None,
) -> tuple[float | None, str | None]:
    settings = get_settings()
    payload = {"input": case.input, "expected": case.expected, "actual": actual}
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            resp = await client.post(judge_url, json=payload)
        if resp.status_code >= 400:
            return None, f"LLM judge HTTP {resp.status_code}: {resp.text[:300]}"
        body = resp.json()
        return float(body.get("score", 0)), body.get("notes") or body.get("rationale")
    except Exception as exc:
        return None, f"LLM judge failed: {exc}"


async def run_evaluation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    data: EvaluationCreate,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> EvaluationRun:
    cases = list(data.cases)
    if not cases:
        # Prefer eval suites from attached enterprise skills
        from app.models.skill import AgentSkill, Skill

        skill_rows = (
            await db.execute(
                select(Skill)
                .join(AgentSkill, AgentSkill.skill_id == Skill.id)
                .where(
                    AgentSkill.tenant_id == tenant_id,
                    AgentSkill.agent_id == data.agent_id,
                    AgentSkill.is_active.is_(True),
                    Skill.is_active.is_(True),
                )
            )
        ).scalars().all()
        for skill in skill_rows:
            suite = skill.eval_suite or {}
            for i, raw in enumerate(suite.get("cases") or []):
                if not isinstance(raw, dict):
                    continue
                expect_contains = raw.get("expect_contains") or []
                expected = raw.get("expected")
                if expected is None and expect_contains:
                    expected = {f"contains_{j}": v for j, v in enumerate(expect_contains)}
                cases.append(
                    EvaluationCase(
                        case_id=str(raw.get("name") or f"{skill.slug}-{i}"),
                        input=raw.get("input") or skill.sample_input or {},
                        expected=expected,
                        match_mode=str(raw.get("match_mode") or "contains"),
                        label=f"{skill.name}: {raw.get('name') or i}",
                    )
                )
        if not cases:
            cases = [
                EvaluationCase(
                    case_id="quality-smoke",
                    input={"task": "analyze", "use_sample": True},
                    expected={"summary": "", "issues": []},
                    match_mode="keys",
                    label="Default AD smoke",
                )
            ]

    # Fill default thresholds from catalog
    thresholds = {d["id"]: float(d["default_threshold"]) for d in DIMENSION_CATALOG}
    thresholds.update(data.thresholds or {})

    suite_meta = {
        "cases": [c.model_dump() for c in cases],
        "dimensions": data.dimensions,
        "thresholds": thresholds,
        "pass_score": data.pass_score,
        "max_latency_ms": data.max_latency_ms,
        "required_keys": data.required_keys,
        "required_nodes": data.required_nodes,
        "use_llm_judge": data.use_llm_judge,
    }

    run = EvaluationRun(
        tenant_id=tenant_id,
        agent_id=data.agent_id,
        name=data.name,
        status="running",
        suite=suite_meta,
        use_llm_judge=data.use_llm_judge,
    )
    db.add(run)
    await db.flush()

    weighted_scores: list[tuple[float, float]] = []
    case_pass = 0
    try:
        for case in cases:
            # Retry transient agent timeouts / connection blips (common on first case)
            execution = None
            last_invoke_error: str | None = None
            for attempt in range(3):
                execution = await execution_service.invoke_agent(
                    db,
                    tenant_id=tenant_id,
                    agent_id=data.agent_id,
                    input_payload=case.input,
                    config={},
                    actor_id=actor_id,
                    actor_email=actor_email,
                )
                if execution.status == "succeeded":
                    break
                last_invoke_error = execution.error
                if attempt < 2:
                    await asyncio.sleep(1.2 * (attempt + 1))

            assert execution is not None
            actual = execution.response if execution.status == "succeeded" else None
            latency_ms = execution.latency_ms

            det_score, det_passed, det_metrics = score_deterministic(
                actual, case.expected, case.match_mode
            )
            assertion_metrics = run_custom_assertions(actual, case.assertions)

            case_dims = case.dimensions or data.dimensions
            case_thr = {**thresholds, **(case.thresholds or {})}
            dim_report = await evaluate_dimensions(
                dimensions=case_dims,
                thresholds=case_thr,
                input_payload=case.input,
                actual=actual,
                latency_ms=latency_ms,
                max_latency_ms=case.max_latency_ms
                if case.max_latency_ms is not None
                else data.max_latency_ms,
                required_keys=case.required_keys or data.required_keys,
                required_nodes=case.required_nodes or data.required_nodes,
                allow_pii=case.allow_pii,
                use_llm_judge=data.use_llm_judge,
            )

            judge_notes = dim_report.get("llm_note")
            if data.llm_judge_url and data.use_llm_judge:
                ext_score, ext_notes = await optional_llm_judge(
                    judge_url=data.llm_judge_url, case=case, actual=actual
                )
                if ext_score is None:
                    det_metrics["external_judge_error"] = ext_notes
                else:
                    det_metrics["external_judge_score"] = ext_score
                    judge_notes = (judge_notes or "") + f" | external: {ext_notes}"

            # Combine: 25% deterministic + 25% assertions + 50% dimensions
            parts = [
                ("deterministic", det_score, 0.25 if case.match_mode not in {"none", "dimensions_only"} else 0.0),
                ("assertions", float(assertion_metrics["score"]), 0.25 if case.assertions else 0.0),
                ("dimensions", float(dim_report["aggregate_score"]), 0.5),
            ]
            weight_sum = sum(w for _, _, w in parts if w > 0) or 1.0
            final_score = sum(s * w for _, s, w in parts if w > 0) / weight_sum

            dims_payload = dim_report.get("dimensions") or {}
            if data.strict_dimensions:
                dimensions_ok = bool(dim_report["passed"])
            else:
                # Soft gate: aggregate clears pass_score AND critical safety dims pass
                critical_fail = [
                    did
                    for did in case_dims
                    if did in _CRITICAL_DIMS
                    and did in dims_payload
                    and not dims_payload[did].get("passed")
                ]
                dimensions_ok = (
                    float(dim_report["aggregate_score"]) >= float(data.pass_score)
                    and not critical_fail
                )

            passed = (
                execution.status == "succeeded"
                and (det_passed or case.match_mode in {"none", "dimensions_only"})
                and bool(assertion_metrics["passed"])
                and dimensions_ok
                and final_score >= float(data.pass_score)
            )

            metrics: dict[str, Any] = {
                "deterministic": det_metrics,
                "assertions": assertion_metrics,
                "dimensions": dim_report["dimensions"],
                "dimension_aggregate": dim_report["aggregate_score"],
                "dimensions_all_passed": dim_report["passed"],
                "dimensions_gate_ok": dimensions_ok,
                "strict_dimensions": data.strict_dimensions,
                "latency_ms": latency_ms,
                "thresholds": case_thr,
                "pass_score": data.pass_score,
                "label": case.label,
            }
            if execution.status != "succeeded":
                final_score = 0.0
                passed = False
                metrics["invoke_error"] = execution.error or last_invoke_error

            result = EvaluationResult(
                tenant_id=tenant_id,
                run_id=run.id,
                case_id=case.case_id,
                input_payload=case.input,
                expected=case.expected,
                actual=actual,
                score=final_score,
                passed=passed,
                metrics=metrics,
                judge_notes=judge_notes,
            )
            db.add(result)
            weighted_scores.append((final_score, float(case.weight or 1.0)))
            if passed:
                case_pass += 1

        total_w = sum(w for _, w in weighted_scores) or 1.0
        aggregate = sum(s * w for s, w in weighted_scores) / total_w
        run.aggregate_score = aggregate
        run.status = "completed"
        run.summary = (
            f"{case_pass}/{len(weighted_scores)} cases passed · "
            f"aggregate {aggregate:.2f} (gate {data.pass_score})"
        )

        from app.models.agent import Agent

        agent = await db.get(Agent, data.agent_id)
        if agent and agent.tenant_id == tenant_id:
            agent.evaluation_status = "passed" if aggregate >= data.pass_score else "failed"
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        await db.flush()
        raise

    await record_audit(
        db,
        tenant_id=tenant_id,
        action="evaluation.completed",
        resource_type="evaluation_run",
        resource_id=str(run.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"aggregate_score": run.aggregate_score, "status": run.status},
    )
    await db.flush()

    stmt = (
        select(EvaluationRun)
        .where(EvaluationRun.id == run.id)
        .options(selectinload(EvaluationRun.results))
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_evaluation(
    db: AsyncSession, *, tenant_id: UUID, run_id: UUID
) -> EvaluationRun:
    stmt = (
        select(EvaluationRun)
        .where(EvaluationRun.id == run_id, EvaluationRun.tenant_id == tenant_id)
        .options(selectinload(EvaluationRun.results))
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if run is None:
        raise LookupError("Evaluation run not found")
    return run


async def list_evaluations(
    db: AsyncSession, *, tenant_id: UUID, agent_id: UUID | None = None, limit: int = 30
) -> list[EvaluationRun]:
    stmt = (
        select(EvaluationRun)
        .where(EvaluationRun.tenant_id == tenant_id)
        .order_by(EvaluationRun.created_at.desc())
        .limit(limit)
        .options(selectinload(EvaluationRun.results))
    )
    if agent_id:
        stmt = stmt.where(EvaluationRun.agent_id == agent_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


def dimension_catalog() -> list[dict[str, Any]]:
    return DIMENSION_CATALOG
