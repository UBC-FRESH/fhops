from fhops.cli.main import app
from tests.cli import CliRunner, cli_text

FIXTURE_BUNDLE = "tests/fixtures/milp/minitoy_operational_bundle.json"


def test_solve_mip_operational_cli(tmp_path):
    runner = CliRunner()
    out_path = tmp_path / "minitoy_operational.csv"
    bundle_path = tmp_path / "bundle.json"
    result = runner.invoke(
        app,
        [
            "solve-mip-operational",
            "examples/minitoy/scenario.yaml",
            "--out",
            str(out_path),
            "--time-limit",
            "1",
            "--dump-bundle",
            str(bundle_path),
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    assert out_path.exists()
    assert bundle_path.exists()

    out_path2 = tmp_path / "minitoy_operational_bundle.csv"
    result_bundle = runner.invoke(
        app,
        [
            "solve-mip-operational",
            "--bundle-json",
            FIXTURE_BUNDLE,
            "--out",
            str(out_path2),
            "--time-limit",
            "1",
        ],
    )
    assert result_bundle.exit_code == 0, cli_text(result_bundle)
    assert out_path2.exists()
