#!/usr/bin/env bash
# Run miniswerouterbench in a loop until OUT_DIR/results has TARGET_N JSON files
# (same idea as runs/*/run_until_500.sh for SWERouterBench).
#
# Required env (set by a wrapper or export before invoking):
#   OUT_DIR          -- e.g. runs/mini_router_a
#   ROUTER_IMPORT    -- e.g. swerouter.routers.always_model:AlwaysModelRouter
#   ROUTER_LABEL     -- human label for eval_summary / score
#
# Optional env:
#   RUN_ID           -- default: ROUTER_LABEL
#   TARGET_N         -- default: 500
#   LIMIT            -- if set, passed as --limit (e.g. 1 for smoke)
#   INSTANCE_IDS     -- space-separated SWE-bench ids, passed as --instances ...
#   WORKERS          -- default: 2
#   MAX_STEPS        -- default: 250 (mini-swe-agent SWE-bench official; use for
#                       leaderboard-comparable runs vs mini v2 × Verified table)
#   BUDGET_USD       -- default: 3.0 (same as mini official SWE-bench cost_limit)
#                       Shorter dev runs (e.g. max_steps=40 / budget_usd=5) are not
#                       comparable to that leaderboard without relabeling.
#   ROUTER_EXTRA     -- extra CLI words for --router-arg / other flags (no quotes inside values)
#   MAX_ROUNDS       -- default: 200
#   STALL_LIMIT      -- default: 4 (give up after this many rounds with no new results)
#   POOL PRICING TTL TIER_MAP -- optional paths passed to --pool --pricing --ttl --tier-map
#
# Usage:
#   bash scripts/examples/example_router_a.sh
#   bash scripts/examples/example_router_b.sh
#   # Full dual-router (500 Verified each, same MAX_STEPS/BUDGET): run the two
#   # wrappers in parallel terminals; keep WORKERS/POOL/PRICING/TTL/TIER_MAP aligned.
#   # or:
#   export OUT_DIR=... ROUTER_IMPORT=... ROUTER_LABEL=...
#   bash scripts/examples/resume_until_n.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/env.inc.sh"

MINI_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_ROOT="$(cd "${MINI_ROOT}/.." && pwd)"
# Prefer ``pip install`` packages; only prepend monorepo src dirs when present.
_PY_EXTRA=("${MINI_ROOT}")
if [[ -d "${REPO_ROOT}/SWERouterBench/swerouter" ]]; then
  _PY_EXTRA+=("${REPO_ROOT}/SWERouterBench")
fi
if [[ -d "${REPO_ROOT}/CommonRouterBench/main" ]]; then
  _PY_EXTRA+=("${REPO_ROOT}/CommonRouterBench")
fi
export PYTHONPATH="$(
  IFS=:
  echo "${_PY_EXTRA[*]}"
)${PYTHONPATH:+:${PYTHONPATH}}"

: "${OUT_DIR:?set OUT_DIR}"
: "${ROUTER_IMPORT:?set ROUTER_IMPORT}"
: "${ROUTER_LABEL:?set ROUTER_LABEL}"

RUN_ID="${RUN_ID:-${ROUTER_LABEL}}"
TARGET_N="${TARGET_N:-500}"
WORKERS="${WORKERS:-2}"
MAX_STEPS="${MAX_STEPS:-250}"
BUDGET_USD="${BUDGET_USD:-3.0}"
MAX_ROUNDS="${MAX_ROUNDS:-200}"
STALL_LIMIT="${STALL_LIMIT:-4}"
ROUTER_EXTRA="${ROUTER_EXTRA:-}"

count_results() {
  mkdir -p "${OUT_DIR}/results"
  find "${OUT_DIR}/results" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l
}

DATA_ARGS=()
if [[ -n "${POOL:-}" ]]; then DATA_ARGS+=(--pool "${POOL}"); fi
if [[ -n "${PRICING:-}" ]]; then DATA_ARGS+=(--pricing "${PRICING}"); fi
if [[ -n "${TTL:-}" ]]; then DATA_ARGS+=(--ttl "${TTL}"); fi
if [[ -n "${TIER_MAP:-}" ]]; then DATA_ARGS+=(--tier-map "${TIER_MAP}"); fi

LIMIT_ARGS=()
if [[ -n "${LIMIT:-}" ]]; then LIMIT_ARGS+=(--limit "${LIMIT}"); fi

INSTANCE_ARGS=()
if [[ -n "${INSTANCE_IDS:-}" ]]; then
  # shellcheck disable=SC2206
  INSTANCE_ARGS=(--instances ${INSTANCE_IDS})
fi

STALL_ROUNDS=0
PREV=-1

cd "${MINI_ROOT}"

for round in $(seq 1 "${MAX_ROUNDS}"); do
  n="$(count_results)"
  echo "$(date -Is) resume_until_n: round=${round} results=${n}/${TARGET_N} out=${OUT_DIR}"
  if [[ "${n}" -ge "${TARGET_N}" ]]; then
    echo "$(date -Is) resume_until_n: finished (${n} results)."
    exit 0
  fi
  if [[ "${n}" -eq "${PREV}" ]] && [[ "${round}" -gt 1 ]]; then
    STALL_ROUNDS=$((STALL_ROUNDS + 1))
    if [[ "${STALL_ROUNDS}" -ge "${STALL_LIMIT}" ]]; then
      echo "$(date -Is) resume_until_n: no new results for ${STALL_ROUNDS} rounds; giving up." >&2
      exit 1
    fi
  else
    STALL_ROUNDS=0
  fi
  PREV="${n}"

  # shellcheck disable=SC2086
  set +e
  python3 -m miniswerouter.cli run \
    --router-import "${ROUTER_IMPORT}" \
    ${ROUTER_EXTRA} \
    --router-label "${ROUTER_LABEL}" \
    --output-dir "${OUT_DIR}" \
    --workers "${WORKERS}" \
    --max-steps "${MAX_STEPS}" \
    --budget-usd "${BUDGET_USD}" \
    --run-id "${RUN_ID}" \
    "${LIMIT_ARGS[@]}" \
    "${INSTANCE_ARGS[@]}" \
    "${DATA_ARGS[@]}"
  rc=$?
  set -e
  if [[ "${rc}" != 0 ]]; then
    echo "$(date -Is) resume_until_n: miniswerouterbench exited ${rc}; retrying after short sleep." >&2
  fi
  sleep 3
done

echo "$(date -Is) resume_until_n: exceeded MAX_ROUNDS=${MAX_ROUNDS}" >&2
exit 1
