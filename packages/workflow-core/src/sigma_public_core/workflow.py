"""Atomic resource-bound state changes, without external side effects.

The configured Scope is a trusted host input. The host must control database file
access and supply authorization before constructing the store. Scope is a data
partition, not an authentication mechanism.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .errors import WorkflowError
from .scope import Scope


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise WorkflowError("invalid_request")
    return value


def _json(value: object) -> str:
    """Require actual JSON values; reject coercion of keys and non-finite numbers."""

    def check(item: object) -> None:
        if item is None or type(item) in (str, bool, int, float):
            return
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError
                check(child)
            return
        raise ValueError

    try:
        check(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise WorkflowError("invalid_request") from None


@dataclass(frozen=True, init=False)
class Transition:
    from_states: frozenset[str]
    to_state: str
    guard: Callable[[dict[str, Any]], bool] | None

    def __init__(
        self,
        from_states: Iterable[str],
        to_state: str,
        guard: Callable[[dict[str, Any]], bool] | None = None,
    ):
        if isinstance(from_states, str):
            raise WorkflowError("invalid_request")
        try:
            states = frozenset(_identifier(state) for state in from_states)
        except TypeError:
            raise WorkflowError("invalid_request") from None
        if not states or (guard is not None and not callable(guard)):
            raise WorkflowError("invalid_request")
        object.__setattr__(self, "from_states", states)
        object.__setattr__(self, "to_state", _identifier(to_state))
        object.__setattr__(self, "guard", guard)


@dataclass(frozen=True)
class WorkflowDefinition:
    initial_state: str
    transitions: Mapping[str, Transition]

    def __post_init__(self):
        _identifier(self.initial_state)
        if not isinstance(self.transitions, Mapping):
            raise WorkflowError("invalid_request")
        transitions = dict(self.transitions)
        for name, transition in transitions.items():
            _identifier(name)
            if not isinstance(transition, Transition):
                raise WorkflowError("invalid_request")
        object.__setattr__(self, "transitions", MappingProxyType(transitions))


@dataclass(frozen=True)
class Entity:
    id: str
    state: str
    version: int
    data: dict[str, Any]


@dataclass(frozen=True)
class TransitionReceipt:
    """Durable successful transition; retries return the original receipt.

    ``version`` is the resulting entity version. Payload is recorded as request
    metadata only; transitions never merge it into entity data or execute it.
    """

    id: str
    idempotency_key: str
    entity_id: str
    action: str
    actor_id: str
    from_state: str
    to_state: str
    version: int
    payload: dict[str, Any]
    created_at: str


class WorkflowStore:
    """SQLite store bound to one tenant/project, with an actor for receipts.

    Each operation uses a short-lived connection. Writes use BEGIN IMMEDIATE to
    serialize the target/version/guard check and state/event/receipt persistence.
    SQLite's busy timeout is 15 seconds. The definition and its pure guards are
    trusted host code; use one consistently configured definition per database
    namespace. There are no arbitrary transition handlers or external effects.
    New database files have owner-only permissions. Existing permissions are not
    changed; the host must secure the database and its enclosing directories.
    """

    def __init__(self, path: str | Path, scope: Scope, definition: WorkflowDefinition):
        if str(path) == ":memory:" or not isinstance(scope, Scope):
            raise WorkflowError("invalid_request")
        if not isinstance(definition, WorkflowDefinition):
            raise WorkflowError("invalid_request")
        self.path = Path(path)
        self.scope = scope
        self.definition = definition
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise WorkflowError("storage_error")
            finally:
                os.close(fd)
            with self._connection(write=True) as db:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS workflow_entities (
                        tenant_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        version INTEGER NOT NULL CHECK (version >= 0),
                        data_json TEXT NOT NULL,
                        PRIMARY KEY (tenant_id, project_id, entity_id)
                    )
                """)
                db.execute("""
                    CREATE TABLE IF NOT EXISTS workflow_receipts (
                        tenant_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        version INTEGER NOT NULL,
                        receipt_json TEXT NOT NULL,
                        PRIMARY KEY (tenant_id, project_id, idempotency_key),
                        UNIQUE (tenant_id, project_id, entity_id, version),
                        FOREIGN KEY (tenant_id, project_id, entity_id)
                            REFERENCES workflow_entities (tenant_id, project_id, entity_id)
                    )
                """)
        except OSError:
            raise WorkflowError("storage_error") from None

    @contextmanager
    def _connection(self, *, write: bool = False):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA synchronous = FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except sqlite3.Error:
            if db is not None:
                db.rollback()
            raise WorkflowError("storage_error") from None
        except BaseException:
            if db is not None:
                db.rollback()
            raise
        finally:
            if db is not None:
                db.close()

    def _load(self, db: sqlite3.Connection, entity_id: str) -> Entity:
        row = db.execute(
            "SELECT entity_id, state, version, data_json FROM workflow_entities "
            "WHERE tenant_id = ? AND project_id = ? AND entity_id = ?",
            (*self.scope.namespace, entity_id),
        ).fetchone()
        if row is None:
            raise WorkflowError("not_found")
        return Entity(row["entity_id"], row["state"], row["version"], json.loads(row["data_json"]))

    @staticmethod
    def _guard(transition: Transition, entity: Entity) -> bool:
        if transition.guard is None:
            return True
        try:
            # Mutation by a misbehaving guard cannot change persisted entity data.
            result = transition.guard(json.loads(_json(entity.data)))
            if type(result) is not bool:
                raise ValueError
            return result
        except Exception:
            raise WorkflowError("guard_error") from None

    def create(self, entity_id: str, data: dict[str, Any]) -> Entity:
        entity_id = _identifier(entity_id)
        if type(data) is not dict:
            raise WorkflowError("invalid_request")
        data_json = _json(data)
        with self._connection(write=True) as db:
            exists = db.execute(
                "SELECT 1 FROM workflow_entities WHERE tenant_id = ? AND project_id = ? AND entity_id = ?",
                (*self.scope.namespace, entity_id),
            ).fetchone()
            if exists is not None:
                raise WorkflowError("already_exists")
            db.execute(
                "INSERT INTO workflow_entities VALUES (?, ?, ?, ?, 0, ?)",
                (*self.scope.namespace, entity_id, self.definition.initial_state, data_json),
            )
            return self._load(db, entity_id)

    def get(self, entity_id: str) -> Entity:
        entity_id = _identifier(entity_id)
        with self._connection() as db:
            return self._load(db, entity_id)

    def allowed_actions(self, entity_id: str) -> list[str]:
        """Advisory discovery only: execution reloads and checks its actual target."""
        entity = self.get(entity_id)
        return sorted(
            name
            for name, transition in self.definition.transitions.items()
            if entity.state in transition.from_states and self._guard(transition, entity)
        )

    def transition(
        self,
        entity_id: str,
        action: str,
        expected_version: int,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
    ) -> TransitionReceipt:
        entity_id = _identifier(entity_id)
        action = _identifier(action)
        idempotency_key = _identifier(idempotency_key)
        if type(expected_version) is not int or expected_version < 0:
            raise WorkflowError("invalid_request")
        if payload is None:
            payload = {}
        if type(payload) is not dict:
            raise WorkflowError("invalid_request")
        request_json = _json({
            "actor_id": self.scope.actor_id,
            "entity_id": entity_id,
            "action": action,
            "expected_version": expected_version,
            "payload": payload,
        })
        # Freeze caller-owned mutable data before entering the transaction.
        payload = json.loads(request_json)["payload"]
        fingerprint = hashlib.sha256(request_json.encode()).hexdigest()
        with self._connection(write=True) as db:
            previous = db.execute(
                "SELECT fingerprint, receipt_json FROM workflow_receipts "
                "WHERE tenant_id = ? AND project_id = ? AND idempotency_key = ?",
                (*self.scope.namespace, idempotency_key),
            ).fetchone()
            if previous is not None:
                if previous["fingerprint"] != fingerprint:
                    raise WorkflowError("idempotency_conflict")
                return TransitionReceipt(**json.loads(previous["receipt_json"]))
            entity = self._load(db, entity_id)
            if entity.version != expected_version:
                raise WorkflowError("stale_version")
            transition = self.definition.transitions.get(action)
            if transition is None or entity.state not in transition.from_states:
                raise WorkflowError("action_not_allowed")
            if not self._guard(transition, entity):
                raise WorkflowError("guard_rejected")
            receipt = TransitionReceipt(
                id=str(uuid.uuid4()),
                idempotency_key=idempotency_key,
                entity_id=entity_id,
                action=action,
                actor_id=self.scope.actor_id,
                from_state=entity.state,
                to_state=transition.to_state,
                version=entity.version + 1,
                payload=payload,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            db.execute(
                "UPDATE workflow_entities SET state = ?, version = ? "
                "WHERE tenant_id = ? AND project_id = ? AND entity_id = ?",
                (receipt.to_state, receipt.version, *self.scope.namespace, entity_id),
            )
            db.execute(
                "INSERT INTO workflow_receipts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    *self.scope.namespace,
                    idempotency_key,
                    fingerprint,
                    entity_id,
                    receipt.version,
                    _json(receipt.__dict__),
                ),
            )
            return receipt

    def events(self, entity_id: str) -> list[TransitionReceipt]:
        """Return committed transitions ordered by entity version; creation is version 0."""
        entity_id = _identifier(entity_id)
        with self._connection() as db:
            self._load(db, entity_id)
            rows = db.execute(
                "SELECT receipt_json FROM workflow_receipts "
                "WHERE tenant_id = ? AND project_id = ? AND entity_id = ? ORDER BY version",
                (*self.scope.namespace, entity_id),
            ).fetchall()
            return [TransitionReceipt(**json.loads(row["receipt_json"])) for row in rows]
