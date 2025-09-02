from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator
import datetime as dt

Day = int  # 1..D

class Block(BaseModel):
    id: str
    landing_id: str
    work_required: float  # in 'work units' (e.g., machine-hours) to complete block
    earliest_start: Optional[Day] = 1
    latest_finish: Optional[Day] = None

    @field_validator("latest_finish")
    @classmethod
    def _lf_ge_es(cls, v, info):
        es = info.data.get("earliest_start", 1)
        if v is not None and v < es:
            raise ValueError("latest_finish must be >= earliest_start")
        return v

class Machine(BaseModel):
    id: str
    crew: Optional[str] = None
    daily_hours: float = 10.0
    operating_cost: float = 0.0

class Landing(BaseModel):
    id: str
    daily_capacity: int = 2  # max machines concurrently working

class CalendarEntry(BaseModel):
    machine_id: str
    day: Day
    available: int = 1  # 1 available, 0 not available

class ProductionRate(BaseModel):
    machine_id: str
    block_id: str
    rate: float  # work units per day if assigned (<= work_required/block)

class Scenario(BaseModel):
    name: str
    num_days: int
    start_date: Optional[dt.date] = None  # ISO date for reporting (optional)
    blocks: List[Block]
    machines: List[Machine]
    landings: List[Landing]
    calendar: List[CalendarEntry]
    production_rates: List[ProductionRate]

    def machine_ids(self) -> List[str]:
        return [m.id for m in self.machines]

    def block_ids(self) -> List[str]:
        return [b.id for b in self.blocks]

    def landing_ids(self) -> List[str]:
        return [l.id for l in self.landings]

    def window_for(self, b_id: str) -> Tuple[int, int]:
        b = next(b for b in self.blocks if b.id == b_id)
        es = b.earliest_start if b.earliest_start is not None else 1
        lf = b.latest_finish if b.latest_finish is not None else self.num_days
        return es, lf

class Problem(BaseModel):
    scenario: Scenario
    days: List[Day]

    @classmethod
    def from_scenario(cls, sc: Scenario) -> "Problem":
        return cls(scenario=sc, days=list(range(1, sc.num_days + 1)))
