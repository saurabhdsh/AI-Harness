"""Cost estimation from executions — visible FinOps spend from invoke logs."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost import CostRecord
from app.models.execution import AgentExecution

# Demo-visible estimated rates (USD per 1K tokens) — labeled as estimates in UI.
# ~order of small commercial LLM pricing so FinOps moves when you invoke.
RATE_IN_PER_1K = 0.002   # $2.00 / 1M input
RATE_OUT_PER_1K = 0.008  # $8.00 / 1M output
MIN_INVOKE_USD = 0.0005  # floor so a successful invoke is never $0.00


def estimate_tokens_from_payload(payload: Any) -> tuple[int, int]:
    blob = json.dumps(payload if payload is not None else {}, default=str)
    out_tok = max(80, len(blob) // 4)
    in_tok = max(60, out_tok // 2)
    return in_tok, out_tok


def compute_cost_usd(token_input: int, token_output: int) -> float:
    cost = (token_input / 1000.0) * RATE_IN_PER_1K + (token_output / 1000.0) * RATE_OUT_PER_1K
    if token_input or token_output:
        return round(max(cost, MIN_INVOKE_USD), 6)
    return 0.0


def resolve_tokens(
    *,
    token_input: int | None,
    token_output: int | None,
    output_payload: Any,
) -> tuple[int, int, bool]:
    tin = int(token_input or 0)
    tout = int(token_output or 0)
    estimated = False
    if tin <= 0 and tout <= 0:
        tin, tout = estimate_tokens_from_payload(output_payload)
        estimated = True
    return tin, tout, estimated


async def repair_zero_cost_records(db: AsyncSession, tenant_id: UUID) -> int:
    """Backfill $0 cost rows from their linked execution output/tokens."""
    result = await db.execute(
        select(CostRecord).where(
            CostRecord.tenant_id == tenant_id,
            CostRecord.cost_usd == 0.0,
        )
    )
    rows = list(result.scalars().all())
    fixed = 0
    for row in rows:
        tin = int(row.token_input or 0)
        tout = int(row.token_output or 0)
        payload: Any = None
        if row.execution_id:
            exe = await db.get(AgentExecution, row.execution_id)
            if exe is not None:
                if not tin and not tout:
                    tin = int(exe.token_input or 0)
                    tout = int(exe.token_output or 0)
                payload = exe.response
        tin, tout, estimated = resolve_tokens(
            token_input=tin,
            token_output=tout,
            output_payload=payload if payload is not None else {"latency_ms": True},
        )
        # latency-only fallback when no payload
        if estimated and payload is None:
            tin, tout = 120, 200
        cost = compute_cost_usd(tin, tout)
        if cost <= 0:
            continue
        row.token_input = tin
        row.token_output = tout
        row.cost_usd = cost
        meta = dict(row.metadata_ or {})
        meta["rate_source"] = "placeholder"
        meta["repaired"] = True
        if estimated:
            meta["tokens_estimated"] = True
        meta["note"] = "Estimated rates — not provider invoices"
        row.metadata_ = meta
        fixed += 1
    if fixed:
        await db.flush()
    return fixed
