#!/usr/bin/env bash
# Portable example B: GoldTierRouter (oracle) — uses CommonRouterBench labels
# + SWERouterBench tier_to_model. Intended for pipeline checks, not leaderboard.
#
# Requires paths to question_bank.jsonl and tier_to_model.json. Defaults try
# (1) installed package layout (2) sibling CommonRouterBench / SWERouterBench dirs.
#
# Usage:
#   cd MiniSWERouterBench
#   export INSTANCE_IDS="django__django-11133"
#   bash scripts/examples/example_router_b.sh
#
# Override paths if needed:
#   export QUESTION_BANK_PATH=/abs/CommonRouterBench/data/question_bank.jsonl
#   export TIER_TO_MODEL_PATH=/abs/SWERouterBench/data/tier_to_model.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINI_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

_resolve_question_bank() {
  if [[ -n "${QUESTION_BANK_PATH:-}" ]]; then
    echo "${QUESTION_BANK_PATH}"
    return 0
  fi
  MINI_ROOT="${MINI_ROOT}" python3 - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

mini = Path(os.environ["MINI_ROOT"]).resolve()

def try_paths() -> list[Path]:
    out: list[Path] = []
    try:
        from importlib.resources import files

        import main

        out.append(Path(str(files(main) / "data" / "question_bank.jsonl")))
    except Exception:
        pass
    out.append(mini.parent / "CommonRouterBench" / "data" / "question_bank.jsonl")
    return out

for p in try_paths():
    if p.is_file():
        print(p)
        raise SystemExit(0)
raise SystemExit(
    "question_bank.jsonl not found. pip install CommonRouterBench or clone "
    "CommonRouterBench next to MiniSWERouterBench, or set QUESTION_BANK_PATH."
)
PY
}

_resolve_tier_map() {
  if [[ -n "${TIER_TO_MODEL_PATH:-}" ]]; then
    echo "${TIER_TO_MODEL_PATH}"
    return 0
  fi
  python3 - <<'PY'
from __future__ import annotations

from pathlib import Path

import swerouter

p = Path(swerouter.__file__).resolve().parent.parent / "data" / "tier_to_model.json"
if p.is_file():
    print(p)
    raise SystemExit(0)
raise SystemExit(
    "tier_to_model.json not found next to the swerouter install; "
    "set TIER_TO_MODEL_PATH to SWERouterBench/data/tier_to_model.json."
)
PY
}

QB="$(_resolve_question_bank)"
TM="$(_resolve_tier_map)"

export INSTANCE_IDS="${INSTANCE_IDS:-django__django-11133}"

export OUT_DIR="${OUT_DIR:-${MINI_ROOT}/runs/mini_gold_tier_smoke}"
export ROUTER_LABEL="${ROUTER_LABEL:-mini_gold_tier_smoke}"
export RUN_ID="${RUN_ID:-${ROUTER_LABEL}}"
export ROUTER_IMPORT="swerouter.routers.gold_tier:GoldTierRouter.from_cli_args"
export ROUTER_EXTRA="--router-arg question_bank_path=${QB} --router-arg tier_to_model_path=${TM} --router-arg allowed_instance_ids=${INSTANCE_IDS// /,} --router-arg label=${ROUTER_LABEL}"

export TARGET_N="${TARGET_N:-1}"
export WORKERS="${WORKERS:-1}"
export LIMIT="${LIMIT:-1}"

exec bash "${SCRIPT_DIR}/resume_until_n.sh"
