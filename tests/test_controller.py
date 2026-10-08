"""Functional receipts and end-to-end behavior with synthetic projects only."""

import json
import sqlite3
import sys
import time

import pytest
from sigma_public import Controller, RunError, source_digest
from sigma_public_core import Scope, WorkflowError
from sigma_public_verify import Evidence, VerificationPolicy, Verifier


@pytest.fixture
def setup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n")
    db = tmp_path / "runtime" / "public.sqlite"
    controller = Controller(db, Scope("synthetic", "project-a", "operator"))
    return controller, project, db


def passing_command():
    return [sys.executable, "-B", "-c", "import app; assert app.answer == 42"]


def test_build_executes_real_behavior_and_survives_restart(setup):
    controller, project, db = setup
    run = controller.start("build", project, ["behavior"])
    receipt = controller.run_check(run.id, "behavior", passing_command())
    assert receipt["return_code"] == 0
    assert receipt["reason"] == "passed"
    restarted = Controller(db, controller.scope)
    assert restarted.finish(run.id)["completion_current"] is True
    assert restarted.inspect(run.id)["reason"] == "declared_checks_passed"


def test_missing_check_is_incomplete_and_can_continue(setup):
    controller, project, _ = setup
    run = controller.start("build", project, ["behavior"])
    result = controller.finish(run.id)
    assert result["status"] == "open"
    assert result["current_validation"] == "incomplete"
    controller.run_check(run.id, "behavior", passing_command())
    assert controller.finish(run.id)["status"] == "completed"


def test_failed_command_cannot_become_completed(setup):
    controller, project, _ = setup
    run = controller.start("build", project, ["behavior"])
    controller.run_check(run.id, "behavior", [sys.executable, "-c", "raise SystemExit(3)"])
    assert controller.finish(run.id)["status"] == "failed"


def test_newer_failure_overrides_old_pass_even_if_clock_moves_back(setup, monkeypatch):
    controller, project, _ = setup
    run = controller.start("build", project, ["behavior"])
    controller.run_check(run.id, "behavior", passing_command())
    monkeypatch.setattr(time, "time_ns", lambda: 1)
    controller.run_check(run.id, "behavior", [sys.executable, "-c", "raise SystemExit(1)"])
    assert controller.finish(run.id)["status"] == "failed"


def test_changes_after_check_invalidate_receipt(setup):
    controller, project, _ = setup
    run = controller.start("build", project, ["behavior"])
    controller.run_check(run.id, "behavior", passing_command())
    (project / "untracked.py").write_text("unverified = True")
    assert controller.finish(run.id)["reason"] == "stale_check_receipt"
    controller.run_check(run.id, "behavior", passing_command())
    assert controller.finish(run.id)["completion_current"]
    (project / "app.py").write_text("answer = 0")
    assert controller.inspect(run.id)["completion_current"] is False


def test_change_during_check_is_not_a_pass(setup):
    controller, project, _ = setup
    run = controller.start("build", project, ["behavior"])
    result = controller.run_check(run.id, "behavior", [
        sys.executable, "-c", "from pathlib import Path; Path('app.py').write_text('answer=0')",
    ])
    assert result["reason"] == "source_changed_during_check"
    assert controller.finish(run.id)["status"] == "failed"


def test_blocker_requires_resolution_even_when_tests_pass(setup):
    controller, project, _ = setup
    run = controller.start("build", project, ["behavior"])
    controller.run_check(run.id, "behavior", passing_command())
    blocker = controller.add_blocker(run.id, "SYNTHETIC: missing review of deployment")
    assert controller.finish(run.id)["reason"] == "unresolved_blockers"
    controller.resolve_blocker(run.id, blocker)
    assert controller.finish(run.id)["completion_current"]


def test_budget_exhaustion_remains_incomplete(setup):
    controller, project, _ = setup
    run = controller.start("build", project, ["a", "b"], budget_checks=1)
    controller.run_check(run.id, "a", passing_command())
    with pytest.raises(RunError, match="budget_exhausted"):
        controller.run_check(run.id, "b", passing_command())
    result = controller.finish(run.id)
    assert result["status"] == "incomplete"
    assert result["completion_current"] is False


def test_timeout_and_output_limit_cannot_pass(setup):
    controller, project, _ = setup
    run = controller.start("build", project, ["behavior"])
    result = controller.run_check(
        run.id, "behavior", [sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05,
    )
    assert result["reason"] == "timeout"
    result = controller.run_check(
        run.id, "behavior", [sys.executable, "-c", "print('x' * 100000)"], max_output_bytes=1000,
    )
    assert result["reason"] == "output_limit"


def test_private_output_and_argv_are_not_persisted(setup):
    controller, project, db = setup
    run = controller.start("build", project, ["behavior"])
    canary = "SYNTHETIC_PRIVATE_OUTPUT_9242"
    result = controller.run_check(run.id, "behavior", [sys.executable, "-c", f"print('{canary}')"])
    assert canary not in json.dumps(result)
    with sqlite3.connect(db) as connection:
        dump = "\n".join(connection.iterdump())
    assert canary not in dump


def test_analysis_uses_all_components_without_claiming_truth(setup):
    controller, project, db = setup
    run = controller.start("analysis", project, [])
    evidence = (Evidence("synthetic-manual", "The sample returns 42.", "synthetic://manual"),)
    finding = controller.record_finding(
        run.id, "The sample returns 42.", evidence, "returns 42", "Synthetic illustration only",
    )
    assert finding["quotation"]["status"] == "matched"
    assert finding["verification"]["status"] == "offline"
    assert controller.memory.get(finding["memory_id"]).source_ids == ("synthetic-manual",)
    with sqlite3.connect(db) as conn:
        saved_evidence, quotation = conn.execute(
            "SELECT evidence_json, quotation FROM sigma_findings WHERE id=?", (finding["id"],),
        ).fetchone()
    assert json.loads(saved_evidence) == [{
        "id": "synthetic-manual", "text": "The sample returns 42.", "source": "synthetic://manual",
    }]
    assert quotation == "returns 42"
    result = controller.finish(run.id)
    assert result["status"] == "completed"
    assert result["truth_established"] is False
    assert result["reason"] == "evidence_recorded_not_truth_verified"


def test_retracting_finding_invalidates_completion(setup):
    controller, project, _ = setup
    run = controller.start("analysis", project, [])
    finding = controller.record_finding(
        run.id, "Synthetic claim", (Evidence("s", "sample", "synthetic://s"),), "sample", "Uncertain",
    )
    controller.finish(run.id)
    record = controller.memory.get(finding["memory_id"])
    controller.memory.retract(record.id, expected_version=record.version)
    assert controller.inspect(run.id)["completion_current"] is False


def test_failed_optional_verification_creates_blocker(setup):
    controller, project, db = setup

    class MalformedAdapter:
        def assess(self, request):
            return "not json"

    verifier = Verifier(VerificationPolicy(
        external_enabled=True, provider="synthetic", model="test", endpoint="https://example.invalid/check",
        export_classification="public",
    ), MalformedAdapter())
    controller = Controller(db, controller.scope, verifier)
    run = controller.start("analysis", project, [])
    controller.record_finding(
        run.id, "Synthetic claim", (Evidence("s", "sample", "synthetic://s"),), "sample", "Uncertain",
    )
    assert controller.finish(run.id)["reason"] == "unresolved_blockers"
    assert controller.inspect(run.id)["verification_statuses"] == ["malformed"]


def test_scope_cannot_reuse_another_runs_receipts(setup):
    controller, project, db = setup
    run = controller.start("build", project, ["behavior"])
    controller.run_check(run.id, "behavior", passing_command())
    other = Controller(db, Scope("synthetic", "project-b", "operator"))
    with pytest.raises(WorkflowError):
        other.finish(run.id)


def test_interrupted_receipt_recovery_is_explicit(setup):
    controller, project, db = setup
    run = controller.start("build", project, ["behavior"])
    # Simulate the durable receipt left by an executor stopped before completion.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO sigma_checks(id,tenant,project,run_id,name,started_ns,program,command_digest,"
            "before_digest) VALUES(?,?,?,?,?,?,?,?,?)",
            ("interrupted", *controller.scope.namespace, run.id, "behavior", 0, "synthetic", "digest",
             source_digest(project)),
        )
    assert controller.finish(run.id)["reason"] == "interrupted_or_running_check"
    with pytest.raises(RunError, match="confirmation_required"):
        controller.abandon_check(run.id, "interrupted")
    restarted = Controller(db, controller.scope)
    restarted.abandon_check(run.id, "interrupted", confirm_executor_stopped=True)
    restarted.run_check(run.id, "behavior", passing_command())
    assert restarted.finish(run.id)["completion_current"]


def test_runtime_database_cannot_pollute_source_tree(setup):
    _, project, _ = setup
    controller = Controller(project / "public.sqlite", Scope("t", "p", "a"))
    with pytest.raises(RunError, match="outside_workspace"):
        controller.start("build", project, ["check"])


def test_digest_tracks_executable_bits(setup):
    _, project, _ = setup
    before = source_digest(project)
    (project / "app.py").chmod(0o700)
    assert source_digest(project) != before
