# MiniSWERouterBench（中文版）

`MiniSWERouterBench` 把 [SWERouterBench](https://github.com/commonrouter-lab/SWERouterBench) 里
「按步路由 + 真实美元打分」这一整套评测，**跑在 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)
的 scaffold 上**。

## 为什么单开一个仓

`SWERouterBench` 的 scaffold 是「bash + `str_replace_editor` + `finish`」的多
工具版；而 [CommonRouterBench](https://github.com/commonrouter-lab/CommonRouterBench)
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

Alpha。CLI 为 `miniswerouterbench run|score|render`；榜单文件 schema 与
SWERouterBench 一致，**可同工具链消费**。**两仓的数字不能直接比**：`pricing_fingerprint`
和 action space 都不同。

### 生产默认 vs. 开发期旋钮

**上榜 / 对比实验：直接用 CLI 默认值即可**，和 mini-swe-agent 官方
`swebench.yaml` 对齐（`step_limit=250`、`cost_limit=3`）。**不要**传
`--max-steps-json` / `--max-steps-json-file`，**也不要**用
`GoldTierRouter`，这两个是**开发期辅助工具**：

- `--max-steps-json(-file)`：按 instance 覆写步数上限。只在想**便宜复现**
  某次调试（比如把每题上限压到 `len(CRB_GT_trajectory)`）时用。
- `GoldTierRouter`（`swerouter.routers.gold_tier`）：按
  [CommonRouterBench](https://github.com/commonrouter-lab/CommonRouterBench)
  GT 档位做的 oracle 路由。只用来**做整条链路的自洽性校验**或者当「完美档
  位路由」的理论参考线，**不是**会拿去上榜的真实 router。

## 相关项目

- [CommonRouterBench](https://github.com/commonrouter-lab/CommonRouterBench)：上游静态路由 bench 与 GT 源。
- [SWERouterBench](https://github.com/commonrouter-lab/SWERouterBench)：editor scaffold 的动态路由 bench。
- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)：本仓依托的 scaffold。

## 许可

Apache-2.0。
