"""SQLite memory storage. The host selects a database and immutable project scope.

Stored text is untrusted material, never verified knowledge. Retraction hides a
record; deletion also clears its content and source references from the logical
store. Neither operation erases filesystem remnants, backups, or provider copies.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sigma_public_core.scope import Scope


class MemoryStoreError(Exception):
    """A storage error whose message contains no record content or path."""


class MemoryNotFound(MemoryStoreError):
    """Unknown, hidden, and other-project records are indistinguishable."""


class MemoryConflict(MemoryStoreError):
    """The caller's expected record version is stale."""


class MemoryValidationError(MemoryStoreError, ValueError):
    """Invalid input; error messages do not echo that input."""


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    content: str | None
    version: int
    source_ids: tuple[str, ...]
    status: str
    expires_at: float | None
    created_at: float
    updated_at: float
    created_by: str
    updated_by: str


class MemoryStore:
    """Bind storage to one trusted tenant/project; actor is an audit principal.

    Identifiers are SQL parameters, never filesystem components. Each operation uses
    its own connection; write transactions serialize updates and append metadata-only
    receipts atomically. No memory files, credentials, or environment are discovered.
    """

    def __init__(self, path: str | Path, scope: Scope):
        if not isinstance(scope, Scope):
            raise MemoryValidationError("A trusted scope is required")
        self.scope = scope
        if not isinstance(path, (str, Path)) or not str(path) or str(path) == ":memory:":
            raise MemoryValidationError("An explicit database file is required")
        self.path = Path(path).absolute()
        try:
            # Restrict newly created stores; do not silently change existing host permissions.
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise MemoryValidationError("A regular database file is required")
            finally:
                os.close(descriptor)
        except OSError:
            raise MemoryStoreError("Memory storage could not be opened") from None
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS sp_memory_records (
                    tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    content TEXT,
                    version INTEGER NOT NULL CHECK (version > 0),
                    source_ids TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('active', 'retracted', 'deleted')),
                    expires_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    created_by TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, project_id, id)
                );
                CREATE TABLE IF NOT EXISTS sp_memory_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    occurred_at REAL NOT NULL
                );
            """)

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous=FULL")
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except (sqlite3.Error, UnicodeError):
            raise MemoryStoreError("Memory storage operation failed") from None
        finally:
            if connection is not None:
                # Closing an uncommitted transaction rolls it back, including receipts.
                connection.close()

    @staticmethod
    def _content(content: str) -> str:
        if not isinstance(content, str) or not content.strip():
            raise MemoryValidationError("Memory content must be nonempty text")
        try:
            length = len(content.encode("utf-8"))
        except UnicodeError:
            raise MemoryValidationError("Memory content must be valid Unicode") from None
        if length > 1_000_000:
            raise MemoryValidationError("Memory content exceeds the size limit")
        return content

    @staticmethod
    def _sources(source_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        if not isinstance(source_ids, (tuple, list)) or len(source_ids) > 128:
            raise MemoryValidationError("Source references must be a bounded list of identifiers")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 512 for item in source_ids):
            raise MemoryValidationError("Source references must be nonempty identifiers")
        # Stable de-duplication does not infer independent evidence or confirmation.
        return tuple(dict.fromkeys(source_ids))

    @staticmethod
    def _expiry(expires_at: float | None) -> float | None:
        if expires_at is None:
            return None
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
            raise MemoryValidationError("Expiry must be a finite UTC Unix timestamp")
        try:
            value = float(expires_at)
        except (OverflowError, ValueError):
            raise MemoryValidationError("Expiry must be a finite UTC Unix timestamp") from None
        if not math.isfinite(value):
            raise MemoryValidationError("Expiry must be a finite UTC Unix timestamp")
        return value

    @staticmethod
    def _id(memory_id: str) -> None:
        if not isinstance(memory_id, str) or not memory_id or len(memory_id) > 128:
            raise MemoryValidationError("Invalid memory identifier")

    @staticmethod
    def _version(expected_version: int) -> None:
        if type(expected_version) is not int or expected_version < 1:
            raise MemoryValidationError("Expected version must be a positive integer")

    @staticmethod
    def _record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            content=row["content"],
            version=row["version"],
            source_ids=tuple(json.loads(row["source_ids"])),
            status=row["status"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by=row["created_by"],
            updated_by=row["updated_by"],
        )

    def _load(self, connection: sqlite3.Connection, memory_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sp_memory_records WHERE tenant_id=? AND project_id=? AND id=?",
            (*self.scope.namespace, memory_id),
        ).fetchone()
        if row is None or row["status"] == "deleted":
            raise MemoryNotFound("Memory record is unavailable")
        return row

    @staticmethod
    def _visible(row: sqlite3.Row, now: float) -> bool:
        return row["status"] == "active" and (row["expires_at"] is None or row["expires_at"] > now)

    def _receipt(
        self, connection: sqlite3.Connection, memory_id: str, version: int, action: str, now: float
    ) -> None:
        connection.execute(
            "INSERT INTO sp_memory_events "
            "(tenant_id, project_id, memory_id, version, action, actor_id, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*self.scope.namespace, memory_id, version, action, self.scope.actor_id, now),
        )

    def add(
        self, content: str, source_ids: tuple[str, ...] = (), expires_at: float | None = None
    ) -> MemoryRecord:
        content, sources, expiry = self._content(content), self._sources(source_ids), self._expiry(expires_at)
        memory_id, now = str(uuid.uuid4()), time.time()
        with self._connection(write=True) as connection:
            connection.execute(
                "INSERT INTO sp_memory_records VALUES (?, ?, ?, ?, 1, ?, 'active', ?, ?, ?, ?, ?)",
                (
                    *self.scope.namespace,
                    memory_id,
                    content,
                    json.dumps(sources),
                    expiry,
                    now,
                    now,
                    self.scope.actor_id,
                    self.scope.actor_id,
                ),
            )
            self._receipt(connection, memory_id, 1, "add", now)
            return self._record(self._load(connection, memory_id))

    def get(self, memory_id: str) -> MemoryRecord:
        self._id(memory_id)
        with self._connection() as connection:
            row = self._load(connection, memory_id)
            if not self._visible(row, time.time()):
                raise MemoryNotFound("Memory record is unavailable")
            return self._record(row)

    def search(self, query: str, limit: int = 20) -> list[MemoryRecord]:
        if not isinstance(query, str) or len(query) > 1024:
            raise MemoryValidationError("Search query must be bounded text")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise MemoryValidationError("Search limit must be between 1 and 100")
        # instr treats wildcard and SQL-looking text literally, including empty queries.
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM sp_memory_records WHERE tenant_id=? AND project_id=? "
                "AND status='active' AND (expires_at IS NULL OR expires_at>?) "
                "AND instr(lower(content), lower(?)) > 0 ORDER BY created_at, id LIMIT ?",
                (*self.scope.namespace, time.time(), query, limit),
            ).fetchall()
            return [self._record(row) for row in rows]

    def revise(
        self, memory_id: str, expected_version: int, content: str, source_ids: tuple[str, ...] = ()
    ) -> MemoryRecord:
        return self._mutate(
            memory_id, expected_version, "revise", self._content(content), self._sources(source_ids)
        )

    def retract(self, memory_id: str, expected_version: int) -> MemoryRecord:
        return self._mutate(memory_id, expected_version, "retract")

    def delete(self, memory_id: str, expected_version: int) -> MemoryRecord:
        return self._mutate(memory_id, expected_version, "delete")

    def _mutate(
        self,
        memory_id: str,
        expected_version: int,
        action: str,
        content: str | None = None,
        sources: tuple[str, ...] = (),
    ) -> MemoryRecord:
        self._id(memory_id)
        self._version(expected_version)
        with self._connection(write=True) as connection:
            row = self._load(connection, memory_id)
            now = time.time()
            if action == "revise" and not self._visible(row, now):
                raise MemoryNotFound("Memory record is unavailable")
            if row["version"] != expected_version:
                raise MemoryConflict("Memory version conflict")
            if action == "retract" and row["status"] != "active":
                raise MemoryNotFound("Memory record is unavailable")
            version = row["version"] + 1
            new_content = content if action == "revise" else row["content"]
            new_sources = json.dumps(sources) if action == "revise" else row["source_ids"]
            status, expiry = row["status"], row["expires_at"]
            if action == "retract":
                status = "retracted"
            if action == "delete":
                new_content, new_sources, status, expiry = None, "[]", "deleted", None
            connection.execute(
                "UPDATE sp_memory_records SET content=?, source_ids=?, status=?, expires_at=?, "
                "version=?, updated_at=?, updated_by=? WHERE tenant_id=? AND project_id=? AND id=?",
                (
                    new_content,
                    new_sources,
                    status,
                    expiry,
                    version,
                    now,
                    self.scope.actor_id,
                    *self.scope.namespace,
                    memory_id,
                ),
            )
            self._receipt(connection, memory_id, version, action, now)
            return MemoryRecord(
                memory_id,
                new_content if action == "revise" else None,
                version,
                tuple(json.loads(new_sources)) if action == "revise" else (),
                status,
                expiry,
                row["created_at"],
                now,
                row["created_by"],
                self.scope.actor_id,
            )
