"""Shared fixtures for running the real application without API credentials or network access."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import dotenv
import pytest
import requests
import streamlit as st
from streamlit.proto.Common_pb2 import FileURLs
from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
from tavily import TavilyClient

ROOT = Path(__file__).resolve().parents[1]
EXTRACT_PAGE = ROOT / "Extract_Names.py"
PROFILES_PAGE = ROOT / "pages" / "1_Find_LinkedIn_Profiles.py"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Never read real credentials from the environment or a developer's .env file."""
    for key in ("OPENROUTER_API_KEY", "BRAVE_SEARCH_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.setenv(key, f"test-{key.lower()}")
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)


@pytest.fixture
def load_script(monkeypatch):
    """Import page helpers while leaving the top-level Streamlit form unsubmitted."""
    monkeypatch.setattr(st, "form_submit_button", lambda *args, **kwargs: False)

    def load(path):
        name = f"test_app_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    return load


@pytest.fixture
def extraction(load_script):
    return load_script(EXTRACT_PAGE)


@pytest.fixture
def profiles(load_script):
    return load_script(PROFILES_PAGE)


@pytest.fixture
def uploaded_file():
    def make(name, data, mime_type):
        record = UploadedFileRec(file_id=name, name=name, type=mime_type, data=data)
        return UploadedFile(record, FileURLs())

    return make


@pytest.fixture
def json_response():
    """Real Response parsing/status checks, with an entirely in-memory body."""
    def make(data, status=200):
        response = requests.Response()
        response.status_code = status
        response.url = "https://example.test/mocked-response"
        response._content = json.dumps(data).encode("utf-8")
        response.headers["Content-Type"] = "application/json"
        return response

    return make


@pytest.fixture
def name_records():
    return [
        {"first_name": "Ada", "last_name": "Lovelace", "middle_name": "Byron", "suffix": None},
        # The first occurrence should win when the same person appears twice.
        {"first_name": "Ada", "last_name": "Lovelace", "middle_name": None, "suffix": None},
        {"first_name": "José", "last_name": "De La Cruz", "middle_name": None, "suffix": "Jr."},
    ]


@pytest.fixture
def api_mocks(monkeypatch, json_response, name_records):
    """Patch the external boundaries, leaving application processing intact."""
    post = Mock(return_value=json_response({
        "choices": [{"message": {"content": json.dumps({"names": name_records})}}],
    }))
    get = Mock(return_value=json_response({"web": {"results": []}}))
    tavily = Mock(return_value={"results": []})
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(TavilyClient, "search", tavily)
    return post, get, tavily
