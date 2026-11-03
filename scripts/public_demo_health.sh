#!/usr/bin/env bash
# Return success only when the public-demo origin is serving its health endpoint.
set -euo pipefail
curl --fail --silent --show-error --max-time 3 \
  "http://127.0.0.1:${PORT:-8780}/studio/api/health" >/dev/null
