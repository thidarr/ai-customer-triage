import json
from unittest.mock import MagicMock

import httpx
import pytest
from google import genai
from google.genai import errors, types

from app.classifier import ClassificationError, classify_message
from app.config import ConfigurationError, get_settings
from app.schemas import TriageResult


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    # Never load the developer's actual credentials during tests.
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setattr("app.classifier.time.sleep", MagicMock())


@pytest.fixture
def output():
    return dict(category="billing", priority="low", summary="Invoice requested.",
                suggested_action="Provide the invoice.")


@pytest.fixture
def gemini(monkeypatch, output):
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.models.generate_content.return_value = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(
            parts=[types.Part(text=json.dumps(output))]
        ))]
    )
    monkeypatch.setattr("app.classifier.genai.Client", factory)
    return factory, client.models.generate_content


def test_valid_result_and_message_only_payload(gemini, output):
    factory, generate = gemini
    result = classify_message("Please send my invoice.")
    assert isinstance(result, TriageResult)
    assert result.model_dump() == output
    kwargs = generate.call_args.kwargs
    assert kwargs["contents"] == "Please send my invoice."
    assert kwargs["model"] == "test-model"
    assert kwargs["config"].response_schema is None
    assert kwargs["config"].response_json_schema == TriageResult.model_json_schema()
    assert kwargs["config"].response_mime_type == "application/json"
    assert "independently" in kwargs["config"].system_instruction
    assert factory.call_args.kwargs["http_options"].timeout == 30_000
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("field,value", [
    ("category", "other"), ("priority", "urgent"),
    *[(field, value) for field in ("summary", "suggested_action")
      for value in ("", " \t\n", None, 123, [], {})],
])
def test_invalid_output_is_rejected(gemini, output, field, value):
    output[field] = value
    gemini[1].return_value = MagicMock(text=json.dumps(output))
    with pytest.raises(ClassificationError):
        classify_message("Help me.")


@pytest.mark.parametrize("field", ["category", "priority", "summary", "suggested_action"])
def test_missing_output_field_is_rejected(gemini, output, field):
    del output[field]
    gemini[1].return_value = MagicMock(text=json.dumps(output))
    with pytest.raises(ClassificationError):
        classify_message("Help me.")


def test_extra_output_field_is_rejected(gemini, output):
    output["customer_id"] = "unexpected"
    gemini[1].return_value = MagicMock(text=json.dumps(output))
    with pytest.raises(ClassificationError):
        classify_message("Help me.")


@pytest.mark.parametrize("text", [None, "", "not JSON", "{}", "null", "[]"])
def test_missing_or_malformed_output_is_rejected(gemini, text):
    gemini[1].return_value = MagicMock(text=text)
    with pytest.raises(ClassificationError):
        classify_message("Help me.")


def test_output_whitespace_is_trimmed(gemini, output):
    output.update(summary="  Invoice requested.\n", suggested_action=" Send invoice. ")
    gemini[1].return_value = MagicMock(text=json.dumps(output))
    result = classify_message("Invoice please.")
    assert result.summary == "Invoice requested."
    assert result.suggested_action == "Send invoice."


@pytest.mark.parametrize("error", [
    errors.APIError(503, {"error": {"message": "Unavailable"}}),
    httpx.ConnectError("Connection failed"),
    httpx.ReadTimeout("Timed out"),
])
def test_provider_failure_stops_classification(gemini, error):
    gemini[1].side_effect = error
    with pytest.raises(ClassificationError):
        classify_message("Help me.")


@pytest.mark.parametrize("variable", ["GEMINI_API_KEY", "GEMINI_MODEL"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_configuration_prevents_call(gemini, monkeypatch, variable, value):
    if value is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, value)
    with pytest.raises(ConfigurationError):
        classify_message("Help me.")
    gemini[0].assert_not_called()


def test_configuration_values_are_loaded():
    settings = get_settings()
    assert settings.gemini_api_key == "test-key"
    assert settings.gemini_model == "test-model"


def test_real_sdk_serializes_schema_with_mocked_transport(monkeypatch, output):
    """Exercise SDK schema conversion without sending any network request."""
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(output)}],
                                          "role": "model"},
                            "finishReason": "STOP"}]
        })

    client = genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            client_args={"transport": httpx.MockTransport(respond)}
        ),
    )
    monkeypatch.setattr("app.classifier.genai.Client", lambda **kwargs: client)
    assert classify_message("Please send an invoice.").model_dump() == output
    assert len(requests) == 1
    assert requests[0]["contents"][0]["parts"] == [{"text": "Please send an invoice."}]
    generation_config = requests[0]["generationConfig"]
    assert "responseSchema" not in generation_config
    schema = generation_config["responseJsonSchema"]
    assert schema == TriageResult.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "additional_properties" not in schema
    assert set(schema["required"]) == set(output)


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_temporary_failure_recovers_on_third_attempt(gemini, output, monkeypatch, code):
    sleep = MagicMock()
    monkeypatch.setattr("app.classifier.time.sleep", sleep)
    monkeypatch.setattr("app.classifier.random.uniform", lambda a, b: 0.5)
    failure = errors.APIError(code, {"error": {"message": "temporary"}})
    gemini[1].side_effect = [failure, failure, MagicMock(text=json.dumps(output))]
    assert classify_message("Invoice please.").model_dump() == output
    assert gemini[1].call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1.5, 2.5]
    assert gemini[0].call_args.kwargs["http_options"].retry_options.attempts == 1


def test_retries_exhausted_and_logs_are_safe(gemini, caplog):
    failure = errors.APIError(503, {"error": {"message": "test-key private-message secret-url"}})
    gemini[1].side_effect = failure
    with pytest.raises(ClassificationError) as caught:
        classify_message("private-message")
    assert caught.value.__cause__ is failure
    assert gemini[1].call_count == 3
    assert "http_code=503" in caplog.text
    for secret in ("test-key", "private-message", "secret-url"):
        assert secret not in caplog.text


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
def test_permanent_provider_error_is_not_retried(gemini, code):
    gemini[1].side_effect = errors.APIError(code, {"error": {"message": "invalid"}})
    with pytest.raises(ClassificationError):
        classify_message("Help")
    gemini[1].assert_called_once()


@pytest.mark.parametrize("text", [None, "", "not JSON", '{"summary":"private-message"}'])
def test_invalid_output_is_not_retried_or_logged(gemini, caplog, text):
    gemini[1].return_value = MagicMock(text=text)
    with pytest.raises(ClassificationError):
        classify_message("private-message")
    gemini[1].assert_called_once()
    assert "private-message" not in caplog.text


@pytest.mark.parametrize("error", [httpx.ReadTimeout("secret"), httpx.ConnectError("secret")])
def test_transport_failure_is_not_retried(gemini, caplog, error):
    gemini[1].side_effect = error
    with pytest.raises(ClassificationError):
        classify_message("Help")
    gemini[1].assert_called_once()
    assert "secret" not in caplog.text
