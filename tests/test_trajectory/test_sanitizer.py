"""Tests for the trajectory sanitizer."""

from __future__ import annotations

from evosys.trajectory.sanitizer import sanitize_dict, sanitize_string, sanitize_value


class TestApiKeyRedaction:
    def test_generic_api_key(self) -> None:
        text = "key is sk_live_abc123def456ghi789jkl0"
        result = sanitize_string(text)
        assert "sk_live_abc123" not in result
        assert "[REDACTED_API_KEY]" in result

    def test_api_key_prefix(self) -> None:
        text = "use api_key_abcdefghijklmnopqrstuvwxyz"
        result = sanitize_string(text)
        assert "abcdefghij" not in result


class TestBearerTokenRedaction:
    def test_bearer_token(self) -> None:
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        result = sanitize_string(text)
        assert "eyJhbG" not in result
        assert "[REDACTED_BEARER_TOKEN]" in result

    def test_bearer_case_insensitive(self) -> None:
        text = "bearer mytoken123456"
        result = sanitize_string(text)
        assert "mytoken" not in result


class TestAwsKeyRedaction:
    def test_aws_access_key(self) -> None:
        text = "key: AKIAIOSFODNN7EXAMPLE"
        result = sanitize_string(text)
        assert "AKIAIOSFODNN7" not in result
        assert "[REDACTED_AWS_KEY]" in result


class TestEmailRedaction:
    def test_email(self) -> None:
        text = "contact user@example.com for info"
        result = sanitize_string(text)
        assert "user@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_complex_email(self) -> None:
        text = "send to john.doe+tag@sub.domain.co.uk"
        result = sanitize_string(text)
        assert "john.doe" not in result


class TestPhoneRedaction:
    def test_us_phone(self) -> None:
        text = "call 555-123-4567"
        result = sanitize_string(text)
        assert "555-123-4567" not in result
        assert "[REDACTED_" in result

    def test_phone_with_country_code(self) -> None:
        text = "call +1-555-123-4567"
        result = sanitize_string(text)
        assert "555-123-4567" not in result


class TestCreditCardRedaction:
    def test_credit_card_dashes(self) -> None:
        text = "card: 4111-1111-1111-1111"
        result = sanitize_string(text)
        assert "4111-1111" not in result
        assert "[REDACTED_" in result

    def test_credit_card_spaces(self) -> None:
        text = "card: 4111 1111 1111 1111"
        result = sanitize_string(text)
        assert "4111 1111" not in result


class TestSsnRedaction:
    def test_ssn(self) -> None:
        text = "SSN: 123-45-6789"
        result = sanitize_string(text)
        assert "123-45-6789" not in result
        assert "[REDACTED_" in result

    def test_ssn_no_dashes(self) -> None:
        text = "SSN: 123456789"
        result = sanitize_string(text)
        assert "123456789" not in result


class TestNestedDicts:
    def test_nested_dict_sanitization(self) -> None:
        data = {
            "config": {
                "api_key": "super_secret_key",
                "endpoint": "https://api.example.com",
            },
            "user": {"email": "test@example.com"},
        }
        result = sanitize_dict(data)
        assert result["config"]["api_key"] == "[REDACTED]"
        assert "[REDACTED_EMAIL]" in result["user"]["email"]


class TestLists:
    def test_list_sanitization(self) -> None:
        data = {"emails": ["alice@example.com", "bob@example.com"]}
        result = sanitize_dict(data)
        assert all("[REDACTED_EMAIL]" in v for v in result["emails"])


class TestCaseInsensitiveKeys:
    def test_uppercase_key(self) -> None:
        data = {"API_KEY": "secret123", "Password": "hunter2"}
        result = sanitize_dict(data)
        assert result["API_KEY"] == "[REDACTED]"
        assert result["Password"] == "[REDACTED]"


class TestPassthroughNonStrings:
    def test_integers_unchanged(self) -> None:
        assert sanitize_value(42) == 42

    def test_floats_unchanged(self) -> None:
        assert sanitize_value(3.14) == 3.14

    def test_booleans_unchanged(self) -> None:
        assert sanitize_value(True) is True

    def test_none_unchanged(self) -> None:
        assert sanitize_value(None) is None


class TestEmptyInputs:
    def test_empty_string(self) -> None:
        assert sanitize_string("") == ""

    def test_empty_dict(self) -> None:
        assert sanitize_dict({}) == {}

    def test_empty_list(self) -> None:
        assert sanitize_value([]) == []
