# Changelog

All notable changes to MiniSWERouterBench are documented here. Format based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Project adheres
to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `miniswerouterbench audit-trace-cost`: same aggregate as `swerouterbench
  audit-trace-cost` (sums `step_cost_usd` vs `raw_usage.cost` from
  `run_dir/*.trace.jsonl`).
- `miniswerouterbench run` accepts optional `--pool`, `--pricing`, `--ttl`, and
  `--tier-map` (paths to the same JSON tables as SWERouterBench) so two-router
  studies can pin identical pool/pricing/TTL/tier maps. `EvalRequest` /
  `RunInstanceRequest` now thread `tier_map_path` through `run_eval`.
- `scripts/examples/`: `env.inc.sh` (source SWERouterBench `.env`; if
  `OPENROUTER_API_KEY_EXP` is set it overrides `OPENROUTER_API_KEY`, matching
  `runs/*/resume.sh`), generic `resume_until_n.sh` (documents default
  `MAX_STEPS=250` / `BUDGET_USD=3.0` for mini official / leaderboard parity),
  and `example_router_a.sh` / `example_router_b.sh` as **SemanticRouterKNN**
  vs **UncommonRoute** wrappers targeting 500 Verified jobs under
  `runs/mini_sr_knn_verified500` and `runs/mini_uncommonroute_verified500`.
- README / README.zh: CLI table, run layout, A/B workflow, and note that
  detailed I/O lives in `*.mini_traj.json` (not `llm_io/`, which is editor-only).
- Trace rows include upstream ``litellm_estimate`` (see SWERouterBench
  ``swerouter/litellm_estimate.py``).

- Independent repository skeleton: `pyproject.toml` (PyPI name
  `MiniSWERouterBench`, import name `miniswerouter`), Apache-2.0 `LICENSE`,
  `.gitignore`.
- Dependency on `SWERouterBench>=0.2.0` (router protocol, pricing, cache,
  usage, leaderboard scoring/rendering, and the shared
  `swerouter.harness.container_runner`). Dependency on
  `CommonRouterBench>=0.1.0` (tokenizer + GT question bank). Dependency on
  `mini-swe-agent>=2.2,<3` (scaffold: `DefaultAgent`, `Environment`, `Model`
  protocols).
- Three thin bridges to wire mini-swe-agent onto SWERouterBench's evaluation
  harness without forking mini:
  - `miniswerouter/harness/env.py::SwebenchContainerEnv` implements mini's
    `Environment` protocol on top of a running SWE-bench work container,
    mirroring mini's `DockerEnvironment` contract (bash -lc, output dict
    shape, `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` sentinel).
  - `miniswerouter/agent/model.py::RouterAwareModel` implements mini's
    `Model` protocol, holds per-model `LitellmModel` instances, dispatches
    per step using SWERouterBench's `Router.select`, and recomputes cost via
    SWERouterBench's locked `PricingTable` four-bucket rule.
  - `miniswerouter/agent/agent.py::MiniRouterAgent` subclasses mini's
    `DefaultAgent` and overrides `query()` to (a) build a `RouterContext`
    from `self.messages` / `self.n_calls`, (b) call `router.select`, and (c)
    persist a SWERouterBench-compatible `*.trace.jsonl` in addition to
    mini's own trajectory JSON.
- CLI `miniswerouterbench` with subcommands `run`, `score`, `render`.
  `score` / `render` re-export SWERouterBench's implementations unchanged so
  leaderboards produced by either bench are directly comparable given the
  same `pricing_fingerprint`.
- CLI defaults mirror mini-swe-agent's official SWE-bench config
  (`step_limit=250`, `cost_limit=3`). Per-instance step caps
  (`--max-steps-json` / `--max-steps-json-file`) and `GoldTierRouter` are
  preserved as dev-time conveniences and explicitly marked as such in the
  CLI help and README; production runs should leave both untouched.
- Fallback patch extraction (when mini's
  `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` handshake did not fire before
  step/cost limits) now excludes `patch.txt` from the captured diff.
  `patch.txt` is the documented intermediate artifact of mini's SWE-bench
  submission protocol; including it would leak plumbing into the patch
  fed to upstream's evaluator. Implemented via a new
  ``exclude_paths`` kwarg on ``swerouter.harness.container_runner.extract_git_diff``.
