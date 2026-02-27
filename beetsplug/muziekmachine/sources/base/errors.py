# clients/errors.py
from __future__ import annotations


class ClientError(Exception):
    """Base class for all client-side errors."""


class ClientConfigError(ClientError):
    """Misconfiguration: missing tokens, bad endpoints, invalid options."""


class ClientAuthError(ClientError):
    """Authentication / authorization failed (401/403)."""


class ClientRateLimitError(ClientError):
    """Rate-limited by the remote service (429)."""
    def __init__(self, message: str = "Rate limited", retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ClientConnectionError(ClientError):
    """Network/connectivity problems (DNS, TLS, timeouts)."""


class ClientTemporaryError(ClientError):
    """Transient server error (5xx) that may succeed on retry."""


class ClientNotFoundError(ClientError):
    """Requested resource doesn't exist (404) or was removed."""


class ClientConflictError(ClientError):
    """Write/update conflict (409), e.g., version mismatch, ETag conflict."""


class ClientValidationError(ClientError):
    """Payload/schema invalid for the remote service."""


class ClientCapabilityError(ClientError):
    """Operation not supported by this client/source (e.g., read-only)."""


class ClientInvariantError(ClientError):
    """Logic invariant violated inside client (bug/assumption broken)."""


class ClientRequestError(ClientError):
    """hoi"""