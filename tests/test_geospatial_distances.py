from pathlib import Path

import pandas as pd
import pytest

from fhops.cli.geospatial import compute_distances


def test_compute_distances_cli_generates_symmetric_matrix(tmp_path):
    geojson = Path("examples/med42/med42_blocks.geojson")
    out_csv = tmp_path / "distances.csv"

    compute_distances(geojson, out_csv)

    assert out_csv.exists()
    df = pd.read_csv(out_csv)

    assert set(df.columns) == {"from_block", "to_block", "distance_m"}
    blocks = set(df["from_block"]).union(df["to_block"])
    assert len(blocks) > 0
    assert len(df) == len(blocks) * (len(blocks) - 1)
    assert (df["distance_m"] > 0).all()

    lookup = {(row["from_block"], row["to_block"]): row["distance_m"] for _, row in df.iterrows()}
    for (src, dst), distance in lookup.items():
        if (dst, src) in lookup:
            assert pytest.approx(distance, rel=1e-6) == lookup[(dst, src)]
