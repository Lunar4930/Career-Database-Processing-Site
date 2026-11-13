"""File preparation, structured response parsing, and the OpenRouter adapter."""

import base64
import json
from unittest.mock import Mock

import pandas as pd
import pymupdf
import pytest
import requests
from pydantic import ValidationError


@pytest.mark.parametrize("source", ["path", "upload"])
@pytest.mark.parametrize("extension", ["png", "jpg", "jpeg"])
def test_images_are_base64_encoded(extraction, uploaded_file, tmp_path, source, extension):
    data = b"\x00\x01\x02image bytes\xff"
    if source == "path":
        path = tmp_path / f"portrait.{extension.upper()}"
        path.write_bytes(data)
        input_file = str(path)
        expected_type = "jpeg" if extension == "jpg" else extension
    else:
        input_file = uploaded_file(f"portrait.{extension}", data, f"image/{extension}")
        expected_type = extension

    content, file_type = extraction.process_file(input_file)

    assert base64.b64decode(content) == data
    assert file_type == expected_type


@pytest.mark.parametrize("source", ["path", "upload"])
def test_html_extracts_readable_text(extraction, uploaded_file, tmp_path, source):
    html = "<html><body><h1>People</h1><p>José De La Cruz &amp; Ada Lovelace</p></body></html>"
    path = tmp_path / "people.html"
    path.write_text(html, encoding="utf-8")
    input_file = str(path) if source == "path" else uploaded_file(path.name, html.encode(), "text/html")

    content, file_type = extraction.process_file(input_file)

    assert file_type == "html"
    assert "José De La Cruz & Ada Lovelace" in content
    assert "<p>" not in content


@pytest.mark.parametrize("source", ["path", "upload"])
def test_pdf_extracts_every_page_in_order(extraction, uploaded_file, tmp_path, source):
    with pymupdf.open() as document:
        for name in ("Ada Lovelace", "Grace Hopper"):
            document.new_page().insert_text((72, 72), name)
        data = document.tobytes()
    path = tmp_path / "people.pdf"
    path.write_bytes(data)
    input_file = str(path) if source == "path" else uploaded_file(path.name, data, "application/pdf")

    content, file_type = extraction.process_file(input_file)

    assert file_type == "pdf"
    assert content.splitlines() == ["Ada Lovelace", "Grace Hopper"]


def test_name_schema_preserves_optional_fields(extraction):
    name = extraction.NameIndividual(first_name="Ada", last_name="Lovelace")
    assert name.model_dump() == {
        "first_name": "Ada", "last_name": "Lovelace", "middle_name": None, "suffix": None,
    }


@pytest.mark.parametrize("missing", ["first_name", "last_name"])
def test_name_schema_requires_first_and_last_name(extraction, missing):
    fields = {"first_name": "Ada", "last_name": "Lovelace"}
    del fields[missing]
    with pytest.raises(ValidationError):
        extraction.NameIndividual(**fields)


@pytest.mark.parametrize("file_type", ["html", "pdf", "png", "jpg", "jpeg"])
def test_openrouter_sends_text_or_image_with_structured_output(extraction, monkeypatch, json_response, file_type):
    response = json_response({"choices": []})
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)

    assert extraction.send_to_openrouter("sample-content", file_type, prompt="Extract names", model="test-model") is response

    args, kwargs = post.call_args
    assert args == ("https://openrouter.ai/api/v1/chat/completions",)
    assert kwargs["headers"] == {
        "Authorization": "Bearer test-openrouter_api_key", "Content-Type": "application/json",
    }
    payload = kwargs["json"]
    assert payload["model"] == "test-model"
    assert payload["temperature"] == 0
    response_format = payload["response_format"]
    assert response_format["type"] == "json_schema"
    schema = response_format["json_schema"]
    assert schema["strict"] is True
    assert "names" in schema["schema"]["required"]
    if file_type in ("png", "jpg", "jpeg"):
        assert payload["messages"] == [{"role": "user", "content": [
            {"type": "text", "text": "Extract names"},
            {"type": "image_url", "image_url": {"url": f"data:image/{file_type};base64,sample-content"}},
        ]}]
    else:
        assert payload["messages"] == [
            {"role": "system", "content": [{"type": "text", "text": "Extract names"}]},
            {"role": "user", "content": [{"type": "text", "text": "sample-content"}]},
        ]


def test_openrouter_forwards_image_provider_preferences(extraction, monkeypatch, json_response):
    post = Mock(return_value=json_response({"choices": []}))
    monkeypatch.setattr(requests, "post", post)
    provider = {"allow_fallbacks": False, "only": ["test-provider"]}
    extraction.send_to_openrouter("image-data", "png", provider=provider)
    assert post.call_args.kwargs["json"]["provider"] == provider


@pytest.mark.parametrize("error", [requests.Timeout("timed out"), requests.ConnectionError("connection failed")])
def test_openrouter_wraps_transport_errors(extraction, monkeypatch, error):
    monkeypatch.setattr(requests, "post", Mock(side_effect=error))
    with pytest.raises(RuntimeError, match="Error processing content") as caught:
        extraction.send_to_openrouter("Ada Lovelace", "html")
    assert caught.value.__cause__ is error


def test_openrouter_rejects_http_errors(extraction, monkeypatch, json_response):
    monkeypatch.setattr(requests, "post", Mock(return_value=json_response({"error": "unavailable"}, status=503)))
    with pytest.raises(RuntimeError, match="503") as caught:
        extraction.send_to_openrouter("Ada Lovelace", "html")
    assert isinstance(caught.value.__cause__, requests.HTTPError)


def test_openrouter_rejects_invalid_json(extraction, monkeypatch, json_response):
    response = json_response({})
    response._content = b"not JSON"
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    with pytest.raises(RuntimeError, match="Error processing content") as caught:
        extraction.send_to_openrouter("Ada Lovelace", "html")
    assert isinstance(caught.value.__cause__, ValueError)


def test_openrouter_rejects_provider_errors_in_successful_http_response(extraction, monkeypatch, json_response):
    response = json_response({"error": {"code": 429, "message": "Rate limit exceeded"}})
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    with pytest.raises(Exception, match=r"\[429\] Rate limit exceeded") as caught:
        extraction.send_to_openrouter("Ada Lovelace", "html")
    assert caught.value.code == 429


@pytest.mark.parametrize("wrapper", ["{}", "```json\n{}\n```", "```\n{}\n```", "Here are the names:\n```json\n{}\n```\nDone."])
def test_response_parsing_deduplicates_and_preserves_name_fields(extraction, json_response, name_records, wrapper):
    content = wrapper.format(json.dumps({"names": name_records}))
    response = json_response({"choices": [{"message": {"content": content}}]})

    result = extraction.parse_response_output(response, "Example, Inc.")

    expected = pd.DataFrame([name_records[0], name_records[2]])
    expected["organization"] = "Example, Inc."
    pd.testing.assert_frame_equal(result.reset_index(drop=True), expected)


def test_response_with_no_names_produces_a_header_only_csv(extraction, json_response):
    response = json_response({"choices": [{"message": {"content": '{"names": []}'}}]})
    result = extraction.parse_response_output(response, "Example Inc")
    assert result.empty
    assert result.to_csv(index=False).strip() == "first_name,last_name,middle_name,suffix,organization"
