#!/usr/bin/env bash
# Load API credentials for miniswerouterbench example wrappers.
#
# Layout assumed (CommonRouterBench monorepo):
#   <repo>/MiniSWERouterBench/scripts/examples/env.inc.sh
#   <repo>/MiniSWERouterBench/.env   <-- primary (OPENROUTER_* / CommonStack, etc.)
#
# Optional: export SWEROUTER_REPO=/path/to/SWERouterBench if the checkout is not
# next to MiniSWERouterBench (used only for PYTHONPATH in resume_until_n.sh).

MINI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_DEFAULT_SW="$(cd "${MINI_ROOT}/.." && pwd)/SWERouterBench"
SWEROUTER_REPO="${SWEROUTER_REPO:-${_DEFAULT_SW}}"

if [[ -f "${MINI_ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${MINI_ROOT}/.env"
  set +a
else
  echo "env.inc.sh: warning: ${MINI_ROOT}/.env not found; set OPENROUTER_* / SWEROUTER_* in the shell." >&2
fi

# CommonStack: when set, overrides OPENROUTER_* and SWEROUTER_* (so legacy keys
# in .env do not shadow COMMONSTACK_* for mini bench runs). Mirrors
# ``miniswerouter.cli._apply_gateway_aliases``.
if [[ -n "${COMMONSTACK_API_BASE:-}" ]]; then
  export OPENROUTER_BASE_URL="${COMMONSTACK_API_BASE}"
  export SWEROUTER_BASE_URL="${COMMONSTACK_API_BASE}"
fi
if [[ -n "${COMMONSTACK_API_KEY:-}" ]]; then
  export OPENROUTER_API_KEY_EXP="${COMMONSTACK_API_KEY}"
  export OPENROUTER_API_KEY="${COMMONSTACK_API_KEY}"
  export SWEROUTER_API_KEY="${COMMONSTACK_API_KEY}"
fi

# Prefer OPENROUTER_API_KEY_EXP when CommonStack did not set the key.
if [[ -z "${COMMONSTACK_API_KEY:-}" ]] && [[ -n "${OPENROUTER_API_KEY_EXP:-}" ]]; then
  export OPENROUTER_API_KEY="${OPENROUTER_API_KEY_EXP}"
fi

# Align env names with miniswerouter.cli defaults (SWEROUTER_* or OPENROUTER_*).
# Set OPENROUTER_BASE_URL / OPENROUTER_API_KEY_EXP in MiniSWERouterBench/.env
# (e.g. CommonStack: https://api.commonstack.ai/v1).
export SWEROUTER_BASE_URL="${SWEROUTER_BASE_URL:-${OPENROUTER_BASE_URL:-}}"
export SWEROUTER_API_KEY="${SWEROUTER_API_KEY:-${OPENROUTER_API_KEY:-}}"
