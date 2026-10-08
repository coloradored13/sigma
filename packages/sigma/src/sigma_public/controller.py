"""A small durable controller; completion records evidence, not model confidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import sqlite3
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

from sigma_public_core import Scope, Transition, WorkflowDefinition, WorkflowStore
from sigma_public_memory import MemoryStore
from sigma_public_verify import Evidence, VerificationRequest, Verifier, check_quote

_IGNORED = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}


class RunError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def source_digest(directory: Path) -> str:
    """Hash file inputs, including untracked files, without emitting their contents.

    Tool caches and the Git database are excluded. Symlinks are unsupported, rather
    than silently claiming to have hashed inputs outside the selected directory.
    """
    if directory.is_symlink() or not directory.is_dir():
        raise RunError("workspace_unavailable")
    digest = hashlib.sha256()

    def walk_error(error: OSError) -> None:
        raise error

    try:
        for root, dirs, files in os.walk(directory, onerror=walk_error):
            dirs[:] = sorted(name for name in dirs if name not in _IGNORED)
            for name in dirs + sorted(files):
                path = Path(root) / name
                if path.is_symlink():
                    raise RunError("unsupported_symlink")
                relative = os.fsencode(path.relative_to(directory).as_posix())
                digest.update(len(relative).to_bytes(8, "big"))
                digest.update(relative)
                if path.is_dir():
                    digest.update(b"directory")
                    digest.update((path.stat().st_mode & 0o777).to_bytes(2, "big"))
                    continue
                if not path.is_file():
                    raise RunError("unsupported_file_type")
                digest.update(b"file")
                with path.open("rb") as stream:
                    before = os.fstat(stream.fileno())
                    file_hash = hashlib.file_digest(stream, "sha256").digest()
                    after = os.fstat(stream.fileno())
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RunError("workspace_unreadable_or_changed")
                digest.update((before.st_mode & 0o111).to_bytes(2, "big"))
                digest.update(file_hash)
    except OSError:
        raise RunError("workspace_unreadable_or_changed") from None
    return digest.hexdigest()


class Controller:
    def __init__(self, path: str | Path, scope: Scope, verifier: Verifier | None = None):
        self.path = Path(path).absolute()
        if self.path.is_symlink():
            raise RunError("runtime_symlink_forbidden")
        self.scope = scope
        self.verifier = verifier or Verifier()
        self.core = WorkflowStore(
            self.path,
            scope,
            WorkflowDefinition(
                "open",
                {
                    "complete": Transition({"open"}, "completed", lambda data: self._evaluate(data)[0] == "ready"),
                    "fail": Transition({"open"}, "failed", lambda data: self._evaluate(data)[0] == "failed"),
                    "stop": Transition({"open"}, "incomplete"),
                },
            ),
        )
        self.memory = MemoryStore(self.path, scope)
        with self._db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sigma_checks (
                    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, project TEXT NOT NULL,
                    run_id TEXT NOT NULL, name TEXT NOT NULL, started_ns INTEGER NOT NULL,
                    finished_ns INTEGER, program TEXT NOT NULL, command_digest TEXT NOT NULL,
                    before_digest TEXT NOT NULL, after_digest TEXT, return_code INTEGER,
                    reason TEXT, stdout_digest TEXT, stderr_digest TEXT
                );
                CREATE TABLE IF NOT EXISTS sigma_blockers (
                    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, project TEXT NOT NULL,
                    run_id TEXT NOT NULL, note TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS sigma_findings (
                    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, project TEXT NOT NULL,
                    run_id TEXT NOT NULL, memory_id TEXT NOT NULL, memory_version INTEGER NOT NULL,
                    quote_evidence_ids TEXT NOT NULL, verification TEXT NOT NULL,
                    limitations TEXT NOT NULL, evidence_json TEXT NOT NULL, quotation TEXT NOT NULL
                );
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @property
    def _scope_values(self) -> tuple[str, str]:
        return self.scope.tenant_id, self.scope.project_id

    def start(self, mode: str, workspace: str | Path, required_checks: list[str], budget_checks: int = 10):
        if mode not in {"analysis", "build"}:
            raise RunError("invalid_mode")
        if not isinstance(budget_checks, int) or isinstance(budget_checks, bool) or budget_checks < 1:
            raise RunError("invalid_budget")
        if not isinstance(required_checks, list) or any(
            not isinstance(name, str) or not name.strip() or len(name) > 128 for name in required_checks
        ):
            raise RunError("invalid_required_checks")
        if len(set(required_checks)) != len(required_checks):
            raise RunError("duplicate_required_checks")
        if mode == "build" and not required_checks:
            raise RunError("build_requires_checks")
        workspace = Path(workspace).resolve()
        if not workspace.is_dir():
            raise RunError("workspace_missing")
        if self.path.is_relative_to(workspace):
            raise RunError("runtime_store_must_be_outside_workspace")
        source_digest(workspace)
        run_id = str(uuid.uuid4())
        return self.core.create(run_id, {
            "run_id": run_id, "mode": mode, "workspace": str(workspace),
            "required_checks": required_checks, "budget_checks": budget_checks,
        })

    def _open(self, run_id: str):
        run = self.core.get(run_id)
        if run.state != "open":
            raise RunError("run_closed")
        return run

    def add_blocker(self, run_id: str, note: str) -> str:
        self._open(run_id)
        if not isinstance(note, str) or not note.strip():
            raise RunError("empty_blocker")
        blocker_id = str(uuid.uuid4())
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._open(run_id)
            conn.execute(
                "INSERT INTO sigma_blockers(id,tenant,project,run_id,note) VALUES(?,?,?,?,?)",
                (blocker_id, *self._scope_values, run_id, note),
            )
            conn.commit()
        return blocker_id

    def resolve_blocker(self, run_id: str, blocker_id: str) -> None:
        self._open(run_id)
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._open(run_id)
            cursor = conn.execute(
                "UPDATE sigma_blockers SET resolved=1 WHERE tenant=? AND project=? AND run_id=? AND id=?",
                (*self._scope_values, run_id, blocker_id),
            )
            if cursor.rowcount != 1:
                raise RunError("blocker_not_found")
            conn.commit()

    def record_finding(
        self, run_id: str, claim: str, evidence: tuple[Evidence, ...], quote: str, limitations: str,
    ) -> dict:
        self._open(run_id)
        if not limitations.strip():
            raise RunError("limitations_required")
        quote_result = check_quote(quote, evidence)
        if quote_result.status != "matched":
            raise RunError("quotation_not_found")
        request = VerificationRequest(claim, evidence)
        result = self.verifier.verify(request)
        record = self.memory.add(claim, source_ids=tuple(item.id for item in evidence))
        finding_id = str(uuid.uuid4())
        try:
            with self._db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._open(run_id)
                conn.execute(
                    "INSERT INTO sigma_findings VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (finding_id, *self._scope_values, run_id, record.id, record.version,
                     json.dumps(quote_result.evidence_ids), json.dumps(asdict(result)), limitations,
                     json.dumps([asdict(item) for item in evidence]), quote),
                )
                if result.status in {"blocked", "error", "malformed", "abstention"} or (
                    result.assessment == "contradicted"
                ):
                    conn.execute(
                        "INSERT INTO sigma_blockers(id,tenant,project,run_id,note) VALUES(?,?,?,?,?)",
                        (finding_id, *self._scope_values, run_id, f"Assess finding {finding_id}: {result.status}"),
                    )
                conn.commit()
        except Exception:
            self.memory.delete(record.id, expected_version=record.version)
            raise
        return {"id": finding_id, "memory_id": record.id, "quotation": asdict(quote_result),
                "verification": asdict(result), "truth_established": False}

    def run_check(
        self, run_id: str, name: str, argv: list[str], timeout: float = 30,
        max_output_bytes: int = 1_000_000,
    ) -> dict:
        run = self._open(run_id)
        if name not in run.data["required_checks"]:
            raise RunError("undeclared_check")
        if not isinstance(argv, list) or not argv or len(argv) > 256 or any(
            not isinstance(arg, str) or "\x00" in arg or len(arg) > 65536 for arg in argv
        ) or not argv[0]:
            raise RunError("invalid_command")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600 or (
            type(max_output_bytes) is not int or not 0 < max_output_bytes <= 100_000_000
        ):
            raise RunError("invalid_execution_limit")
        workspace = Path(run.data["workspace"])
        before = source_digest(workspace)
        check_id = str(uuid.uuid4())
        command_digest = hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute(
                "SELECT COUNT(*) FROM sigma_checks WHERE tenant=? AND project=? AND run_id=?",
                (*self._scope_values, run_id),
            ).fetchone()[0]
            if count >= run.data["budget_checks"]:
                conn.rollback()
                raise RunError("budget_exhausted")
            # Re-read state while the transaction excludes concurrent completion.
            if self.core.get(run_id).state != "open":
                conn.rollback()
                raise RunError("run_closed")
            conn.execute(
                "INSERT INTO sigma_checks(id,tenant,project,run_id,name,started_ns,program,command_digest,"
                "before_digest) VALUES(?,?,?,?,?,?,?,?,?)",
                (check_id, *self._scope_values, run_id, name, time.time_ns(), Path(argv[0]).name,
                 command_digest, before),
            )
            conn.commit()
        reason = "passed"
        return_code = None
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = None
            try:
                process = subprocess.Popen(
                    argv, cwd=workspace, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                    start_new_session=True,
                )
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    output_size = os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size
                    if time.monotonic() >= deadline or output_size > max_output_bytes:
                        reason = "timeout" if time.monotonic() >= deadline else "output_limit"
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        break
                    time.sleep(0.01)
                return_code = process.wait()
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > max_output_bytes:
                    reason = "output_limit"
                if reason == "passed" and return_code != 0:
                    reason = "command_failed"
            except OSError:
                reason = "launch_failed"
            finally:
                # Clean up on ordinary exit and Python cancellation as well.
                # Detached processes and SIGKILL require host process isolation.
                if process is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    if process.poll() is None:
                        process.wait()
            stdout.seek(0)
            stderr.seek(0)
            stdout_hash = hashlib.file_digest(stdout, "sha256").hexdigest()
            stderr_hash = hashlib.file_digest(stderr, "sha256").hexdigest()
        try:
            after = source_digest(workspace)
        except RunError:
            after = None
        if reason == "passed" and before != after:
            reason = "source_changed_during_check"
        with self._db() as conn:
            conn.execute(
                "UPDATE sigma_checks SET finished_ns=?,after_digest=?,return_code=?,reason=?,"
                "stdout_digest=?,stderr_digest=? WHERE id=? AND tenant=? AND project=? AND finished_ns IS NULL",
                (time.time_ns(), after, return_code, reason, stdout_hash, stderr_hash,
                 check_id, *self._scope_values),
            )
            return dict(conn.execute("SELECT * FROM sigma_checks WHERE id=?", (check_id,)).fetchone())

    def abandon_check(self, run_id: str, check_id: str, *, confirm_executor_stopped: bool = False) -> None:
        """Operator recovery after stopping an interrupted executor.

        Never infer that a receipt is abandoned merely from its age. The host must
        stop/reap the old process before authorizing a retry.
        """
        if confirm_executor_stopped is not True:
            raise RunError("executor_stop_confirmation_required")
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._open(run_id)
            cursor = conn.execute(
                "UPDATE sigma_checks SET finished_ns=?,reason='interrupted' WHERE id=? AND tenant=? "
                "AND project=? AND run_id=? AND finished_ns IS NULL",
                (time.time_ns(), check_id, *self._scope_values, run_id),
            )
            if cursor.rowcount != 1:
                raise RunError("pending_check_not_found")
            conn.commit()

    def _evaluate(self, data: dict) -> tuple[str, str]:
        run_id = data["run_id"]
        with self._db() as conn:
            blockers = conn.execute(
                "SELECT COUNT(*) FROM sigma_blockers WHERE tenant=? AND project=? AND run_id=? AND resolved=0",
                (*self._scope_values, run_id),
            ).fetchone()[0]
            checks = conn.execute(
                "SELECT * FROM sigma_checks WHERE tenant=? AND project=? AND run_id=? ORDER BY rowid",
                (*self._scope_values, run_id),
            ).fetchall()
            findings = conn.execute(
                "SELECT * FROM sigma_findings WHERE tenant=? AND project=? AND run_id=?",
                (*self._scope_values, run_id),
            ).fetchall()
        if blockers:
            return "incomplete", "unresolved_blockers"
        if any(row["finished_ns"] is None for row in checks):
            return "incomplete", "interrupted_or_running_check"
        latest = {row["name"]: row for row in checks}
        if any(name not in latest for name in data["required_checks"]):
            reason = "budget_exhausted" if len(checks) >= data["budget_checks"] else "required_checks_unrun"
            return "incomplete", reason
        if any(row["reason"] != "passed" for row in latest.values()):
            return "failed", "check_failed"
        try:
            current = source_digest(Path(data["workspace"]))
        except RunError:
            return "incomplete", "workspace_unavailable"
        if any(row["before_digest"] != current or row["after_digest"] != current for row in latest.values()):
            return "incomplete", "stale_check_receipt"
        if data["mode"] == "analysis":
            if not findings:
                return "incomplete", "no_findings"
            for finding in findings:
                try:
                    memory = self.memory.get(finding["memory_id"])
                except Exception:
                    return "incomplete", "finding_unavailable"
                if memory.version != finding["memory_version"]:
                    return "incomplete", "finding_changed"
            return "ready", "evidence_recorded_not_truth_verified"
        return "ready", "declared_checks_passed"

    def finish(self, run_id: str, *, stop: bool = False) -> dict:
        run = self._open(run_id)
        result, reason = self._evaluate(run.data)
        if result == "incomplete" and not stop and reason != "budget_exhausted":
            return self.inspect(run_id)
        action = "stop" if stop or result == "incomplete" else "fail" if result == "failed" else "complete"
        self.core.transition(
            run_id, action, expected_version=run.version,
            idempotency_key=f"finish:{run_id}:{run.version}:{action}", payload={"reason": reason},
        )
        return self.inspect(run_id)

    def inspect(self, run_id: str) -> dict:
        run = self.core.get(run_id)
        result, reason = self._evaluate(run.data)
        with self._db() as conn:
            checks = conn.execute(
                "SELECT id,name,reason FROM sigma_checks WHERE tenant=? AND project=? AND run_id=?",
                (*self._scope_values, run_id),
            ).fetchall()
            findings = conn.execute(
                "SELECT verification FROM sigma_findings WHERE tenant=? AND project=? AND run_id=?",
                (*self._scope_values, run_id),
            ).fetchall()
        return {"run_id": run.id, "mode": run.data["mode"], "status": run.state,
                "current_validation": result, "reason": reason,
                "completion_current": run.state == "completed" and result == "ready",
                "truth_established": False,
                "checks": [dict(row) for row in checks],
                "verification_statuses": [json.loads(row["verification"])["status"] for row in findings],
                "scope": {"tenant_id": self.scope.tenant_id, "project_id": self.scope.project_id}}
