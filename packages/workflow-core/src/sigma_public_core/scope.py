"""Trusted scope supplied by the host, never by an MCP tool argument."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    tenant_id: str
    project_id: str
    actor_id: str

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.project_id, self.actor_id):
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError("Scope identifiers must be nonempty strings of at most 128 characters")
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise ValueError("Scope identifiers must be valid Unicode") from None

    @property
    def namespace(self) -> tuple[str, str]:
        return self.tenant_id, self.project_id
