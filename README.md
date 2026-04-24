# MiniSWERouterBench

MiniSWERouterBench runs [SWERouterBench](https://github.com/CommonstackAI/SWERouterBench)'s
per-step router evaluation on top of the
[mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) scaffold.

## Quickstart

1. **Install** (Python ≥ 3.10), from a checkout of this repository:

   ```bash
   pip install -e .
   ```

2. **Runtime**: Docker must be available (same contract as SWERouterBench: SWE-bench
   containers, grading, and `git diff` extraction). Ensure you can pull or build
   the SWE-bench images used by your `swebench` version.

3. **Credentials**: copy [`.env.example`](.env.example) to `.env` in the
   `MiniSWERouterBench` directory (or export variables in your shell). Never
   commit `.env`; it is listed in [`.gitignore`](.gitignore).

   ```bash
   cp .env.example .env
   # edit .env — set OPENROUTER_BASE_URL + OPENROUTER_API_KEY (or SWEROUTER_*)
   ```

4. **Smoke run** (one Verified instance, fixed model every step):

   ```bash
   miniswerouterbench run \
     --router-import swerouter.routers.always_model:AlwaysModelRouter \
     --router-arg model_id=deepseek/deepseek-v3.2 \
     --router-arg label=always_deepseek_smoke \
     --router-label always_deepseek_smoke \
     --output-dir runs/smoke_always \
     --instances django__django-11133 \
     --limit 1 --workers 1 --run-id smoke_always
   ```

   Equivalent shell wrappers live under [`scripts/examples/`](scripts/examples/)
   (`env.inc.sh`, `resume_until_n.sh`, `example_router_a.sh`, `example_router_b.sh`).

### Environment variables

| Variable | Role |
|----------|------|
| `OPENROUTER_BASE_URL` | OpenAI-compatible API base (default if `SWEROUTER_BASE_URL` unset). |
| `OPENROUTER_API_KEY` | Bearer token for that base (default if `SWEROUTER_API_KEY` unset). |
| `SWEROUTER_BASE_URL` / `SWEROUTER_API_KEY` | Explicit names read by `miniswerouterbench run --base-url` / `--api-key` defaults. |
| `COMMONSTACK_API_BASE` / `COMMONSTACK_API_KEY` | Optional: when set, the CLI maps them onto `OPENROUTER_*` / `SWEROUTER_*` so a single gateway block in `.env` is enough (see `miniswerouter.cli._apply_gateway_aliases`). |
| `OPENROUTER_API_KEY_EXP` | Optional alternate key; used when `OPENROUTER_API_KEY` is empty. |

CLI flags `--base-url` and `--api-key` override environment defaults.

### How to plug in your router

MiniSWERouterBench does not import your code automatically. You pass an import path
and string kwargs, the CLI imports a callable, calls it, and expects a SWERouterBench
[`Router`](https://github.com/CommonstackAI/SWERouterBench/blob/main/swerouter/router.py)
instance:

- **`--router-import`**: `module:path.to.Callable` — usually a class or a
  `@classmethod` factory such as `swerouter.routers.gold_tier:GoldTierRouter.from_cli_args`.
  The target must be callable with **keyword-only** arguments matching your
  `--router-arg key=value` pairs (all values are strings).
- **`--router-arg`**: repeat as needed; passed as `**router_args` into that callable.
- **Contract**: the returned object must implement `select(ctx: RouterContext) -> RouterDecision`
  with `model_id` in `ctx.available_models`. Invalid `model_id` values fail fast
  in the harness (same as SWERouterBench).

Built-in references in the `swerouter.routers` package (shipped with SWERouterBench)
include `AlwaysModelRouter`, `RoundRobinRouter`, `GoldTierRouter`, and optional
adapters such as `SemanticRouterKNNRouter` / `UncommonRouteRouter` where you supply
artifact paths via `--router-arg`. Use `GoldTierRouter` only as an oracle / pipeline
check, not as a production router (see “Production defaults vs. dev knobs” below).

### Before you publish a repo

- Confirm **`.env` is not tracked**: `git status` should not list it; keep secrets
  out of shell history where possible.
- Search the tree for accidental keys, e.g. `rg -i 'api_key|sk-[a-zA-Z0-9]{20,}'`
  (adjust for your token format).
- **Runs and logs** belong under `runs/`, `logs/`, `agent_logs/`, etc.; they are
  ignored by [`.gitignore`](.gitignore) — do not force-add them.

## Why a separate repo?

`SWERouterBench` ships an "editor" scaffold (bash + `str_replace_editor` +
`finish`) that is tool-rich. The ground-truth tier labels published by
[CommonRouterBench](https://github.com/CommonstackAI/CommonRouterBench)
were, however, harvested from trajectories produced by mini-swe-agent's
bash-only scaffold. Reusing those labels faithfully therefore requires an
aligned scaffold.

Rather than forking SWERouterBench, MiniSWERouterBench keeps the two
scaffolds as independent benches and shares every scaffold-agnostic piece
through dependencies:

| Source | What we reuse |
|--------|---------------|
| `SWERouterBench` | Router protocol, locked pool + pricing + TTL data, four-bucket pricing table, wall-clock prompt cache, leaderboard scorer and markdown renderer, `swerouter.harness.container_runner` (Docker lifecycle, `git diff`, official eval) |
| `CommonRouterBench` | Ground-truth tier bank (`target_tier` per step) consumed by `GoldTierRouter` |
| `mini-swe-agent` | `DefaultAgent`, `Model`/`Environment` protocols, `bash`-only action space, linear history, cost/step limits |

Only three thin bridges live in this repo:

- `SwebenchContainerEnv` — mini `Environment` on a SWE-bench container.
- `RouterAwareModel` — mini `Model` that dispatches per-step via
  SWERouterBench's `Router` and prices requests with SWERouterBench's locked
  `PricingTable`.
- `MiniRouterAgent(DefaultAgent)` — writes SWERouterBench-compatible
  `*.trace.jsonl` in addition to mini's own trajectory JSON.

## Status

Alpha. CLI is `miniswerouterbench run|score|audit-infra|audit-trace-cost|render`; leaderboard files are
byte-identical in shape to SWERouterBench's, so runs on the two scaffolds
can share the same downstream tooling. Numbers from the two scaffolds are
**not** directly comparable — different `pricing_fingerprint` plus different
action space mean different games.

### CLI overview

| Command | Purpose |
|---------|---------|
| `run` | Run a router on SWE-bench Verified; writes `results/`, `*.trace.jsonl`, `agent_logs/`, `case_summaries/`, `*.mini_traj.json`, `eval_summary.json`. |
| `score` | Recompute `total_actual_bill_usd` from disk (optional `--reprice-from-raw-usage`, `--exclude-infra-failures`; optional `--pool` / `--pricing` / `--ttl` overrides). |
| `audit-infra` | Scan `results/*.json` for instances that fair-metrics exclusion would drop (same rules as SWERouterBench). |
| `audit-trace-cost` | Compare summed trace `step_cost_usd` vs provider `raw_usage.cost` under `*.trace.jsonl`. |
| `render` | Markdown leaderboard from one or more score JSON files. |

### Run directory layout (aligned with SWERouterBench where applicable)

Under `--output-dir`:

- `results/<instance_id>.json` — per-instance outcome (same schema as SWERouterBench).
- `<instance_id>.trace.jsonl` — scorer-facing trace + `loop_summary` marker.
- `agent_logs/<instance_id>/agent.log` — container harness log.
- `case_summaries/<instance_id>.summary.json` — compact per-case rollup (tier distribution, per-step summary). `io_log_path` in that JSON points at the **mini trajectory** file below (not `llm_io/`).
- `<instance_id>.mini_traj.json` — full mini-swe-agent trajectory (bash-only detailed log).

**Editor scaffold only:** SWERouterBench also writes `llm_io/<instance_id>.io.jsonl` (verbatim request/response). MiniSWERouterBench does **not** emit `llm_io/`; use `*.mini_traj.json` for detailed inspection.

### Optional `run` flags (shared tables across two routers)

Pass the same paths for both runs so `pool_fingerprint` / pricing / TTL / tier labels match:

- `--pool`, `--pricing`, `--ttl` — override JSON paths (defaults: `SWERouterBench/data/*.json` resolved from the installed package).
- `--tier-map` — override `tier_to_model.json` for `case_summaries` tier fields.

### Two-router A/B workflow

1. Run router A and router B with **identical** `--workers`, `--max-steps`, `--budget-usd`, `--run-id` pattern, and the same `--pool` / `--pricing` / `--ttl` / `--tier-map` if you override them; use **different** `--output-dir` and `--router-label`.
2. Score each run (recommended for historical traces):

   ```bash
   miniswerouterbench score --run-dir runs/your_a --router-label your_a --reprice-from-raw-usage --out runs/your_a/score_final.json
   miniswerouterbench score --run-dir runs/your_b --router-label your_b --reprice-from-raw-usage --out runs/your_b/score_final.json
   ```

3. Optional: `--exclude-infra-failures` on `score` for fair headline metrics; `audit-infra --run-dir ...` to inspect exclusions.
4. `miniswerouterbench render --score runs/your_a/score_final.json runs/your_b/score_final.json --out leaderboard.md`

Example shell wrappers (env loading + loop until N results): [scripts/examples/](scripts/examples/).
`example_router_a.sh` runs `AlwaysModelRouter` (portable baseline / smoke).
`example_router_b.sh` runs `GoldTierRouter` (oracle; needs CommonRouterBench +
SWERouterBench data paths — the script tries importlib and sibling checkouts).
For large sweeps, unset `LIMIT`, raise `TARGET_N`, and align `WORKERS` with your
hardware; for custom routers, set `ROUTER_IMPORT` / `ROUTER_EXTRA` and reuse
`resume_until_n.sh` as a loop driver.

### Production defaults vs. dev knobs

For leaderboard submissions and real evaluations, **just use the CLI
defaults**: they mirror mini-swe-agent's official `swebench.yaml` config
(`step_limit=250`, `cost_limit=3`). Do not pass `--max-steps-json` or
`--max-steps-json-file`, and do not use `GoldTierRouter` — those are
dev-time conveniences:

- `--max-steps-json(-file)`: per-instance step cap override. Useful only
  when you want to reproduce a tiny debug run cheaply (e.g. cap every
  instance at `len(CRB_GT_trajectory)` to compare against the oracle
  baseline).
- `GoldTierRouter` (imported from `swerouter.routers.gold_tier`): oracle
  router that reads
  [CommonRouterBench](https://github.com/CommonstackAI/CommonRouterBench)'s
  `target_tier` ground truth per step. Useful only for sanity-checking the
  pipeline or as a theoretical "perfect tier routing" reference — not a
  real router you'd submit to the leaderboard.

## Related projects

- [CommonRouterBench](https://github.com/CommonstackAI/CommonRouterBench) — the upstream static router benchmark and GT bank.
- [SWERouterBench](https://github.com/CommonstackAI/SWERouterBench) — dynamic router bench on the editor scaffold.
- [MiniSWERouterBench](https://github.com/CommonstackAI/MiniSWERouterBench) — this repository (mini-swe-agent harness).
- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) — the scaffold this bench pivots on.

## License

Apache-2.0.
