"""End-to-end runner for one SWE-bench Verified instance on the mini scaffold.

Flow (mirrors SWERouterBench's ``swerouter.harness.run_instance`` but swaps
the editor-scaffold agent loop for mini-swe-agent's ``DefaultAgent`` +
``bash``-only action space):

1. Load the dataset row + build a ``test_spec`` via
   :mod:`swerouter.harness.container_runner` (shared with SWERouterBench so
   the container lifecycle is identical).
2. Start the SWE-bench work container.
3. Construct the three bridges: :class:`RouterAwareModel`,
   :class:`SwebenchContainerEnv`, :class:`MiniRouterAgent`.
4. ``agent.run(task=problem_statement)`` -- mini's scaffold drives bash-only
   steps until ``COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`` or ``step_limit`` /
   ``cost_limit`` fires.
5. Prefer mini's own ``submission`` (the text emitted after the sentinel) as
   the patch; fall back to ``extract_git_diff`` on the container so budget
   overruns still get graded on whatever changes were made.
6. Hand the patch to upstream's official evaluator via
   :func:`swerouter.harness.container_runner.run_upstream_eval`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from swerouter.agent.loop import ModelPoolEntry, load_model_pool
from swerouter.cache import TTLPolicy
from swerouter.harness.container_runner import (
    DEFAULT_DATASET_NAME,
    DEFAULT_DATASET_SPLIT,
    DEFAULT_EVAL_MODEL_NAME,
    DEFAULT_IMAGE_NAMESPACE,
    SwebenchContainerHandle,
    extract_git_diff,
    load_dataset_instance,
    make_test_spec_for_instance,
    run_upstream_eval,
)
from swerouter.pricing import PricingTable, load_pricing_table
from swerouter.router import Router

from miniswerouter.agent.agent import MiniRouterAgent
from miniswerouter.agent.model import RouterAwareModel
from miniswerouter.agent.prompts import (
    FORMAT_ERROR_TEMPLATE,
    INSTANCE_TEMPLATE,
    MINI_SWEBENCH_ENV_DEFAULTS,
    OBSERVATION_TEMPLATE,
    SYSTEM_TEMPLATE,
)
from miniswerouter.harness.env import (
    SwebenchContainerEnv,
    SwebenchContainerEnvConfig,
)


# By default we route all traffic through SWERouterBench's locked data files
# so the two benches share one pool + pricing + TTL source of truth. Callers
# can override via RunInstanceRequest.{pool,pricing,ttl}_path.
import swerouter  # noqa: E402  (used only to locate data files on disk)

_SWEROUTER_ROOT = Path(swerouter.__file__).resolve().parent.parent
DEFAULT_POOL = _SWEROUTER_ROOT / "data" / "model_pool.json"
DEFAULT_PRICING = _SWEROUTER_ROOT / "data" / "model_pricing.json"
DEFAULT_TTL = _SWEROUTER_ROOT / "data" / "ttl_policy.json"

# mini's CLI default for the eval model name sub-dir; we keep SWERouterBench's
# value so leaderboard reports converge.
MINI_EVAL_MODEL_NAME = DEFAULT_EVAL_MODEL_NAME


@dataclass
class RunInstanceRequest:
    """All inputs needed to run one instance on the mini scaffold."""

    instance_id: str
    router: Router
    base_url: str
    api_key: str
    output_dir: Path
    dataset_name: str = DEFAULT_DATASET_NAME
    dataset_split: str = DEFAULT_DATASET_SPLIT
    pool_path: Path = DEFAULT_POOL
    pricing_path: Path = DEFAULT_PRICING
    ttl_path: Path = DEFAULT_TTL
    # Defaults match mini-swe-agent's official SWE-bench config
    # (``minisweagent/config/benchmarks/swebench.yaml``: step_limit=250,
    # cost_limit=3). Dev harnesses that want to run tighter (to save tokens
    # or isolate step-count-sensitive behaviour) override via
    # ``EvalRequest.max_steps`` / ``max_steps_by_instance`` in the library
    # API, or ``--max-steps`` / ``--max-steps-json`` on the CLI.
    max_steps: int = 250
    budget_usd: float = 3.0
    per_command_timeout_sec: int | None = None
    select_timeout_sec: float = 30.0
    run_id: str = "miniswerouter_default"
    eval_timeout_sec: int = 1800
    force_rebuild: bool = False
    rm_image: bool = False
    image_namespace: str | None = DEFAULT_IMAGE_NAMESPACE
    # Extra litellm model_kwargs forwarded to every pool member's LitellmModel.
    # Callers typically leave this empty; mini's canonical defaults
    # (``drop_params=True, temperature=0.0, parallel_tool_calls=True``) are
    # pre-populated below so we stay wire-compatible with stock mini.
    default_model_kwargs: Mapping[str, Any] = field(
        default_factory=lambda: {
            "drop_params": True,
            "temperature": 0.0,
            "parallel_tool_calls": True,
        }
    )


@dataclass
class InstanceResult:
    """Single-instance output. Schema matches SWERouterBench's so that
    :func:`swerouter.leaderboard.score.score_run_dir` consumes the same
    JSON without modification.
    """

    instance_id: str
    resolved: bool
    patch: str | None
    patch_applied: bool
    trace_path: Path
    step_count: int
    total_router_cost_usd: float
    finished_by: str
    model_distribution: dict[str, int]
    agent_error: str | None
    eval_error: str | None
    eval_report_path: Path | None
    pool_fingerprint: str
    pricing_schema_version: int
    ttl_policy_name: str
    fail_to_pass_pass_count: int | None = None
    fail_to_pass_fail_count: int | None = None
    pass_to_pass_pass_count: int | None = None
    pass_to_pass_fail_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _pool_fingerprint(pool: list[ModelPoolEntry]) -> str:
    sorted_ids = sorted(p.model_id for p in pool)
    return "|".join(sorted_ids)


def _build_env_config(request: RunInstanceRequest) -> SwebenchContainerEnvConfig:
    """Materialize ``SwebenchContainerEnvConfig`` from mini's SWE-bench defaults.

    Per-command timeout can be overridden via the request.
    """

    cfg_dict = {
        **MINI_SWEBENCH_ENV_DEFAULTS,
    }
    if request.per_command_timeout_sec is not None:
        cfg_dict["timeout"] = int(request.per_command_timeout_sec)
    return SwebenchContainerEnvConfig(
        cwd=cfg_dict["cwd"],
        env=dict(cfg_dict["env"]),
        forward_env=[],
        timeout=int(cfg_dict["timeout"]),
        interpreter=list(cfg_dict["interpreter"]),
    )


def run_instance(request: RunInstanceRequest) -> InstanceResult:
    """Drive one SWE-bench Verified instance end-to-end on the mini scaffold."""

    output_dir = Path(request.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / f"{request.instance_id}.trace.jsonl"
    traj_path = output_dir / f"{request.instance_id}.mini_traj.json"

    pool = load_model_pool(request.pool_path)
    pricing = load_pricing_table(request.pricing_path)
    ttl = TTLPolicy.load(request.ttl_path)
    for entry in pool:
        if entry.model_id not in pricing:
            raise ValueError(
                f"pool model {entry.model_id!r} missing from pricing "
                f"table schema v{pricing.schema_version}"
            )

    instance = load_dataset_instance(
        request.instance_id,
        dataset_name=request.dataset_name,
        dataset_split=request.dataset_split,
    )
    test_spec = make_test_spec_for_instance(
        instance, image_namespace=request.image_namespace
    )

    handle = SwebenchContainerHandle(
        test_spec=test_spec,
        run_id=request.run_id,
        log_path=output_dir / "agent_logs" / request.instance_id / "agent.log",
        force_rebuild=request.force_rebuild,
    )

    agent_error: str | None = None
    patch_text = ""
    step_count = 0
    total_router_cost_usd = 0.0
    finished_by = "error_before_loop"
    model_distribution: dict[str, int] = {}

    try:
        handle.start()
        try:
            env = SwebenchContainerEnv(
                handle=handle, config=_build_env_config(request)
            )
            model = RouterAwareModel(
                pool=pool,
                pricing=pricing,
                base_url=request.base_url,
                api_key=request.api_key,
                default_model_kwargs=request.default_model_kwargs,
                observation_template=OBSERVATION_TEMPLATE,
                format_error_template=FORMAT_ERROR_TEMPLATE,
            )
            agent = MiniRouterAgent(
                model=model,
                env=env,
                router=request.router,
                instance_id=request.instance_id,
                trace_path=trace_path,
                ttl=ttl,
                budget_usd=request.budget_usd,
                select_timeout_sec=request.select_timeout_sec,
                system_template=SYSTEM_TEMPLATE,
                instance_template=INSTANCE_TEMPLATE,
                step_limit=request.max_steps,
                cost_limit=request.budget_usd,
                output_path=traj_path,
            )
            run_result = agent.run(task=str(instance.get("problem_statement", "")))
            submission = run_result.get("submission", "") if isinstance(run_result, Mapping) else ""
            step_count = agent.n_calls
            total_router_cost_usd = sum(s.step_cost_usd for s in model.step_log)
            for s in model.step_log:
                model_distribution[s.model_id] = model_distribution.get(s.model_id, 0) + 1
            finished_by = (
                run_result.get("exit_status", "unknown")
                if isinstance(run_result, Mapping)
                else "unknown"
            )

            # Prefer mini's own submission; fall back to whole-repo git diff
            # if the agent exited without submitting (budget/step cap).
            # ``patch.txt`` is the intermediate file mini's submission
            # protocol writes (see the SYSTEM/INSTANCE templates: the agent
            # runs ``git diff -- ... > patch.txt`` before echoing the
            # sentinel). Exclude it from the fallback diff so half-completed
            # submissions don't leak plumbing into the captured patch.
            if submission.strip():
                patch_text = submission
            else:
                patch_text = extract_git_diff(
                    handle.container, exclude_paths=("patch.txt",)
                )
        except Exception as ex:
            agent_error = f"{type(ex).__name__}: {ex}"
            # Best-effort fallback: if we already entered the container, try
            # to capture any changes the agent made before crashing.
            if handle.container is not None:
                try:
                    patch_text = extract_git_diff(
                        handle.container, exclude_paths=("patch.txt",)
                    )
                except Exception:  # noqa: BLE001
                    patch_text = ""
    finally:
        handle.stop()

    eval_report = run_upstream_eval(
        test_spec=test_spec,
        instance_id=request.instance_id,
        patch_text=patch_text,
        run_id=request.run_id,
        timeout_sec=request.eval_timeout_sec,
        rm_image=request.rm_image,
        model_name=MINI_EVAL_MODEL_NAME,
    )

    return InstanceResult(
        instance_id=request.instance_id,
        resolved=eval_report.resolved,
        patch=patch_text or None,
        patch_applied=eval_report.patch_applied,
        trace_path=trace_path,
        step_count=step_count,
        total_router_cost_usd=total_router_cost_usd,
        finished_by=finished_by,
        model_distribution=model_distribution,
        agent_error=agent_error,
        eval_error=eval_report.error,
        eval_report_path=eval_report.report_path,
        pool_fingerprint=_pool_fingerprint(pool),
        pricing_schema_version=pricing.schema_version,
        ttl_policy_name=ttl.policy_name,
        fail_to_pass_pass_count=eval_report.test_counts.get("FAIL_TO_PASS.success"),
        fail_to_pass_fail_count=eval_report.test_counts.get("FAIL_TO_PASS.failure"),
        pass_to_pass_pass_count=eval_report.test_counts.get("PASS_TO_PASS.success"),
        pass_to_pass_fail_count=eval_report.test_counts.get("PASS_TO_PASS.failure"),
        extra={
            "instance_repo": instance.get("repo", ""),
            "mini_trajectory_path": str(traj_path),
        },
    )


__all__ = [
    "RunInstanceRequest",
    "InstanceResult",
    "run_instance",
    "DEFAULT_DATASET_NAME",
    "DEFAULT_DATASET_SPLIT",
    "DEFAULT_POOL",
    "DEFAULT_PRICING",
    "DEFAULT_TTL",
    "MINI_EVAL_MODEL_NAME",
]
