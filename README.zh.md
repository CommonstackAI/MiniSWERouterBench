# MiniSWERouterBench（中文版）

`MiniSWERouterBench` 把 [SWERouterBench](https://github.com/CommonstackAI/SWERouterBench) 里
「按步路由 + 真实美元打分」这一整套评测，**跑在 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)
的 scaffold 上**。

## 快速上手

1. **安装**（Python ≥ 3.10），在仓库根目录：

   ```bash
   pip install -e .
   ```

2. **环境**：需要可用 Docker（与 SWERouterBench 相同：拉镜像、起 SWE-bench 容器、官方评测）。

3. **密钥**：将 [`.env.example`](.env.example) 复制为同目录下的 `.env` 并填写网关地址与 Key；**切勿**将 `.env` 提交到 Git（已在 [`.gitignore`](.gitignore) 中忽略）。

4. **冒烟**：单题、每步固定模型（`AlwaysModelRouter`）：

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

   Shell 模板见 [`scripts/examples/`](scripts/examples/)（`env.inc.sh`、`resume_until_n.sh`、`example_router_a.sh`、`example_router_b.sh`）。

### 环境变量（与英文 README 一致）

| 变量 | 作用 |
|------|------|
| `OPENROUTER_BASE_URL` / `OPENROUTER_API_KEY` | OpenAI 兼容网关与 Bearer Token（`SWEROUTER_*` 未设时的默认来源）。 |
| `SWEROUTER_BASE_URL` / `SWEROUTER_API_KEY` | CLI `--base-url` / `--api-key` 的默认环境名。 |
| `COMMONSTACK_API_BASE` / `COMMONSTACK_API_KEY` | 可选：设置时由 CLI 映射到 `OPENROUTER_*` / `SWEROUTER_*`。 |
| `OPENROUTER_API_KEY_EXP` | 可选备用 Key。 |

命令行显式传入的 `--base-url` / `--api-key` 优先于环境变量。

### 如何接入你自己的 Router

通过 **`--router-import module:工厂或类`** 与多次 **`--router-arg key=value`**（值均为字符串）构造
[`Router`](https://github.com/CommonstackAI/SWERouterBench/blob/main/swerouter/router.py)：
可调用对象被 `**router_args` 调用后，必须实现 `select(ctx) -> RouterDecision`，且
`model_id` 必须属于 `ctx.available_models`（否则 harness 直接报错）。

`swerouter.routers` 下自带若干实现（如 `AlwaysModelRouter`、`GoldTierRouter`、可选适配器等）；`GoldTierRouter` 仅适合管线自检与 oracle 参考，不适合作为「真实上榜 router」。

### 开源发布前自检

- 确认 `.env` 未被 `git add`；全仓检索是否误提交 `api_key`、`sk-...` 等敏感串。
- `runs/`、`logs/`、`agent_logs/` 等产物应在 [`.gitignore`](.gitignore) 中，避免强行加入版本库。

## 为什么单开一个仓

`SWERouterBench` 的 scaffold 是「bash + `str_replace_editor` + `finish`」的多
工具版；而 [CommonRouterBench](https://github.com/CommonstackAI/CommonRouterBench)
里的 GT 档位（`target_tier`）是基于 mini-swe-agent 风格（**bash-only + 线性
history**）的轨迹标定出来的。**忠实复用 GT 必须用对齐的 scaffold**，所以单
开一仓。

但实现上我们**不重写轮子**：

| 来自 | 复用内容 |
|------|---------|
| `SWERouterBench` | `Router` 协议、锁定的池/价/TTL、四桶定价、挂钟 prompt cache、leaderboard 打分 + markdown 渲染、共享的 `swerouter.harness.container_runner`（Docker 生命周期、`git diff`、官方评测） |
| `CommonRouterBench` | GT 档位（`target_tier`），被 `GoldTierRouter` 消费 |
| `mini-swe-agent` | `DefaultAgent`、`Model` / `Environment` 协议、`bash` 单工具、线性历史、step/cost 限额 |

本仓只写 **3 个薄桥接**：

- `SwebenchContainerEnv` —— 在 SWE-bench 容器上实现 mini 的 `Environment` 协议。
- `RouterAwareModel` —— 实现 mini 的 `Model` 协议；持有多条 `LitellmModel`，
  按步调用 `Router.select` 分发；按 SWERouterBench 锁定的四桶价重新结算。
- `MiniRouterAgent(DefaultAgent)` —— 重写 `query()` 同时写一份
  SWERouterBench 兼容的 `*.trace.jsonl`，供 `swerouter.leaderboard.score` 吃。

## 状态

Alpha。CLI 为 `miniswerouterbench run|score|audit-infra|audit-trace-cost|render`；榜单文件 schema 与
SWERouterBench 一致，**可同工具链消费**。**两仓的数字不能直接比**：`pricing_fingerprint`
和 action space 都不同。

### CLI 一览

| 子命令 | 作用 |
|--------|------|
| `run` | 在 SWE-bench Verified 上跑路由；落盘 `results/`、`*.trace.jsonl`、`agent_logs/`、`case_summaries/`、`*.mini_traj.json`、`eval_summary.json`。 |
| `score` | 离线计分（可选 `--reprice-from-raw-usage`、`--exclude-infra-failures`；可选 `--pool` / `--pricing` / `--ttl`）。 |
| `audit-infra` | 扫描 `results/*.json`，列出会被公平口径剔除的实例（规则与 SWERouterBench 一致）。 |
| `audit-trace-cost` | 对 `*.trace.jsonl` 汇总 `step_cost_usd` 与 `raw_usage.cost` 做对比。 |
| `render` | 从若干 `score.json` 生成 markdown 榜单。 |

### 运行目录布局（与 SWERouterBench 对齐的部分）

在 `--output-dir` 下：

- `results/<instance_id>.json` — 与主仓同 schema 的单题结果。
- `<instance_id>.trace.jsonl` — 计分用 trace + `loop_summary`。
- `agent_logs/<instance_id>/agent.log` — 容器侧日志。
- `case_summaries/<instance_id>.summary.json` — 简化摘要（档位分布、逐步摘要）。其中 `io_log_path` 指向下面的 **mini 轨迹文件**（不是 `llm_io/`）。
- `<instance_id>.mini_traj.json` — mini-swe-agent 完整轨迹（bash-only 下的「详细日志」）。

**说明：** SWERouterBench（editor scaffold）额外有 `llm_io/<instance_id>.io.jsonl`（逐步原始请求/响应）。Mini 侧**不生成** `llm_io/`，详细内容以 `*.mini_traj.json` 为准。

### `run` 可选参数（两路由对比时锁同一套表）

两次跑传入相同的 `--pool`、`--pricing`、`--ttl`、`--tier-map`（若需覆盖默认），可保证池指纹、计价、TTL、`case_summaries` 档位映射一致；仅改 `--output-dir`、`--router-label`、`--router-import` / `--router-arg`。

### 双路由 A/B 流程

1. 路由 A、B 各跑一次：`--workers` / `--max-steps` / `--budget-usd` / `--run-id` 及数据文件路径保持一致；`--output-dir` 与 `--router-label` 区分。
2. 分别计分（推荐全量复现时加 `--reprice-from-raw-usage`）：

   ```bash
   miniswerouterbench score --run-dir runs/your_a --router-label your_a --reprice-from-raw-usage --out runs/your_a/score_final.json
   miniswerouterbench score --run-dir runs/your_b --router-label your_b --reprice-from-raw-usage --out runs/your_b/score_final.json
   ```

3. 需要「有效样本」口径时：`score` 加 `--exclude-infra-failures`；事先可用 `audit-infra --run-dir ...` 看剔除面。
4. `miniswerouterbench render --score runs/your_a/score_final.json runs/your_b/score_final.json --out leaderboard.md`

可复用脚本模板：[scripts/examples/](scripts/examples/) 下 `env.inc.sh`、`resume_until_n.sh`、`example_router_a.sh`（`AlwaysModelRouter` 便携基线）、`example_router_b.sh`（`GoldTierRouter`，需 CRB + SWERouterBench 数据路径；脚本会尝试 importlib 与相邻目录）。大规模补跑可调高 `TARGET_N`、去掉 `LIMIT`，或自行设置 `ROUTER_IMPORT` / `ROUTER_EXTRA` 复用 `resume_until_n.sh`。

### 生产默认 vs. 开发期旋钮

**上榜 / 对比实验：直接用 CLI 默认值即可**，和 mini-swe-agent 官方
`swebench.yaml` 对齐（`step_limit=250`、`cost_limit=3`）。**不要**传
`--max-steps-json` / `--max-steps-json-file`，**也不要**用
`GoldTierRouter`，这两个是**开发期辅助工具**：

- `--max-steps-json(-file)`：按 instance 覆写步数上限。只在想**便宜复现**
  某次调试（比如把每题上限压到 `len(CRB_GT_trajectory)`）时用。
- `GoldTierRouter`（`swerouter.routers.gold_tier`）：按
  [CommonRouterBench](https://github.com/CommonstackAI/CommonRouterBench)
  GT 档位做的 oracle 路由。只用来**做整条链路的自洽性校验**或者当「完美档
  位路由」的理论参考线，**不是**会拿去上榜的真实 router。

## 相关项目

- [CommonRouterBench](https://github.com/CommonstackAI/CommonRouterBench)：上游静态路由 bench 与 GT 源。
- [SWERouterBench](https://github.com/CommonstackAI/SWERouterBench)：editor scaffold 的动态路由 bench。
- [MiniSWERouterBench](https://github.com/CommonstackAI/MiniSWERouterBench)：本仓库源码（mini-swe-agent 侧 harness）。
- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)：本仓依托的 scaffold。

## 许可

Apache-2.0。
