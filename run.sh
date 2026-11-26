#!/bin/sh
set -eu
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  if command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv .venv
  else
    python3 -m venv .venv
  fi
fi

.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m ghosts.environment
.venv/bin/python -m ghosts.build_variants --out artifacts
.venv/bin/python -m ghosts.regeneration_check artifacts
.venv/bin/python -m ghosts.verify_invariance artifacts --mutation-test
.venv/bin/python -m ghosts.probe_harness --dry-run --artifacts artifacts --out artifacts/dryrun --config configs/endpoints.json
.venv/bin/python scripts/generate_figures.py
.venv/bin/python -m pytest -q
