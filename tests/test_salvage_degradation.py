from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from fhops.salvage.degradation import (
    DEFAULT_CURVE_ID,
    DecayCurve,
    DecayCurveLibrary,
    DecayCurvePoint,
    DecayCurveSource,
    get_decay_curve,
    load_decay_library,
)
from fhops.salvage.report import (
    REQUIRED_STORAGE_COLUMNS,
    build_salvage_report,
    write_salvage_report,
)

TINY7 = Path("examples/tiny7/scenario.yaml")
SOURCE = DecayCurveSource(
    citation="Example source",
    url="https://example.org/source",
    boundary="Test-only boundary.",
)


def _curve(points: list[tuple[float, float]], curve_id: str = "test") -> DecayCurve:
    return DecayCurve(
        curve_id=curve_id,
        name="Test curve",
        age_unit="years",
        retention_definition="fraction",
        points=[DecayCurvePoint(age_years=age, retention_fraction=value) for age, value in points],
        source=SOURCE,
    )


def test_packaged_library_loads_with_published_curve():
    library = load_decay_library()

    assert library.schema_version == "salvage.decay.v1"
    curve = library.curve(DEFAULT_CURVE_ID)
    assert curve.curve_id == "pnw_fire_killed_mixed_conifer"
    assert curve.retention_at(0.0) == pytest.approx(1.0)
    assert curve.retention_at(1.0) == pytest.approx(0.99)
    assert curve.retention_at(2.0) == pytest.approx(0.89)
    assert curve.retention_at(3.0) == pytest.approx(0.58)
    assert curve.retention_at(4.0) == pytest.approx(0.22)
    assert curve.retention_at(5.0) == pytest.approx(0.0)
    assert "Prestemon" in curve.source.citation
    assert "not a BC-specific" in curve.source.boundary


def test_retention_interpolates_between_published_points():
    curve = _curve([(0.0, 1.0), (2.0, 0.5), (4.0, 0.0)])

    assert curve.retention_at(1.0) == pytest.approx(0.75)
    assert curve.retention_at(3.0) == pytest.approx(0.25)
    assert curve.retention_at(0.5) == pytest.approx(0.875)


def test_retention_clamps_outside_published_range():
    curve = _curve([(1.0, 1.0), (3.0, 0.4)])

    assert curve.retention_at(0.0) == 1.0
    assert curve.retention_at(99.0) == 0.4


def test_retention_rejects_negative_and_non_finite_ages():
    curve = _curve([(0.0, 1.0)])

    with pytest.raises(ValueError, match="non-negative"):
        curve.retention_at(-0.1)
    with pytest.raises(ValueError, match="finite"):
        curve.retention_at(float("nan"))


def test_product_windows_follow_published_shelf_life():
    library = load_decay_library()

    assert library.eligible_products(0.0) == ("lumber", "pulp")
    assert library.eligible_products(1.0) == ("lumber", "pulp")
    assert library.eligible_products(2.5) == ("pulp",)
    assert library.eligible_products(3.5) == ("pulp", "bioenergy")
    assert library.eligible_products(6.0) == ("bioenergy",)


def test_product_windows_reject_negative_age():
    library = load_decay_library()

    with pytest.raises(ValueError, match="non-negative"):
        library.eligible_products(-1.0)


def test_library_rejects_unknown_curve():
    library = load_decay_library()

    with pytest.raises(KeyError, match="unknown salvage decay curve"):
        library.curve("missing")


def test_curve_rejects_unordered_or_duplicate_points():
    with pytest.raises(ValidationError, match="strictly increasing"):
        _curve([(0.0, 1.0), (2.0, 0.5), (1.0, 0.2)])


def test_curve_rejects_out_of_range_retention():
    with pytest.raises(ValidationError):
        DecayCurvePoint(age_years=1.0, retention_fraction=1.1)


def test_library_rejects_wrong_schema_and_duplicate_ids():
    payload = {
        "schema_version": "wrong",
        "curves": [],
        "product_windows": [],
    }
    with pytest.raises(ValidationError, match="unsupported"):
        DecayCurveLibrary.model_validate(payload)

    curve = _curve([(0.0, 1.0)], curve_id="same")
    with pytest.raises(ValidationError, match="unique"):
        DecayCurveLibrary(
            schema_version="salvage.decay.v1",
            curves=[curve, curve],
            product_windows=[],
        )


def test_get_decay_curve_uses_supplied_library():
    library = load_decay_library()

    assert get_decay_curve(library=library).curve_id == DEFAULT_CURVE_ID
    with pytest.raises(KeyError):
        get_decay_curve("missing", library=library)


def test_build_salvage_report_joins_blocks_and_ages():
    storage = pd.DataFrame(
        {
            "block_id": ["B01", "B02"],
            "years_since_disturbance": [1.0, 4.0],
        }
    )
    report = build_salvage_report(TINY7, storage, value_per_m3=10.0)

    assert list(report.frame.columns) == [
        "block_id",
        "years_since_disturbance",
        "salvage_processing_mode",
        "is_salvage_block",
        "retention_fraction",
        "original_volume_m3",
        "retained_volume_m3",
        "value_per_m3",
        "retained_value",
        "eligible_products",
        "curve_id",
    ]
    assert len(report.frame) == 2
    assert report.frame.loc[0, "retention_fraction"] == pytest.approx(0.99)
    assert report.frame.loc[1, "retention_fraction"] == pytest.approx(0.22)
    assert report.frame.loc[0, "eligible_products"] == "lumber;pulp"
    assert report.frame.loc[1, "eligible_products"] == "pulp;bioenergy"
    assert report.frame.loc[0, "retained_value"] == pytest.approx(
        report.frame.loc[0, "retained_volume_m3"] * 10.0
    )
    assert report.total_original_volume_m3 > report.total_retained_volume_m3
    assert report.total_retained_value is not None
    assert report.blocks_without_salvage_mode == ("B01", "B02")


def test_build_salvage_report_preserves_declared_salvage_mode(tmp_path: Path):
    scenario_dir = tmp_path / "tiny7"
    shutil.copytree(Path("examples/tiny7"), scenario_dir)
    blocks_path = scenario_dir / "data" / "blocks.csv"
    blocks = pd.read_csv(blocks_path)
    blocks["salvage_processing_mode"] = "standard_mill"
    blocks.to_csv(blocks_path, index=False)

    storage = pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [1.0]})
    report = build_salvage_report(scenario_dir / "scenario.yaml", storage)

    assert bool(report.frame.loc[0, "is_salvage_block"]) is True
    assert report.frame.loc[0, "salvage_processing_mode"] == "standard_mill"
    assert report.blocks_without_salvage_mode == ()


def test_build_salvage_report_omits_value_without_price():
    storage = pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [2.0]})
    report = build_salvage_report(TINY7, storage)

    assert report.frame.loc[0, "value_per_m3"] is None
    assert report.frame.loc[0, "retained_value"] is None
    assert report.total_retained_value is None


def test_build_salvage_report_rejects_bad_storage_tables():
    with pytest.raises(ValueError, match="missing required columns"):
        build_salvage_report(TINY7, pd.DataFrame({"block_id": ["B01"]}))

    with pytest.raises(ValueError, match="at least one row"):
        build_salvage_report(
            TINY7,
            pd.DataFrame(columns=list(REQUIRED_STORAGE_COLUMNS)),
        )

    with pytest.raises(ValueError, match="duplicate block_id"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["B01", "B01"], "years_since_disturbance": [1.0, 2.0]}),
        )

    with pytest.raises(ValueError, match="numeric"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": ["not-a-number"]}),
        )

    with pytest.raises(ValueError, match="non-negative"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [-1.0]}),
        )

    with pytest.raises(ValueError, match="not present in the scenario"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["NOPE"], "years_since_disturbance": [1.0]}),
        )

    with pytest.raises(ValueError, match="value_per_m3"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [1.0]}),
            value_per_m3=-1.0,
        )

    with pytest.raises(KeyError, match="unknown salvage decay curve"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [1.0]}),
            curve_id="missing",
        )


def test_build_salvage_report_rejects_empty_block_id():
    with pytest.raises(ValueError, match="empty block_id"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["  "], "years_since_disturbance": [1.0]}),
        )


def test_write_salvage_report_outputs_csv_and_markdown(tmp_path: Path):
    storage = pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [3.0]})
    report = build_salvage_report(TINY7, storage, value_per_m3=12.5)

    written = write_salvage_report(report, tmp_path / "report")

    assert written["csv"].exists()
    assert written["markdown"].exists()
    csv_frame = pd.read_csv(written["csv"])
    assert csv_frame.loc[0, "block_id"] == "B01"
    assert csv_frame.loc[0, "curve_id"] == DEFAULT_CURVE_ID
    markdown = written["markdown"].read_text(encoding="utf-8")
    assert "Salvage shelf-life report" in markdown
    assert "retention definition" in markdown.lower()
    assert "Prestemon" in markdown
    assert "not a BC-specific" in markdown
    assert "read-only" in markdown.lower()


def test_packaged_library_json_is_valid_json_and_source_urls_are_public():
    payload = json.loads(
        Path("data/reference/degradation/salvage_decay.v1.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "salvage.decay.v1"
    for curve in payload["curves"]:
        assert curve["source"]["url"].startswith("https://")
    for window in payload["product_windows"]:
        assert window["source"]["url"].startswith("https://")


def test_build_salvage_report_preserves_leading_zero_block_ids(tmp_path: Path):
    scenario_dir = tmp_path / "tiny7_zero"
    shutil.copytree(Path("examples/tiny7"), scenario_dir)
    for path in scenario_dir.rglob("*"):
        if path.is_file() and path.suffix in {".csv", ".yaml", ".yml"}:
            path.write_text(
                path.read_text(encoding="utf-8").replace("B01", "001"), encoding="utf-8"
            )

    storage = tmp_path / "storage.csv"
    storage.write_text("block_id,years_since_disturbance\n001,1\n", encoding="utf-8")
    report = build_salvage_report(scenario_dir / "scenario.yaml", storage)

    assert report.frame.loc[0, "block_id"] == "001"
    assert report.frame.loc[0, "retention_fraction"] == pytest.approx(0.99)


def test_build_salvage_report_rejects_non_finite_age_and_value():
    with pytest.raises(ValueError, match="finite"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [float("inf")]}),
        )
    with pytest.raises(ValueError, match="finite and non-negative"):
        build_salvage_report(
            TINY7,
            pd.DataFrame({"block_id": ["B01"], "years_since_disturbance": [1.0]}),
            value_per_m3=float("nan"),
        )
