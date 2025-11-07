"""KPI helpers for FHOPS schedules."""

from __future__ import annotations

import pandas as pd

from fhops.scenario.contract import Problem

__all__ = ["compute_kpis"]


def compute_kpis(pb: Problem, assignments: pd.DataFrame) -> dict[str, float]:
    """Compute simple production KPIs from assignments."""
    sc = pb.scenario
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    remaining = {block.id: block.work_required for block in sc.blocks}

    total_prod = 0.0
    for _, row in assignments.sort_values(["day"]).iterrows():
        block_id = row["block_id"]
        production = min(rate.get((row["machine_id"], block_id), 0.0), remaining[block_id])
        remaining[block_id] = max(0.0, remaining[block_id] - production)
        total_prod += production

    completed_blocks = sum(1 for rem in remaining.values() if rem <= 1e-6)
    return {"total_production": total_prod, "completed_blocks": float(completed_blocks)}
