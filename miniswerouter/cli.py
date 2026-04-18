"""MiniSWERouterBench command-line entrypoint.

Subcommands:

* ``run``     -- run a router on SWE-bench Verified via mini-swe-agent.
* ``score``   -- score an existing run directory using SWERouterBench's
                 scorer (same ``total_actual_bill_usd`` metric).
* ``render``  -- render a markdown leaderboard from one or more score files
                 using SWERouterBench's renderer.

Example::

    miniswerouterbench run \\
        --router-import swerouter.routers.gold_tier:GoldTierRouter.from_cli_args \\
        --router-arg question_bank_path=../CommonRouterBench/data/question_bank.jsonl \\
        --router-arg tier_to_model_path=../SWERouterBench/data/tier_to_model.json \\
        --router-arg allowed_instance_ids=django__django-11133 \\
        --router-arg label=gold_tier_oracle \\
        --router-label gold_tier_oracle \\
        --output-dir runs/mini_gt_one \\
        --instances django__django-11133 \\
        --max-steps 250 --budget-usd 3 --run-id mini_gt_one --force-rerun
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

from swerouter.router import Router


def _parse_router_args(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise ValueError(f"--router-arg expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        if not k:
            raise ValueError(f"--router-arg key empty in {p!r}")
        out[k] = v
    return out


def _instantiate_router(router_import: str, router_args: dict[str, str]) -> Router:
    """Import ``module:attr`` (or ``module:Attr.sub``) and call it."""

    if ":" not in router_import:
        raise ValueError(
            f"--router-import expects 'module:ClassOrFactory', got {router_import!r}"
        )
    module_name, attr_path = router_import.split(":", 1)
    if not attr_path:
        raise ValueError(
            f"--router-import attribute path is empty in {router_import!r}"
        )
    module = importlib.import_module(module_name)
    obj: object = module
    for part in attr_path.split("."):
        if not part:
            raise ValueError(
                f"--router-import attribute path has empty segment in {router_import!r}"
            )
        if not hasattr(obj, part):
            raise ValueError(
                f"{router_import!r}: object {type(obj).__name__} has no attribute {part!r}"
            )
        obj = getattr(obj, part)
    if not callable(obj):
        raise TypeError(
            f"--router-import {router_import!r} resolved to non-callable {type(obj).__name__}"
        )
    instance = obj(**router_args)
    if not hasattr(instance, "select") or not callable(instance.select):
        raise TypeError(
            f"{router_import!r} produced {type(instance).__name__}, which has no callable .select"
        )
    return instance


def _parse_max_steps_by_instance(
    json_literal: str | None, json_file: str | None
) -> dict[str, int] | None:
    """Load optional per-instance step cap override (same shape as SWERouterBench)."""

    if json_literal and json_file:
        raise ValueError("pass either --max-steps-json or --max-steps-json-file, not both")
    raw: str | None = None
    if json_literal:
        raw = json_literal
    elif json_file:
        raw = Path(json_file).read_text(encoding="utf-8")
    if raw is None:
        return None
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("--max-steps-json must decode to an object mapping instance_id -> int")
    out: dict[str, int] = {}
    for k, v in doc.items():
        if not isinstance(k, str) or not k:
            raise ValueError(f"--max-steps-json key must be non-empty string, got {k!r}")
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise ValueError(
                f"--max-steps-json[{k!r}] must be positive int, got {v!r}"
            )
        out[k] = v
    return out


def _cmd_run(args: argparse.Namespace) -> int:
    from miniswerouter.harness.run_eval import EvalRequest, run_eval

    router = _instantiate_router(args.router_import, _parse_router_args(args.router_arg))

    instance_ids: tuple[str, ...] | None = None
    if args.instances:
        instance_ids = tuple(i for i in args.instances if i)

    max_steps_by_instance = _parse_max_steps_by_instance(
        args.max_steps_json, args.max_steps_json_file
    )

    req = EvalRequest(
        router=router,
        base_url=args.base_url,
        api_key=args.api_key,
        output_dir=Path(args.output_dir),
        instance_ids=instance_ids,
        limit=args.limit,
        max_workers=args.workers,
        max_steps=args.max_steps,
        max_steps_by_instance=max_steps_by_instance,
        budget_usd=args.budget_usd,
        per_command_timeout_sec=args.per_command_timeout_sec,
        run_id=args.run_id,
        force_rerun=args.force_rerun,
        rm_image=args.rm_image,
    )
    summary = run_eval(req, router_label=args.router_label)
    print(
        json.dumps(
            {
                "router_label": summary.router_label,
                "resolved_count": summary.resolved_count,
                "resolved_rate": summary.resolved_rate,
                "completed": summary.completed,
                "total_router_cost_usd": summary.total_router_cost_usd,
                "pool_fingerprint": summary.pool_fingerprint,
                "pricing_schema_version": summary.pricing_schema_version,
            },
            indent=2,
        )
    )
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    # Delegate wholesale to SWERouterBench -- our results/*.json and
    # *.trace.jsonl schemas match byte-for-byte.
    from swerouter.leaderboard.score import score_run_dir

    score = score_run_dir(
        run_dir=Path(args.run_dir),
        router_label=args.router_label,
        pricing_path=Path(args.pricing) if args.pricing else None,
        ttl_path=Path(args.ttl) if args.ttl else None,
        pool_path=Path(args.pool) if args.pool else None,
    )
    out_path = Path(args.out) if args.out else Path(args.run_dir) / "score.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(score, fh, indent=2)
    print(
        json.dumps(
            {
                "router_label": score["router_label"],
                "total_actual_bill_usd": score["total_actual_bill_usd"],
                "resolved_count": score["resolved_count"],
                "resolved_rate": score["resolved_rate"],
                "instances": len(score["per_instance"]),
                "pricing_fingerprint": score["pricing_fingerprint"],
                "score_path": str(out_path),
            },
            indent=2,
        )
    )
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    from swerouter.leaderboard.render import render_leaderboard

    score_files = [Path(p) for p in args.score]
    markdown = render_leaderboard(score_files)
    out = Path(args.out) if args.out else None
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print(f"wrote {out}")
    else:
        sys.stdout.write(markdown)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="miniswerouterbench")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser(
        "run", help="Run a router on SWE-bench Verified via mini-swe-agent."
    )
    run.add_argument("--router-import", required=True, help="module:ClassOrFactory")
    run.add_argument(
        "--router-arg",
        action="append",
        default=[],
        help="key=value; may be repeated; passed as kwargs to the factory",
    )
    run.add_argument("--router-label", required=True)
    run.add_argument(
        "--base-url",
        default=os.environ.get("SWEROUTER_BASE_URL")
        or os.environ.get("OPENROUTER_BASE_URL"),
    )
    run.add_argument(
        "--api-key",
        default=os.environ.get("SWEROUTER_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY"),
    )
    run.add_argument("--output-dir", required=True)
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("--instances", nargs="*", default=None)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument(
        "--max-steps", type=int, default=250,
        help="step_limit passed to mini's DefaultAgent. Default matches mini's "
        "official SWE-bench config (step_limit=250). Tighter values are dev-time "
        "knobs for saving tokens; production leaderboard runs should leave the "
        "default in place.",
    )
    run.add_argument(
        "--max-steps-json",
        default=None,
        help="[DEV ONLY] Optional inline JSON mapping instance_id -> max_steps, e.g. "
        '\'{"django__django-11133": 8}\'. Missing keys fall back to --max-steps. '
        "Intended for debugging; production submissions should not use this.",
    )
    run.add_argument(
        "--max-steps-json-file",
        default=None,
        help="[DEV ONLY] Path to a JSON file with the same shape as --max-steps-json.",
    )
    run.add_argument(
        "--budget-usd", type=float, default=3.0,
        help="cost_limit passed to mini's DefaultAgent. Default matches mini's "
        "official SWE-bench config (cost_limit=3).",
    )
    run.add_argument(
        "--per-command-timeout-sec", type=int, default=None,
        help="Override the per-bash-command timeout (mini default 60s).",
    )
    run.add_argument("--run-id", default="miniswerouter_default")
    run.add_argument("--force-rerun", action="store_true")
    run.add_argument("--rm-image", action="store_true")
    run.set_defaults(func=_cmd_run)

    score = sub.add_parser("score", help="Score an existing run directory.")
    score.add_argument("--run-dir", required=True)
    score.add_argument("--router-label", required=True)
    score.add_argument("--pricing", default=None)
    score.add_argument("--ttl", default=None)
    score.add_argument("--pool", default=None)
    score.add_argument("--out", default=None)
    score.set_defaults(func=_cmd_score)

    render = sub.add_parser("render", help="Render a markdown leaderboard.")
    render.add_argument("--score", nargs="+", required=True)
    render.add_argument("--out", default=None)
    render.set_defaults(func=_cmd_render)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        missing = [k for k in ("base_url", "api_key") if not getattr(args, k)]
        if missing:
            parser.error(
                f"missing required connection settings: {missing}. Pass --base-url / --api-key "
                f"or set SWEROUTER_BASE_URL / SWEROUTER_API_KEY (or OPENROUTER_*)."
            )

    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
