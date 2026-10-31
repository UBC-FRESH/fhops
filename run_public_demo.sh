#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=src:.
exec /home/gep/projects/fhops/.venv/bin/python -m uvicorn demo_app:app --host 127.0.0.1 --port "${PORT:-8780}"
