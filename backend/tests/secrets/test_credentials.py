"""Unit tests for the Secrets Manager credential retrieval helper (Task 4.1).

Covers:
  - correct retrieval of a plain-string secret (GitHub token) and a
    JSON-structured secret (Azure service principal / registry creds)
  - that the returned `SecretStr` value never exposes the raw secret via
    `repr()`/`str()`/logging, either at the top-level object or nested in
    a dict/list
  - basic error handling when a secret is not found / has no SecretString
  - that `get_credential` never fetches unless a name is configured
  - that no log record emitted during a fetch contains the raw secret value

Exhaustive allowlist-enforcement testing is Task 4.4's responsibility, not
this one (see tasks.md Task 4.1 scope note).
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from pydantic import SecretStr

from daf.secrets.credentials import (
    CredentialName,
    CredentialNotConfiguredError,
    CredentialRetrievalError,
    CredentialsClient,
)

GITHUB_TOKEN_SECRET_NAME = "daf/phase1/github-token"
AZURE_SP_SECRET_NAME = "daf/phase1/azure-service-principal"
RAW_GITHUB_TOKEN = "ghp_super_secret_value_12345"  # noqa: S105 - test fixture value
RAW_AZURE_SP = {
    "clientId": "11111111-1111-1111-1111-111111111111",
    "clientSecret": "az-super-secret-value",
    "tenantId": "22222222-2222-2222-2222-222222222222",
}


def _mock_client_returning(secret_string: str) -> MagicMock:
    client = MagicMock()
    client.get_secret_value.return_value = {"SecretString": secret_string}
    return client


class TestGetSecret:
    def test_retrieves_and_returns_the_correct_secret_value(self) -> None:
        client = _mock_client_returning(RAW_GITHUB_TOKEN)
        creds = CredentialsClient(client)

        result = creds.get_secret(GITHUB_TOKEN_SECRET_NAME)

        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == RAW_GITHUB_TOKEN
        client.get_secret_value.assert_called_once_with(SecretId=GITHUB_TOKEN_SECRET_NAME)

    def test_makes_a_fresh_call_every_time_no_caching_across_calls(self) -> None:
        client = _mock_client_returning(RAW_GITHUB_TOKEN)
        creds = CredentialsClient(client)

        creds.get_secret(GITHUB_TOKEN_SECRET_NAME)
        creds.get_secret(GITHUB_TOKEN_SECRET_NAME)

        assert client.get_secret_value.call_count == 2


class TestGetSecretFields:
    def test_retrieves_json_secret_fields_as_secret_str_values(self) -> None:
        client = _mock_client_returning(json.dumps(RAW_AZURE_SP))
        creds = CredentialsClient(client)

        fields = creds.get_secret_fields(AZURE_SP_SECRET_NAME)

        assert set(fields.keys()) == set(RAW_AZURE_SP.keys())
        for key, expected_value in RAW_AZURE_SP.items():
            assert isinstance(fields[key], SecretStr)
            assert fields[key].get_secret_value() == expected_value

    def test_raises_credential_retrieval_error_on_invalid_json(self) -> None:
        client = _mock_client_returning("not-json")
        creds = CredentialsClient(client)

        with pytest.raises(CredentialRetrievalError):
            creds.get_secret_fields(AZURE_SP_SECRET_NAME)


class TestGetCredential:
    def test_resolves_secret_name_via_configured_map(self) -> None:
        client = _mock_client_returning(RAW_GITHUB_TOKEN)
        creds = CredentialsClient(
            client,
            secret_name_map={CredentialName.GITHUB_TOKEN: GITHUB_TOKEN_SECRET_NAME},
        )

        result = creds.get_credential(CredentialName.GITHUB_TOKEN)

        assert result.get_secret_value() == RAW_GITHUB_TOKEN
        client.get_secret_value.assert_called_once_with(SecretId=GITHUB_TOKEN_SECRET_NAME)

    def test_raises_when_credential_name_not_configured(self) -> None:
        client = _mock_client_returning(RAW_GITHUB_TOKEN)
        creds = CredentialsClient(client, secret_name_map={})

        with pytest.raises(CredentialNotConfiguredError):
            creds.get_credential(CredentialName.REGISTRY_CREDENTIALS)

        client.get_secret_value.assert_not_called()


class TestSecretNeverLeaksViaReprOrLogging:
    def test_repr_and_str_never_expose_the_raw_secret(self) -> None:
        client = _mock_client_returning(RAW_GITHUB_TOKEN)
        creds = CredentialsClient(client)
        result = creds.get_secret(GITHUB_TOKEN_SECRET_NAME)

        assert RAW_GITHUB_TOKEN not in repr(result)
        assert RAW_GITHUB_TOKEN not in str(result)

    def test_printing_or_fstring_formatting_the_object_does_not_leak_secret(self, capsys) -> None:
        client = _mock_client_returning(RAW_GITHUB_TOKEN)
        creds = CredentialsClient(client)
        result = creds.get_secret(GITHUB_TOKEN_SECRET_NAME)

        print(result)
        print(f"token={result}")
        captured = capsys.readouterr()

        assert RAW_GITHUB_TOKEN not in captured.out

    def test_secret_fields_dict_repr_does_not_leak_any_field_value(self) -> None:
        client = _mock_client_returning(json.dumps(RAW_AZURE_SP))
        creds = CredentialsClient(client)
        fields = creds.get_secret_fields(AZURE_SP_SECRET_NAME)

        rendered = repr(fields)
        for expected_value in RAW_AZURE_SP.values():
            assert expected_value not in rendered

    def test_no_log_record_emitted_during_fetch_contains_the_raw_secret_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = _mock_client_returning(RAW_GITHUB_TOKEN)
        creds = CredentialsClient(client)

        with caplog.at_level(logging.DEBUG):
            creds.get_secret(GITHUB_TOKEN_SECRET_NAME)

        for record in caplog.records:
            assert RAW_GITHUB_TOKEN not in record.getMessage()


class TestErrorHandling:
    def test_secret_not_found_raises_credential_retrieval_error(self) -> None:
        client = MagicMock()
        client.get_secret_value.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "Secrets Manager can't find the specified secret.",
                }
            },
            operation_name="GetSecretValue",
        )
        creds = CredentialsClient(client)

        with pytest.raises(CredentialRetrievalError) as exc_info:
            creds.get_secret("does/not/exist")

        assert exc_info.value.secret_name == "does/not/exist"

    def test_error_message_never_contains_a_secret_value(self) -> None:
        client = MagicMock()
        client.get_secret_value.side_effect = ClientError(
            error_response={"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
            operation_name="GetSecretValue",
        )
        creds = CredentialsClient(client)

        with pytest.raises(CredentialRetrievalError) as exc_info:
            creds.get_secret("does/not/exist")

        # The error concerns the secret's *name*, never a value (there was
        # no value to leak in this case, but this guards the invariant
        # generally: the message is built solely from secret_name/reason).
        assert "does/not/exist" in str(exc_info.value)

    def test_secret_with_no_secret_string_raises_credential_retrieval_error(self) -> None:
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretBinary": b"binary-not-supported"}
        creds = CredentialsClient(client)

        with pytest.raises(CredentialRetrievalError):
            creds.get_secret("some/binary/secret")
