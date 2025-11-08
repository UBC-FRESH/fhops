"""KPI helpers for FHOPS schedules."""

from __future__ import annotations

import pandas as pd

from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import build_distance_lookup

__all__ = ["compute_kpis"]


def compute_kpis(pb: Problem, assignments: pd.DataFrame) -> dict[str, float]:
    """Compute production and mobilisation KPIs from assignments."""

    sc = pb.scenario
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    remaining = {block.id: block.work_required for block in sc.blocks}

    mobilisation_cost = 0.0
    mobilisation = sc.mobilisation
    mobilisation_lookup = build_distance_lookup(mobilisation)
    mobil_params = (
        {param.machine_id: param for param in mobilisation.machine_params}
        if mobilisation is not None
        else {}
    )
    previous_block: dict[str, str | None] = {machine.id: None for machine in sc.machines}

    total_prod = 0.0
    for _, row in assignments.sort_values(["day", "machine_id"]).iterrows():
        block_id = row["block_id"]
        production = min(rate.get((row["machine_id"], block_id), 0.0), remaining[block_id])
        remaining[block_id] = max(0.0, remaining[block_id] - production)
        total_prod += production

        params = mobil_params.get(row["machine_id"])
        prev = previous_block.get(row["machine_id"])
        if params is not None and prev is not None and prev != block_id:
            distance = mobilisation_lookup.get((prev, block_id), 0.0)
            cost = params.setup_cost
            if distance <= params.walk_threshold_m:
                cost += params.walk_cost_per_meter * distance
            else:
                cost += params.move_cost_flat
            mobilisation_cost += cost
        previous_block[row["machine_id"]] = block_id

    completed_blocks = sum(1 for rem in remaining.values() if rem <= 1e-6)

    result: dict[str, float] = {
        "total_production": total_prod,
        "completed_blocks": float(completed_blocks),
    }
    if mobilisation is not None:
        result["mobilisation_cost"] = mobilisation_cost
    return result
