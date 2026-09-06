import pytest

from lib import gem

pytestmark = pytest.mark.tier1


class FakeAPIError(Exception):
    """Stands in for google.genai.errors.APIError - real errors captured
    2026-09-06 against the live API expose structured .code (int) and
    .status (str) attributes, not just a message string. See DIARY.md."""

    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


# ----------------------------------------------------------- classify_error -
def test_classify_error_recognizes_a_bad_key():
    e = FakeAPIError("API key not valid. Please pass a valid API key.", 400, "INVALID_ARGUMENT")
    assert gem.classify_error(e) == "bad_key"


def test_classify_error_recognizes_permission_denied_as_a_bad_key():
    e = FakeAPIError("The caller does not have permission", 403, "PERMISSION_DENIED")
    assert gem.classify_error(e) == "bad_key"


def test_classify_error_recognizes_daily_quota_exhaustion():
    e = FakeAPIError("Quota exceeded for quota metric 'GenerateContent'", 429, "RESOURCE_EXHAUSTED")
    assert gem.classify_error(e) == "quota"


def test_classify_error_recognizes_depleted_prepayment():
    e = FakeAPIError("Prepayment credits are depleted", 429, "RESOURCE_EXHAUSTED")
    assert gem.classify_error(e) == "billing"


def test_classify_error_recognizes_a_bare_rate_limit():
    # RESOURCE_EXHAUSTED without either "quota" or "prepayment" wording -
    # TROUBLESHOOTING.md's "429 errors coming quickly" case: too many
    # requests per minute, not the daily allowance or the account balance.
    e = FakeAPIError("Too many requests", 429, "RESOURCE_EXHAUSTED")
    assert gem.classify_error(e) == "rate_limit"


def test_classify_error_recognizes_model_not_found():
    e = FakeAPIError(
        "models/gemini-old-model is not found for API version v1beta", 404, "NOT_FOUND"
    )
    assert gem.classify_error(e) == "model_not_found"


def test_classify_error_falls_back_to_unknown():
    assert gem.classify_error(ValueError("something else entirely")) == "unknown"


def test_classify_error_falls_back_to_unknown_for_a_plain_exception_with_no_attrs():
    assert gem.classify_error(Exception("a generic failure")) == "unknown"


# ----------------------------------------------------------- explain_error --
def test_explain_error_names_the_daily_quota():
    e = FakeAPIError("Quota exceeded", 429, "RESOURCE_EXHAUSTED")
    msg = gem.explain_error(e)
    assert "tomorrow" in msg.lower()
    assert "quota" in msg.lower() or "allowance" in msg.lower()


def test_explain_error_names_billing():
    e = FakeAPIError("Prepayment credits are depleted", 429, "RESOURCE_EXHAUSTED")
    msg = gem.explain_error(e)
    assert "top up" in msg.lower() or "aistudio.google.com" in msg.lower()


def test_explain_error_names_the_bad_key():
    e = FakeAPIError("API key not valid", 400, "INVALID_ARGUMENT")
    msg = gem.explain_error(e)
    assert "key" in msg.lower()


def test_explain_error_names_which_constant_to_change_on_model_not_found():
    e = FakeAPIError("models/gemini-old is not found", 404, "NOT_FOUND")
    msg = gem.explain_error(e)
    assert "lib/media.py" in msg


def test_explain_error_falls_back_to_the_message_for_unknown_errors():
    e = ValueError("a weird one-off failure")
    assert "a weird one-off failure" in gem.explain_error(e)


# ------------------------------------------------------------ backoff_delay -
def test_backoff_base_increases_with_attempt_number():
    # The deterministic part, tested exactly - jitter is tested separately
    # below so this isn't at the mercy of randomness.
    assert gem._backoff_base(0) < gem._backoff_base(1) < gem._backoff_base(2)


def test_backoff_base_is_capped():
    assert gem._backoff_base(10) == gem.BACKOFF_CAP_SECONDS


def test_backoff_delay_is_at_least_the_uncapped_base_for_that_attempt():
    for attempt in range(4):
        assert gem.backoff_delay(attempt) >= gem._backoff_base(attempt)


def test_backoff_delay_adds_no_more_than_the_documented_jitter():
    for attempt in range(4):
        assert gem.backoff_delay(attempt) <= gem._backoff_base(attempt) + gem.BACKOFF_JITTER_SECONDS


def test_backoff_delay_is_never_negative():
    for attempt in range(6):
        assert gem.backoff_delay(attempt) >= 0
