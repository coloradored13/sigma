"""Synthetic end-to-end demo. Never reads legacy settings or calls a provider."""

import json
import sys
import tempfile
from pathlib import Path

from sigma_public import Controller
from sigma_public_core import Scope, Transition, WorkflowDefinition, WorkflowError, WorkflowStore
from sigma_public_verify import Evidence


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sigma-public-example-") as temporary:
        base = Path(temporary)
        project = base / "synthetic-project"
        project.mkdir()
        (project / "app.py").write_text("def answer():\n    return 42\n")
        scope = Scope("synthetic", "example", "demo-operator")
        orders = WorkflowStore(base / "orders.sqlite", scope, WorkflowDefinition("pending", {
            "approve": Transition({"pending"}, "approved"),
            "ship": Transition({"approved"}, "shipped"),
            "refund": Transition({"shipped"}, "refunded", lambda data: data["total"] < 500),
        }))
        orders.create("A", {"total": 999})
        orders.create("B", {"total": 25})
        orders.transition("A", "approve", expected_version=0, idempotency_key="approve-a")
        orders.transition("A", "ship", expected_version=1, idempotency_key="ship-a")
        orders.get("A")  # Viewing shipped A must not affect pending B's eligibility.
        orders.transition("B", "approve", expected_version=0, idempotency_key="approve-b")
        try:
            orders.transition("A", "approve", expected_version=2, idempotency_key="invalid-approve-a")
        except WorkflowError:
            shipped_approval_blocked = True
        else:
            raise AssertionError("Shipped order was approved")
        try:
            orders.transition("A", "refund", expected_version=2, idempotency_key="invalid-refund-a")
        except WorkflowError:
            expensive_refund_blocked = True
        else:
            raise AssertionError("Guard was evaluated against the wrong order")
        controller = Controller(base / "sigma-public.sqlite", scope)
        analysis = controller.start("analysis", project, [])
        controller.record_finding(
            analysis.id, "The synthetic function returns 42.",
            (Evidence("example-source", "def answer():\n    return 42\n", "synthetic://app.py"),),
            "return 42", "One synthetic example; quotation matching does not establish general correctness.",
        )
        analysis_result = controller.finish(analysis.id)
        build = controller.start("build", project, ["behavior"])
        receipt = controller.run_check(build.id, "behavior", [
            sys.executable, "-B", "-c", "from app import answer; assert answer() == 42",
        ])
        build_result = controller.finish(build.id)
        assert receipt["reason"] == "passed" and build_result["completion_current"]
        print(json.dumps({
            "lateral_approval": orders.get("B").state,
            "shipped_approval_blocked": shipped_approval_blocked,
            "expensive_refund_blocked": expensive_refund_blocked,
            "analysis": analysis_result,
            "build": build_result,
            "external_provider_calls": 0,
        }, indent=2))


if __name__ == "__main__":
    main()
