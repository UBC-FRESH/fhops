"""Build a synthetic cross-repo hydrology quickstart workspace.

The script creates a self-contained working directory with:

- a shared FEMIC hydrology response bundle;
- a small WS4 compiled dataset, crosswalk, schedule, and exposure table;
- a FHOPS scenario copy, crosswalk, screen schedule, hazard schedule, exposure,
  hazard windows, and asset inventory.

It does not run the WS4 or FHOPS CLIs. The companion quickstart page runs them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pandas as pd

from fhops import __version__ as fhops_version  # type: ignore[import-untyped]
from fhops.scenario.io import load_scenario  # type: ignore[import-untyped]

DEFAULT_OUT = Path("build/hydrology_quickstart")
DEFAULT_BUNDLE = Path("tests/fixtures/hydrology/response")
DEFAULT_SCENARIO = Path("examples/lidar_tfl6")
DEFAULT_HAZARD = Path("tests/fixtures/hydrology/hazard/valid.json")
DEFAULT_ASSETS = Path("tests/fixtures/hydrology/assets/valid.json")


def build_quickstart(
    out_dir: Path,
    *,
    bundle: Path = DEFAULT_BUNDLE,
    scenario: Path = DEFAULT_SCENARIO,
    hazard: Path = DEFAULT_HAZARD,
    assets: Path = DEFAULT_ASSETS,
    force: bool = False,
) -> dict[str, object]:
    """Create a synthetic cross-repo quickstart workspace.

    Parameters
    ----------
    out_dir : Path
        Output workspace.
    bundle : Path, optional
        FEMIC hydrology response bundle.
    scenario : Path, optional
        FHOPS scenario directory to copy.
    hazard : Path, optional
        Operational hazard fixture.
    assets : Path, optional
        Road/culvert asset fixture.
    force : bool, optional
        Replace an existing output directory.

    Returns
    -------
    dict[str, object]
        Workspace manifest with paths, versions, and expected row counts.
    """
    out = out_dir.expanduser().resolve()
    if out.exists() and not force:
        raise FileExistsError(f"{out} exists; pass --force to replace it")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(bundle, out / "bundle")
    shutil.copytree(scenario, out / "fhops" / "scenario")
    shutil.copy2(hazard, out / "fhops" / "hazard.json")
    shutil.copy2(assets, out / "fhops" / "assets.json")
    _write_ws4_fixture(out)
    _write_fhops_fixture(out)
    manifest = {
        "fhops_version": fhops_version,
        "femic_version": _package_version("femic"),
        "ws4_version": _package_version("ws4"),
        "bundle": "bundle",
        "ws4_dataset": "ws4/dataset",
        "fhops_scenario": "fhops/scenario/scenario.yaml",
        "expected": {
            "ws4_screen_rows": 2,
            "fhops_screen_rows": 2,
            "fhops_constraint_events": 3,
        },
    }
    (out / "quickstart.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _write_ws4_fixture(out: Path) -> None:
    ws4 = out / "ws4"
    dataset = ws4 / "dataset"
    dataset.mkdir(parents=True)
    pd.DataFrame(
        {
            "fragment_id": [1, 2, 3, 4],
            "block_id": [10, 10, 11, 12],
            "area_ha": [0.5, 0.5, 1.0, 1.0],
        }
    ).to_parquet(dataset / "fragments.parquet", index=False)
    pd.DataFrame({"block_id": [10, 11, 12], "area_ha": [1.0, 1.0, 1.0]}).to_parquet(
        dataset / "blocks.parquet",
        index=False,
    )
    (dataset / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "tables": {
                    "fragments": "fragments.parquet",
                    "blocks": "blocks.parquet",
                },
                "sources": [],
                "options": {},
                "metadata": {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [
        {
            "fragment_id": 1,
            "block_id": "",
            "unit_id": "unit-1",
            "watershed_id": "watershed-1",
            "receptor_id": "receptor-1",
            "notes": "quickstart",
        },
        {
            "fragment_id": 2,
            "block_id": "",
            "unit_id": "unit-1",
            "watershed_id": "watershed-1",
            "receptor_id": "receptor-1",
            "notes": "quickstart",
        },
        {
            "fragment_id": 3,
            "block_id": "",
            "unit_id": "unit-1",
            "watershed_id": "watershed-1",
            "receptor_id": "receptor-1",
            "notes": "quickstart",
        },
        {
            "fragment_id": 4,
            "block_id": "",
            "unit_id": "unit-1",
            "watershed_id": "watershed-1",
            "receptor_id": "receptor-1",
            "notes": "quickstart",
        },
    ]
    _write_crosswalk(ws4 / "crosswalk.csv", rows)
    _write_metadata(
        ws4 / "crosswalk.meta.json",
        ws4 / "crosswalk.csv",
        crosswalk_id="quickstart-ws4-crosswalk",
        schema="ws4.hydrology.crosswalk.v1",
    )
    schedule = ws4 / "schedule.csv"
    schedule.write_text(
        "block_id,treatment,offset\n10,clearcut,0\n11,clearcut,1\n",
        encoding="utf-8",
    )
    _write_exposure(
        ws4 / "exposure.json",
        schedule,
        periods=(0, 1),
        watersheds=("watershed-1",),
    )


def _write_fhops_fixture(out: Path) -> None:
    fhops = out / "fhops"
    scenario_path = fhops / "scenario" / "scenario.yaml"
    scenario = load_scenario(scenario_path)
    rows: list[dict[str, object]] = []
    for block_id in scenario.block_ids():
        rows.append(_fhops_row(block_id=block_id))
    for landing_id in scenario.landing_ids():
        rows.append(_fhops_row(landing_id=landing_id))
    for road in scenario.road_construction or []:
        rows.append(_fhops_row(road_id=road.id))
    _write_crosswalk(fhops / "crosswalk.csv", rows)
    _write_metadata(
        fhops / "crosswalk.meta.json",
        fhops / "crosswalk.csv",
        crosswalk_id="quickstart-fhops-crosswalk",
        schema="fhops.hydrology.crosswalk.v1",
    )
    screen_schedule = fhops / "screen_schedule.csv"
    screen_schedule.write_text(
        "machine_id,block_id,day,shift_id\nM1,T6_19212607,1,S1\nM1,T6_23339461,2,S1\n",
        encoding="utf-8",
    )
    _write_exposure(
        fhops / "exposure.json",
        screen_schedule,
        periods=(0, 1),
        watersheds=("watershed-1",),
    )
    (fhops / "hazard_schedule.csv").write_text(
        "machine_id,block_id,day,shift_id\n"
        "M1,T6_19212607,1,S1\n"
        "M1,T6_23339461,3,S1\n"
        "M1,T6_23339462,5,S1\n",
        encoding="utf-8",
    )


def _fhops_row(
    *,
    block_id: str | None = None,
    landing_id: str | None = None,
    road_id: str | None = None,
) -> dict[str, object]:
    return {
        "block_id": block_id or "",
        "landing_id": landing_id or "",
        "road_id": road_id or "",
        "unit_id": "unit-1",
        "watershed_id": "watershed-1",
        "receptor_id": "receptor-1",
        "notes": "quickstart",
    }


def _write_crosswalk(path: Path, rows: list[dict[str, object]]) -> None:
    columns = (
        "fragment_id",
        "block_id",
        "landing_id",
        "road_id",
        "unit_id",
        "watershed_id",
        "receptor_id",
        "notes",
    )
    for row in rows:
        row.setdefault("fragment_id", "")
        row.setdefault("landing_id", "")
        row.setdefault("road_id", "")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_metadata(
    path: Path,
    crosswalk: Path,
    *,
    crosswalk_id: str,
    schema: str,
) -> None:
    payload = {
        "schema_version": schema,
        "crosswalk_id": crosswalk_id,
        "created_utc": "2026-10-27T00:00:00+00:00",
        "review_status": "reviewed",
        "reviewed_by": "quickstart-reviewer",
        "method": "Synthetic quickstart crosswalk",
        "source": "Synthetic fixture",
        "crosswalk_sha256": hashlib.sha256(crosswalk.read_bytes()).hexdigest(),
        "caveats": ["Synthetic quickstart only."],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_exposure(
    path: Path,
    schedule: Path,
    *,
    periods: tuple[int, ...],
    watersheds: tuple[str, ...],
) -> None:
    payload = {
        "schema_version": "ws4.hydrology.exposure.v1",
        "exposure_id": "quickstart-exposure",
        "generated_utc": "2026-10-27T00:00:00+00:00",
        "source_id": "synthetic-quickstart",
        "review_status": "reviewed",
        "reviewer_id": "quickstart-reviewer",
        "schedule_sha256": hashlib.sha256(schedule.read_bytes()).hexdigest(),
        "watershed_ids": list(watersheds),
        "periods": list(periods),
        "rows": [
            {
                "watershed_id": watershed_id,
                "period": period,
                "road_built_km": 0.0,
                "road_used_km": 1.0 + period,
                "road_decommissioned_km": 0.0,
                "culvert_count": 2,
                "culvert_exposed_count": period,
            }
            for watershed_id in watersheds
            for period in periods
        ],
        "caveats": ["Synthetic quickstart exposure only."],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _package_version(name: str) -> str:
    try:
        module = importlib.import_module(name)
    except ImportError:
        module = None
    if module is not None:
        value = getattr(module, "__version__", None)
        if isinstance(value, str) and value:
            return value
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--hazard", type=Path, default=DEFAULT_HAZARD)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    manifest = build_quickstart(
        args.out,
        bundle=args.bundle,
        scenario=args.scenario,
        hazard=args.hazard,
        assets=args.assets,
        force=args.force,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
