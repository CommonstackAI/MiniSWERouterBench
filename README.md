# MiniSWERouterBench

Run [SWERouterBench](https://github.com/CommonstackAI/SWERouterBench)-style per-step routing and USD scoring on the [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) scaffold (`miniswerouterbench` CLI).

## Standard model pool (locked)

Your router’s `select()` must return a `model_id` that appears in the **locked pool**
shipped with SWERouterBench (`data/model_pool.json` inside the installed package, or
[this copy](https://github.com/CommonstackAI/SWERouterBench/blob/main/data/model_pool.json)
on GitHub). The current four IDs are:

| `model_id` | Role in the bench |
|------------|---------------------|
| `anthropic/claude-opus-4.6` | **High baseline** (`is_high_baseline=true`): failed runs bill a full replay at this model. |
| `google/gemini-3-flash-preview` | Pool member |
| `minimax/minimax-m2.7` | Pool member |
| `deepseek/deepseek-v3.2` | Pool member |

Pricing, TTL, and tier→model tables come from the same SWERouterBench `data/` bundle.
Override paths only if you intentionally pin different JSON files (`--pool`, `--pricing`, `--ttl`, `--tier-map` on `run` / `score`).

## Prerequisites

- Python **3.10+**
- **Docker** (SWE-bench Verified images, same contract as SWERouterBench)
- An **OpenAI-compatible** LLM gateway (base URL + API key; [OpenRouter](https://openrouter.ai/) is typical)

## Install

```bash
pip install -e .
```

## API credentials

Copy [`.env.example`](.env.example) to `.env` in this repo root (or export vars in your shell). The CLI loads `.env` when variables are unset. Do **not** commit `.env`.

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_BASE_URL` / `OPENROUTER_API_KEY` | Default gateway if `SWEROUTER_*` unset |
| `SWEROUTER_BASE_URL` / `SWEROUTER_API_KEY` | Explicit names for `run` defaults |
| `COMMONSTACK_API_BASE` / `COMMONSTACK_API_KEY` | Optional; mapped to the above (see `miniswerouter.cli`) |
| `OPENROUTER_API_KEY_EXP` | Optional backup key |

`--base-url` and `--api-key` on `run` override the environment.

## Plug in and test one router

1. **Implement** the SWERouterBench [`Router`](https://github.com/CommonstackAI/SWERouterBench/blob/main/swerouter/router.py) protocol: synchronous `select(ctx) -> RouterDecision`, with `model_id` ∈ `ctx.available_models` (invalid IDs fail fast).

2. **Run** the harness (example: one Verified instance, smoke settings):

   ```bash
   miniswerouterbench run \
     --router-import your.package.module:YourRouterClass \
     --router-arg some_param=value \
     --router-label my_router_smoke \
     --output-dir runs/my_router_smoke \
     --instances django__django-11133 \
     --limit 1 --workers 1 --run-id my_router_smoke
   ```

   Built-in smoke reference (fixed model every step):

   ```bash
   miniswerouterbench run \
     --router-import swerouter.routers.always_model:AlwaysModelRouter \
     --router-arg model_id=deepseek/deepseek-v3.2 \
     --router-arg label=always_deepseek \
     --router-label always_deepseek_smoke \
     --output-dir runs/smoke_always \
     --instances django__django-11133 \
     --limit 1 --workers 1 --run-id smoke_always
   ```

   Factories with non-string constructor args use a dotted import, e.g.
   `swerouter.routers.gold_tier:GoldTierRouter.from_cli_args` plus `--router-arg key=value` (all string values). Reference routers live under `swerouter.routers` in the SWERouterBench package.

3. **Score** the run directory:

   ```bash
   miniswerouterbench score \
     --run-dir runs/my_router_smoke \
     --router-label my_router_smoke \
     --reprice-from-raw-usage \
     --out runs/my_router_smoke/score.json
   ```

4. **Optional checks**: `audit-infra --run-dir ...` (infra exclusions), `audit-trace-cost --run-dir ...` (trace vs provider cost), `render --score ... --out leaderboard.md`.

Shell helpers: [`scripts/examples/`](scripts/examples/) (`env.inc.sh`, `resume_until_n.sh`, `example_router_a.sh`, `example_router_b.sh`).

## CLI

| Command | Purpose |
|---------|---------|
| `run` | Run one router on SWE-bench Verified; writes `results/`, `*.trace.jsonl`, `agent_logs/`, `case_summaries/`, `*.mini_traj.json`, `eval_summary.json` under `--output-dir`. |
| `score` | Recompute `total_actual_bill_usd` (optional `--reprice-from-raw-usage`, `--exclude-infra-failures`, `--pool` / `--pricing` / `--ttl`). |
| `audit-infra` | List instances dropped by fair-metrics infra rules. |
| `audit-trace-cost` | Compare trace `step_cost_usd` vs `raw_usage.cost`. |
| `render` | Markdown leaderboard from `score.json` files. |

## Output layout (`--output-dir`)

- `results/<instance_id>.json` — outcome (SWERouterBench-compatible schema)
- `<instance_id>.trace.jsonl` — scorer-facing trace + `loop_summary`
- `agent_logs/<instance_id>/agent.log` — harness log
- `case_summaries/<instance_id>.summary.json` — per-case rollup
- `<instance_id>.mini_traj.json` — full mini-swe-agent trajectory (there is no `llm_io/` like the editor scaffold in SWERouterBench)

## Official eval defaults

CLI defaults match mini-swe-agent’s published SWE-bench settings: **`--max-steps 250`**, **`--budget-usd 3`**. For a real submission or comparable numbers, keep those defaults and avoid dev-only flags such as `--max-steps-json` unless you know why you need them.

## Related repositories

- [SWERouterBench](https://github.com/CommonstackAI/SWERouterBench) — router protocol, locked `data/`, editor-scaffold bench
- [CommonRouterBench](https://github.com/CommonstackAI/CommonRouterBench) — tier GT bank (e.g. for `GoldTierRouter` smoke)
- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) — agent scaffold
- [This repo](https://github.com/CommonstackAI/MiniSWERouterBench) — source for `miniswerouterbench`

## License

Apache-2.0.
