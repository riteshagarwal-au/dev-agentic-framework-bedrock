"""Secrets retrieval helpers for DAF Phase 1.

Requirement 11.2: "ALL credentials (GitHub token, Azure service principal,
registry credentials) SHALL be stored in AWS Secrets Manager and injected
at tool-call time only."

Requirement 11.3: "CREDENTIALS SHALL NOT appear in prompts, context,
memory, or logs at any point."

See `daf.secrets.credentials` for the `CredentialsClient` implementation.
"""

from daf.secrets.credentials import (
    CredentialError,
    CredentialName,
    CredentialNotConfiguredError,
    CredentialRetrievalError,
    CredentialsClient,
)

__all__ = [
    "CredentialError",
    "CredentialName",
    "CredentialNotConfiguredError",
    "CredentialRetrievalError",
    "CredentialsClient",
]
