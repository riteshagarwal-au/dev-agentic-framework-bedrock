"""AWS Secrets Manager credential retrieval helper.

design.md "Security Considerations":
    "Secrets (GitHub token, Azure SP, registry creds) live only in Secrets
    Manager, injected at tool-call time — never in prompts/context/memory/logs."

Requirement 11.2: "ALL credentials (GitHub token, Azure service principal,
registry credentials) SHALL be stored in AWS Secrets Manager and injected
at tool-call time only."

Requirement 11.3: "CREDENTIALS SHALL NOT appear in prompts, context,
memory, or logs at any point."

Design choices, to satisfy both requirements together:

- `CredentialsClient` never caches a raw secret value across calls. Every
  `get_secret`/`get_secret_fields`/`get_credential` call makes a fresh
  `GetSecretValue` request, so a credential is only ever "live" for the
  duration of the call that needs it (Requirement 11.2, "injected at
  tool-call time only").
- Secret *names*/*ARNs* are never hardcoded in this module. Callers either
  pass the Secrets Manager name/ARN directly (`get_secret`,
  `get_secret_fields`) or configure a small `CredentialName -> secret
  name/ARN` mapping on construction (`get_credential`) — Task 4.3's
  Terraform-provisioned secret resources are the actual source of those
  names/ARNs at deploy time, not this module.
- Every retrieved value is wrapped in Pydantic's `SecretStr` before it is
  returned. `SecretStr.__repr__`/`__str__` always render as
  `SecretStr('**********')` regardless of the wrapped value, so passing a
  `SecretStr` to a log statement, an f-string, or `print()` cannot leak
  the raw value by accident — the caller must explicitly call
  `.get_secret_value()` to obtain the raw string. This module never does
  that itself except to hand the value directly to its caller.
- Log statements in this module only ever include the secret's *name*/
  *identifier* (and, on error, the AWS error code) — never the fetched
  value, never the raw `GetSecretValueOutput`.
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from typing import Any, Protocol

from pydantic import SecretStr

logger = logging.getLogger(__name__)


class SecretsManagerClientProtocol(Protocol):
    """The subset of `boto3.client("secretsmanager")`'s interface this
    module depends on. Typed as a `Protocol` (rather than importing
    boto3's client type directly, which requires the optional
    `boto3-stubs`/`mypy-boto3-secretsmanager` packages) so any object with
    a matching `get_secret_value` method — the real boto3 client, or a
    test mock/stub — satisfies the type.
    """

    def get_secret_value(self, SecretId: str) -> dict[str, Any]: ...


class CredentialName(StrEnum):
    """Logical credential identifiers Requirement 11.2 names explicitly.

    This enum identifies *which* credential a caller wants, not *where* it
    lives in Secrets Manager — the actual secret name/ARN for each is
    supplied by the caller via `CredentialsClient`'s `secret_name_map`
    (Task 4.3 provisions the underlying Secrets Manager resources).
    """

    GITHUB_TOKEN = "GITHUB_TOKEN"
    AZURE_SERVICE_PRINCIPAL = "AZURE_SERVICE_PRINCIPAL"
    REGISTRY_CREDENTIALS = "REGISTRY_CREDENTIALS"


class CredentialError(Exception):
    """Base class for credential retrieval errors.

    Deliberately carries only the secret's *name*/identifier in its
    message — never the (possibly partially fetched) secret value — so
    that an uncaught exception traceback/log cannot leak a credential
    either (Requirement 11.3).
    """

    def __init__(self, secret_name: str, message: str) -> None:
        self.secret_name = secret_name
        super().__init__(message)


class CredentialNotConfiguredError(CredentialError):
    """Raised by `get_credential` when the requested `CredentialName` has
    no entry in the client's configured `secret_name_map`.
    """

    def __init__(self, credential_name: CredentialName) -> None:
        super().__init__(
            secret_name=str(credential_name),
            message=(
                f"No Secrets Manager secret name/ARN configured for credential {credential_name!r}"
            ),
        )
        self.credential_name = credential_name


class CredentialRetrievalError(CredentialError):
    """Raised when Secrets Manager itself fails to return a secret value
    (not found, access denied, throttled, etc.). Wraps the underlying
    `botocore.exceptions.ClientError`/`ValueError` without including any
    secret value in this exception's own message.
    """

    def __init__(self, secret_name: str, reason: str, cause: Exception | None = None) -> None:
        super().__init__(
            secret_name=secret_name,
            message=f"Failed to retrieve secret {secret_name!r}: {reason}",
        )
        self.__cause__ = cause


class CredentialsClient:
    """Fetches credentials from AWS Secrets Manager at call time only.

    Wraps `boto3.client("secretsmanager").get_secret_value()`. No secret
    value is cached across calls — each `get_secret`/`get_secret_fields`/
    `get_credential` call performs a fresh Secrets Manager request, and the
    only thing this class stores across calls is the boto3 client itself
    and the (non-secret) `secret_name_map` configuration.
    """

    def __init__(
        self,
        secretsmanager_client: SecretsManagerClientProtocol,
        secret_name_map: dict[CredentialName, str] | None = None,
    ) -> None:
        """
        Args:
            secretsmanager_client: A `boto3.client("secretsmanager")`
                instance (or any object exposing the same
                `get_secret_value` method — tests pass a mock/stub here).
            secret_name_map: Optional mapping from logical
                `CredentialName` to the Secrets Manager secret name or ARN
                that stores it. Only needed if the caller wants to use
                `get_credential(name)`; `get_secret`/`get_secret_fields`
                take the secret name/ARN directly and never require this.
        """
        self._client = secretsmanager_client
        self._secret_name_map: dict[CredentialName, str] = dict(secret_name_map or {})

    def get_secret(self, secret_name: str) -> SecretStr:
        """Fetch a plain-string secret (e.g. a GitHub token) by Secrets
        Manager name or ARN.

        Returns the value wrapped in `SecretStr` so it can be passed
        around/logged without risk of the raw value being rendered.
        """
        raw_value = self._fetch_raw_secret_string(secret_name)
        return SecretStr(raw_value)

    def get_secret_fields(self, secret_name: str) -> dict[str, SecretStr]:
        """Fetch a JSON-structured secret (e.g. an Azure service principal
        with `clientId`/`clientSecret`/`tenantId` fields, or registry
        credentials with `username`/`password` fields) by Secrets Manager
        name or ARN.

        Each field value is individually wrapped in `SecretStr` before
        being returned, so the returned dict is safe to log/inspect at the
        top level (keys only) without exposing any field's value.
        """
        raw_value = self._fetch_raw_secret_string(secret_name)
        try:
            parsed: dict[str, Any] = json.loads(raw_value)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error(
                "Secret %r was requested as JSON fields but is not valid JSON",
                secret_name,
            )
            raise CredentialRetrievalError(
                secret_name=secret_name,
                reason="secret value is not valid JSON",
                cause=exc,
            ) from exc

        if not isinstance(parsed, dict):
            raise CredentialRetrievalError(
                secret_name=secret_name,
                reason="secret JSON value is not an object",
            )

        return {key: SecretStr(str(value)) for key, value in parsed.items()}

    def get_credential(self, credential_name: CredentialName) -> SecretStr:
        """Fetch a credential by its logical `CredentialName`, resolving
        the Secrets Manager name/ARN via this client's configured
        `secret_name_map`.

        Raises `CredentialNotConfiguredError` if `credential_name` has no
        entry in `secret_name_map`.
        """
        secret_name = self._secret_name_map.get(credential_name)
        if secret_name is None:
            raise CredentialNotConfiguredError(credential_name)
        return self.get_secret(secret_name)

    def _fetch_raw_secret_string(self, secret_name: str) -> str:
        """Single call-time-only fetch point. Every public method routes
        through here so there is exactly one place that calls
        `get_secret_value` and exactly one place that logs about the
        fetch — both log statements below reference `secret_name` only,
        never the response payload.
        """
        logger.info("Fetching secret %r from Secrets Manager", secret_name)
        try:
            response = self._client.get_secret_value(SecretId=secret_name)
        except Exception as exc:  # noqa: BLE001 - re-raised as CredentialRetrievalError below
            error_code = getattr(getattr(exc, "response", None), "get", lambda *_: None)(
                "Error", {}
            )
            code = error_code.get("Code") if isinstance(error_code, dict) else None
            logger.error(
                "Failed to fetch secret %r from Secrets Manager (error_code=%s)",
                secret_name,
                code or type(exc).__name__,
            )
            raise CredentialRetrievalError(
                secret_name=secret_name,
                reason=code or type(exc).__name__,
                cause=exc,
            ) from exc

        raw_value = response.get("SecretString")
        if raw_value is None:
            # SecretBinary secrets are out of scope for Phase 1's
            # credential set (GitHub token / Azure SP / registry creds are
            # all string/JSON secrets) — fail explicitly rather than
            # silently returning an empty/garbage value.
            logger.error(
                "Secret %r has no SecretString value (SecretBinary is unsupported)",
                secret_name,
            )
            raise CredentialRetrievalError(
                secret_name=secret_name,
                reason="secret has no SecretString value (SecretBinary is unsupported)",
            )

        logger.info("Fetched secret %r from Secrets Manager", secret_name)
        return raw_value
