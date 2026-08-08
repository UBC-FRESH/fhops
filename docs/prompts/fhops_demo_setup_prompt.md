# FHOPS Demo Setup Prompt

Paste the following prompt into Copilot in the new development container:

```text
We are setting up a runnable FHOPS demo for Linux user `gep` in this development container.

First, verify the environment:

1. Run `id -un`, `python --version`, `pwd`, and `git status` where applicable.
2. Confirm the current user is `gep`. Do not use `sudo`, and do not create files owned by another user.
3. Locate the FHOPS checkout by finding the directory containing `pyproject.toml` with project name `fhops`. Do not assume the path is `/home/gep/projects/fhops`; use the path that exists in this container.
4. If no FHOPS checkout exists, clone only this repository into a new directory:
   ```bash
   mkdir -p "$HOME/projects"
   git clone https://github.com/UBC-FRESH/fhops.git "$HOME/projects/fhops"
   ```
   Do not clone `ws3`, `fresh-agent-core`, or any other repository for this demo. FHOPS's Python dependencies are installed from its `pyproject.toml` in the next step. If a candidate target directory already exists but is not an FHOPS checkout, stop and report it rather than overwriting it. If cloning is impossible because network access or GitHub authentication is unavailable, report that clearly.
5. Before changing anything in the checkout, read:
   - `AGENTS.md`
   - `README.md`
   - `docs/howto/quickstart.rst`
6. Do not run destructive Git or filesystem commands such as `git reset --hard`, `git clean`, or recursive deletion. Preserve any existing worktree changes.

Set up the demo without modifying tracked source files:

1. Change into the FHOPS repository.
2. Create or reuse the repository-local virtual environment at `.venv`:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -e '.[dev]'
   ```
   FHOPS requires Python 3.11 or newer. If the container has an incompatible Python version, report that clearly and stop before making broader changes.
   The editable install pulls the required Python packages from FHOPS's project metadata, including Pyomo, pandas, NumPy, PyYAML, PyArrow, Optuna, and the HiGHS Python solver. Do not install Gurobi for this smoke demo; HiGHS is the default open-source MIP backend and does not require a commercial licence. Do not install the optional `geo` or `gurobi` extras unless the user specifically requests them.
3. Verify the package and CLI:
   ```bash
   python -c "import fhops; print(fhops.__version__)"
   fhops --help
   ```
4. Run a complete small deterministic demo using the bundled `examples/tiny7/scenario.yaml`. Put generated outputs under `tmp/demo-gep/`, not under tracked example directories:
   ```bash
   mkdir -p tmp/demo-gep

   fhops validate examples/tiny7/scenario.yaml

   fhops solve-mip examples/tiny7/scenario.yaml \
     --driver highs \
     --out tmp/demo-gep/mip_solution.csv

   fhops solve-heur examples/tiny7/scenario.yaml \
     --out tmp/demo-gep/sa_solution.csv

   fhops evaluate examples/tiny7/scenario.yaml \
     --assignments tmp/demo-gep/mip_solution.csv

   fhops evaluate examples/tiny7/scenario.yaml \
     --assignments tmp/demo-gep/sa_solution.csv
   ```
5. Confirm that both solution CSVs exist and contain rows, and summarize the evaluation metrics. Check especially for sequencing violations if that metric is reported.
6. Optionally, if Jupyter is installed and the container supports interactive notebooks, identify the onboarding notebooks under `examples/`, especially:
   - `examples/00_fhops_orientation.ipynb`
   - `examples/02_fhops_solve_compare.ipynb`
   - `examples/03_fhops_playback_kpis.ipynb`
   Do not execute notebooks automatically unless the environment is clearly configured for it.

At the end, report:

- The actual FHOPS repository path.
- The Python executable and version used.
- Whether the virtual environment and editable install succeeded.
- The exact demo commands run.
- The paths of generated demo outputs.
- Key validation/evaluation results.
- Any blocker, warning, or dependency issue.
- Whether `git status --short` shows any tracked-file changes.

Keep the setup focused on a user-facing smoke demo. Do not run the full formatter, linter, mypy, documentation, or entire test cadence unless a setup failure requires targeted diagnosis.
```
