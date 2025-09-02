from __future__ import annotations
import pandas as pd
from fhops.core.types import Problem

def compute_kpis(pb: Problem, assignments: pd.DataFrame) -> dict:
    sc = pb.scenario
    # expected production given assignments and rates (bounded by work_required)
    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    remaining = {b.id: b.work_required for b in sc.blocks}
    total_prod = 0.0
    for (_, row) in assignments.sort_values(["day"]).iterrows():
        r = rate.get((row["machine_id"], row["block_id"]), 0.0)
        b = row["block_id"]
        prod = min(r, remaining[b])
        remaining[b] = max(0.0, remaining[b] - prod)
        total_prod += prod
    completed_blocks = sum(1 for b, rem in remaining.items() if rem <= 1e-6)
    return {"total_production": total_prod, "completed_blocks": completed_blocks}
