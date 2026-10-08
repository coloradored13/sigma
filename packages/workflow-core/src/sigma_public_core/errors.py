"""Stable, content-free workflow errors suitable for transport boundaries."""


class WorkflowError(Exception):
    """An operation failed with a stable code and no caller-supplied content."""

    _MESSAGES = {
        "invalid_request": "Invalid workflow request",
        "not_found": "Entity not found",
        "already_exists": "Entity already exists",
        "stale_version": "Entity version changed",
        "action_not_allowed": "Action is not available for this entity",
        "guard_rejected": "Action guard rejected this entity",
        "guard_error": "Action guard could not be evaluated",
        "idempotency_conflict": "Idempotency key was used for another request",
        "storage_error": "Workflow storage operation failed",
    }

    def __init__(self, code: str):
        self.code = code
        super().__init__(self._MESSAGES[code])
