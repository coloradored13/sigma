"""Explicit local execution; no legacy paths or credential discovery."""

import argparse
import json
import sys
from dataclasses import asdict

from sigma_public_core import Scope
from sigma_public_verify import Evidence

from .controller import Controller


def main() -> None:
    parser = argparse.ArgumentParser(description="Sigma Public local workflow controller (alpha)")
    parser.add_argument("--db", required=True, help="Explicit runtime database outside the project")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--actor", required=True)
    sub = parser.add_subparsers(dest="operation", required=True)
    start = sub.add_parser("start")
    start.add_argument("--mode", choices=["analysis", "build"], required=True)
    start.add_argument("--workspace", required=True)
    start.add_argument("--require", action="append", default=[])
    start.add_argument("--budget-checks", type=int, default=10)
    check = sub.add_parser("check")
    check.add_argument("run_id")
    check.add_argument("name")
    check.add_argument("--timeout", type=float, default=30)
    check.add_argument("command", nargs=argparse.REMAINDER)
    finding = sub.add_parser("finding")
    finding.add_argument("run_id")
    finding.add_argument("--claim", required=True)
    finding.add_argument("--source-id", required=True)
    finding.add_argument("--source", required=True)
    finding.add_argument("--evidence", required=True)
    finding.add_argument("--quote", required=True)
    finding.add_argument("--limitations", required=True)
    blocker = sub.add_parser("blocker")
    blocker.add_argument("run_id")
    blocker.add_argument("--note", required=True)
    resolve = sub.add_parser("resolve")
    resolve.add_argument("run_id")
    resolve.add_argument("blocker_id")
    recover = sub.add_parser("abandon-check")
    recover.add_argument("run_id")
    recover.add_argument("check_id")
    recover.add_argument("--executor-stopped", action="store_true")
    finish = sub.add_parser("finish")
    finish.add_argument("run_id")
    finish.add_argument("--stop", action="store_true")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("run_id")
    args = parser.parse_args()
    try:
        controller = Controller(args.db, Scope(args.tenant, args.project, args.actor))
        if args.operation == "start":
            output = asdict(controller.start(args.mode, args.workspace, args.require, args.budget_checks))
        elif args.operation == "check":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            output = controller.run_check(args.run_id, args.name, command, timeout=args.timeout)
        elif args.operation == "finding":
            evidence = (Evidence(args.source_id, args.evidence, args.source),)
            output = controller.record_finding(args.run_id, args.claim, evidence, args.quote, args.limitations)
        elif args.operation == "blocker":
            output = {"blocker_id": controller.add_blocker(args.run_id, args.note)}
        elif args.operation == "resolve":
            controller.resolve_blocker(args.run_id, args.blocker_id)
            output = {"resolved": True}
        elif args.operation == "abandon-check":
            controller.abandon_check(
                args.run_id, args.check_id, confirm_executor_stopped=args.executor_stopped,
            )
            output = {"marked_interrupted": True}
        elif args.operation == "finish":
            output = controller.finish(args.run_id, stop=args.stop)
        else:
            output = controller.inspect(args.run_id)
        print(json.dumps(output, indent=2))
        if args.operation == "check" and output["reason"] != "passed":
            sys.exit(1)
        if args.operation == "finish" and not output["completion_current"]:
            sys.exit(1)
    except Exception as exc:
        print(json.dumps({"error": getattr(exc, "code", "operation_failed")}), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
