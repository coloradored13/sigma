"""Independent failure probes for controller completion and execution boundaries."""

import sys
import time

import pytest
from sigma_public import Controller, RunError, source_digest
from sigma_public import controller as controller_module
from sigma_public_core import Scope, WorkflowError


@pytest.fixture
def controller(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return Controller(tmp_path / "runtime.db", Scope("review", "synthetic", "reviewer")), workspace


def ready_build(controller):
    app, workspace = controller
    run = app.start("build", workspace, ["test"])
    app.run_check(run.id, "test", [sys.executable, "-c", "pass"])
    return run


def test_missing_workspace_cannot_have_a_valid_source_digest(tmp_path):
    with pytest.raises(RunError):
        source_digest(tmp_path / "absent")


def test_symlink_workspace_root_cannot_have_a_valid_source_digest(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(RunError):
        source_digest(link)


def test_deleted_empty_workspace_invalidates_successful_receipt(controller):
    app, workspace = controller
    run = ready_build(controller)
    workspace.rmdir()
    result = app.finish(run.id)
    assert result["status"] != "completed"
    assert not result["completion_current"]


def test_string_is_not_an_explicit_argument_list(controller):
    app, workspace = controller
    run = app.start("build", workspace, ["test"])
    with pytest.raises(RunError):
        app.run_check(run.id, "test", "true")


@pytest.mark.parametrize("limits", [{"timeout": True}, {"max_output_bytes": True}, {"timeout": "30"}])
def test_command_limits_reject_ambiguous_types(controller, limits):
    app, workspace = controller
    run = app.start("build", workspace, ["test"])
    with pytest.raises(RunError):
        app.run_check(run.id, "test", [sys.executable, "-c", "pass"], **limits)


def test_closing_run_between_open_check_and_blocker_insert_rejects_write(controller, monkeypatch):
    app, _ = controller
    run = ready_build(controller)
    original_open = app._open

    def concurrently_close(run_id):
        found = original_open(run_id)
        monkeypatch.setattr(app, "_open", original_open)
        app.finish(run_id)
        return found

    monkeypatch.setattr(app, "_open", concurrently_close)
    with pytest.raises(RunError):
        app.add_blocker(run.id, "synthetic late blocker")
    assert app.inspect(run.id)["completion_current"]


def test_child_cannot_keep_mutating_workspace_after_check_returns(controller):
    app, workspace = controller
    run = app.start("build", workspace, ["test"])
    child = "import time; time.sleep(0.35); open('late-output', 'w').write('synthetic')"
    parent = f"import subprocess,sys; subprocess.Popen([sys.executable, '-c', {child!r}])"
    app.run_check(run.id, "test", [sys.executable, "-c", parent])
    time.sleep(0.5)
    assert not (workspace / "late-output").exists()


def test_executable_permission_change_invalidates_receipt(controller):
    app, workspace = controller
    script = workspace / "synthetic-check"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o700)
    run = app.start("build", workspace, ["test"])
    app.run_check(run.id, "test", [str(script)])
    script.chmod(0o600)
    assert app.inspect(run.id)["current_validation"] != "ready"


def test_clock_regression_cannot_hide_newer_failed_check(controller, monkeypatch):
    app, workspace = controller
    run = app.start("build", workspace, ["test"])
    monkeypatch.setattr(controller_module.time, "time_ns", lambda: 200)
    app.run_check(run.id, "test", [sys.executable, "-c", "pass"])
    monkeypatch.setattr(controller_module.time, "time_ns", lambda: 100)
    app.run_check(run.id, "test", [sys.executable, "-c", "raise SystemExit(1)"])
    assert app.finish(run.id)["status"] == "failed"


def test_controller_rejects_symlink_database_target(controller, tmp_path):
    app, _ = controller
    linked = tmp_path / "linked.db"
    linked.symlink_to(app.path)
    with pytest.raises((RunError, WorkflowError)):
        Controller(linked, app.scope)


def test_late_executor_cannot_overwrite_interrupted_receipt(controller, monkeypatch):
    app, workspace = controller
    run = app.start("build", workspace, ["test"])
    real_popen = controller_module.subprocess.Popen

    class CompletingProcess:
        def __init__(self, *args, **kwargs):
            self.process = real_popen(*args, **kwargs)
            self.pid = self.process.pid

        def poll(self):
            return self.process.poll()

        def wait(self):
            code = self.process.wait()
            check_id = app.inspect(run.id)["checks"][0]["id"]
            app.abandon_check(run.id, check_id, confirm_executor_stopped=True)
            return code

    monkeypatch.setattr(controller_module.subprocess, "Popen", CompletingProcess)
    receipt = app.run_check(run.id, "test", [sys.executable, "-c", "pass"])
    assert receipt["reason"] == "interrupted"
    assert app.inspect(run.id)["current_validation"] != "ready"
