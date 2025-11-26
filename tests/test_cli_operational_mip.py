from fhops.cli.main import app
from tests.cli import CliRunner, cli_text


def test_solve_mip_operational_cli(tmp_path):
    runner = CliRunner()
    out_path = tmp_path / "minitoy_operational.csv"
    result = runner.invoke(
        app,
        [
            "solve-mip-operational",
            "examples/minitoy/scenario.yaml",
            "--out",
            str(out_path),
            "--time-limit",
            "1",
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    assert out_path.exists()
