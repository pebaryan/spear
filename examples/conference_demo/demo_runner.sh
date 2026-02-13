#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RUN_SHACL=1
for arg in "$@"; do
  if [[ "$arg" == "--skip-shacl" ]]; then
    RUN_SHACL=0
  fi
done

echo "[1/3] Running deterministic graph-native demo runner..."
python "$SCRIPT_DIR/demo_runner.py" --reset

echo "[2/3] Running API-mode demo runner (/api/v1/*)..."
python "$SCRIPT_DIR/api_demo_runner.py" --mode inprocess --reset

if [[ "$RUN_SHACL" -eq 1 ]]; then
  if python - <<'PY'
import importlib
import sys
sys.exit(0 if importlib.util.find_spec("pyshacl") else 1)
PY
  then
    echo "[3/3] Running SHACL validation..."
    python "$SCRIPT_DIR/semantic/validate_shapes.py" --data-dir "$SCRIPT_DIR/run_data"
  else
    echo "[3/3] Skipping SHACL validation (pyshacl not installed)."
  fi
else
  echo "[3/3] Skipping SHACL validation (--skip-shacl)."
fi

echo "Conference demo suite completed."
