import os

import pytest

_CLI_ENV_FLAG = "FHOPS_RUN_FULL_CLI_TESTS"
_CLI_PREFIXES = ("tests/test_cli_",)


def pytest_collection_modifyitems(config, items):
    """Skip slow CLI integration tests unless explicitly enabled."""

    if os.getenv(_CLI_ENV_FLAG):
        return
    skip_cli = pytest.mark.skip(
        reason=f"Set {_CLI_ENV_FLAG}=1 to run the CLI integration test suite."
    )
    for item in items:
        nodeid = item.nodeid
        if nodeid.startswith(_CLI_PREFIXES):
            item.add_marker(skip_cli)
