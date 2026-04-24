# MiniSWERouterBench（说明）

在 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) scaffold 上，跑与 [SWERouterBench](https://github.com/CommonstackAI/SWERouterBench) 一致的「按步选模型 + 美元计分」评测；入口命令为 **`miniswerouterbench`**。

## 标准模型池（锁定）

Router 的 `select()` 返回的 `model_id` 必须来自 **SWERouterBench 随包锁定的池**（已安装包内 `data/model_pool.json`，或 GitHub 上的
[同文件](https://github.com/CommonstackAI/SWERouterBench/blob/main/data/model_pool.json)）。当前四个合法 `model_id` 为：

| `model_id` | 说明 |
|------------|------|
| `anthropic/claude-opus-4.6` | **高价 baseline**（`is_high_baseline=true`）：失败题会按该模型计一次完整重放账单。 |
| `google/gemini-3-flash-preview` | 池内模型 |
| `minimax/minimax-m2.7` | 池内模型 |
| `deepseek/deepseek-v3.2` | 池内模型 |

计价、TTL、档位映射等表与 SWERouterBench 的 `data/` 一致。仅在需要固定另一套 JSON 时，再用 `run` / `score` 的 `--pool`、`--pricing`、`--ttl`、`--tier-map` 覆盖路径。

## 环境要求

- Python **3.10+**
- **Docker**（与 SWERouterBench 相同：SWE-bench Verified 镜像与评测）
- **OpenAI 兼容** LLM 网关（base URL + API Key；常用 [OpenRouter](https://openrouter.ai/)）

## 安装

```bash
pip install -e .
```

## 密钥与 `.env`

复制 [`.env.example`](.env.example) 为仓库根目录下的 `.env`（或在 shell 里 `export`）。CLI 会在变量未设置时读取 `.env`。**不要**把 `.env` 提交到 Git。

| 变量 | 作用 |
|------|------|
| `OPENROUTER_BASE_URL` / `OPENROUTER_API_KEY` | 未设 `SWEROUTER_*` 时的默认网关 |
| `SWEROUTER_BASE_URL` / `SWEROUTER_API_KEY` | 与 `run` 默认参数对应的名字 |
| `COMMONSTACK_API_BASE` / `COMMONSTACK_API_KEY` | 可选，由 CLI 映射到上述变量 |
| `OPENROUTER_API_KEY_EXP` | 可选备用 Key |

`run` 上的 `--base-url` / `--api-key` 优先于环境变量。

## 接入并测试一个 Router

1. **实现** SWERouterBench 的 [`Router`](https://github.com/CommonstackAI/SWERouterBench/blob/main/swerouter/router.py)：`select(ctx) -> RouterDecision`，且 `model_id` 必须属于 `ctx.available_models`（非法值会直接报错）。

2. **跑一次**（示例：只跑一道 Verified 题做冒烟）：

   ```bash
   miniswerouterbench run \
     --router-import 你的模块:你的Router类 \
     --router-arg 参数名=参数值 \
     --router-label my_router_smoke \
     --output-dir runs/my_router_smoke \
     --instances django__django-11133 \
     --limit 1 --workers 1 --run-id my_router_smoke
   ```

   内置参考（每步固定同一模型）：

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

   需要非字符串构造参数时，用类方法工厂，例如  
   `swerouter.routers.gold_tier:GoldTierRouter.from_cli_args`，并多次传入 `--router-arg key=value`（**值一律为字符串**）。更多参考实现见 SWERouterBench 包内 `swerouter.routers`。

3. **对本次 run 计分**：

   ```bash
   miniswerouterbench score \
     --run-dir runs/my_router_smoke \
     --router-label my_router_smoke \
     --reprice-from-raw-usage \
     --out runs/my_router_smoke/score.json
   ```

4. **可选**：`audit-infra`、`audit-trace-cost`、`render` 做剔除面检查、费用对账或生成榜单 Markdown。

辅助脚本：[scripts/examples/](scripts/examples/)（`env.inc.sh`、`resume_until_n.sh`、`example_router_a.sh`、`example_router_b.sh`）。

## CLI 一览

| 子命令 | 作用 |
|--------|------|
| `run` | 在 Verified 上跑你的 router；在 `--output-dir` 下写 `results/`、`*.trace.jsonl`、`agent_logs/`、`case_summaries/`、`*.mini_traj.json`、`eval_summary.json`。 |
| `score` | 离线计分；可选 `--reprice-from-raw-usage`、`--exclude-infra-failures` 及 `--pool` / `--pricing` / `--ttl`。 |
| `audit-infra` | 看哪些题会被公平口径剔除。 |
| `audit-trace-cost` | trace 内计价与 `raw_usage.cost` 对比。 |
| `render` | 从多个 `score.json` 生成榜单 Markdown。 |

## 输出目录说明（`--output-dir`）

- `results/<instance_id>.json` — 单题结果（与 SWERouterBench 同 schema）
- `<instance_id>.trace.jsonl` — 计分用 trace
- `agent_logs/`、`case_summaries/`、`*.mini_traj.json` — 日志与 mini 轨迹（**没有** SWERouterBench editor 侧的 `llm_io/`）

## 官方评测默认值

与 mini-swe-agent 公布的 SWE-bench 配置一致：**`--max-steps 250`**、**`--budget-usd 3`**。要做可对比的正式跑分，请保持默认，勿随意使用 `--max-steps-json` 等开发用开关。

## 相关仓库

- [SWERouterBench](https://github.com/CommonstackAI/SWERouterBench)
- [CommonRouterBench](https://github.com/CommonstackAI/CommonRouterBench)
- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)
- [本仓库](https://github.com/CommonstackAI/MiniSWERouterBench)

## 许可

Apache-2.0。
