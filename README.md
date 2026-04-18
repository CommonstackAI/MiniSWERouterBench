# MiniSWERouterBench

MiniSWERouterBench runs [SWERouterBench](https://github.com/commonrouter-lab/SWERouterBench)'s
per-step router evaluation on top of the
[mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) scaffold.

## Why a separate repo?

`SWERouterBench` ships an "editor" scaffold (bash + `str_replace_editor` +
`finish`) that is tool-rich. The ground-truth tier labels published by
[CommonRouterBench](https://github.com/commonrouter-lab/CommonRouterBench)
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

Alpha. CLI is `miniswerouterbench run|score|render`; leaderboard files are
byte-identical in shape to SWERouterBench's, so runs on the two scaffolds
can share the same downstream tooling. Numbers from the two scaffolds are
**not** directly comparable — different `pricing_fingerprint` plus different
action space mean different games.

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
  [CommonRouterBench](https://github.com/commonrouter-lab/CommonRouterBench)'s
  `target_tier` ground truth per step. Useful only for sanity-checking the
  pipeline or as a theoretical "perfect tier routing" reference — not a
  real router you'd submit to the leaderboard.

## Related projects

- [CommonRouterBench](https://github.com/commonrouter-lab/CommonRouterBench) — the upstream static router benchmark and GT bank.
- [SWERouterBench](https://github.com/commonrouter-lab/SWERouterBench) — dynamic router bench on the editor scaffold.
- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) — the scaffold this bench pivots on.

## License

Apache-2.0.
