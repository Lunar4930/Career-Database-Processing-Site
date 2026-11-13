"""Search request contracts and LinkedIn URL/matching behavior."""

from unittest.mock import Mock

import pandas as pd
import pytest
import requests
from streamlit.runtime.scriptrunner import StopException


def test_brave_search_builds_query_and_returns_response(profiles, monkeypatch, json_response):
    data = {"web": {"results": [{"url": "https://www.linkedin.com/in/ada-lovelace/"}]}}
    get = Mock(return_value=json_response(data))
    monkeypatch.setattr(requests, "get", get)

    result = profiles.brave_search("Ada", "Lovelace", "Byron", "Example Inc", count=3, api_key="test-brave-key")

    assert result == data
    get.assert_called_once_with(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": 'Ada Byron Lovelace Example Inc "LinkedIn"', "results_filter": "web", "count": 3},
        headers={"X-Subscription-Token": "test-brave-key"},
    )


@pytest.mark.parametrize("http_error", [False, True], ids=["timeout", "http-error"])
def test_brave_failure_displays_error_and_stops(profiles, monkeypatch, json_response, http_error):
    response = json_response({"message": "invalid API key"}, status=401)
    error = requests.HTTPError("Unauthorized", response=response) if http_error else requests.Timeout("timed out")
    monkeypatch.setattr(requests, "get", Mock(side_effect=error))
    show_error, show_code = Mock(), Mock()
    stop = Mock(side_effect=StopException())
    monkeypatch.setattr(profiles.st, "error", show_error)
    monkeypatch.setattr(profiles.st, "code", show_code)
    monkeypatch.setattr(profiles.st, "stop", stop)

    with pytest.raises(StopException):
        profiles.brave_search("Ada", "Lovelace", "Byron", "Example Inc")

    show_error.assert_called_once_with(f"Brave search aborted — {type(error).__name__}: {error}")
    stop.assert_called_once()
    if http_error:
        show_code.assert_called_once_with(response.text)
    else:
        show_code.assert_not_called()


@pytest.mark.parametrize("middle_name,organization,query", [
    ("Byron", "Example Inc", "Ada Byron Lovelace Example Inc LinkedIn"),
    (None, "Example Inc", "Ada Lovelace Example Inc LinkedIn"),
    (float("nan"), "Example Inc", "Ada Lovelace Example Inc LinkedIn"),
    (pd.NA, pd.NA, "Ada Lovelace LinkedIn"),
])
def test_tavily_query_handles_missing_csv_values(profiles, middle_name, organization, query):
    client = Mock()
    client.search.return_value = {"results": []}

    result = profiles.tavily_search("Ada", "Lovelace", middle_name, organization, count=4, tavily_client=client)

    assert result == {"results": []}
    client.search.assert_called_once_with(
        query=query, search_depth="advanced", max_results=4,
        include_domains=["linkedin.com"], include_favicon=False, include_usage=False,
    )


def test_tavily_failure_displays_error_and_stops(profiles, monkeypatch):
    client = Mock()
    client.search.side_effect = RuntimeError("search unavailable")
    show_error = Mock()
    stop = Mock(side_effect=StopException())
    monkeypatch.setattr(profiles.st, "error", show_error)
    monkeypatch.setattr(profiles.st, "stop", stop)

    with pytest.raises(StopException):
        profiles.tavily_search("Ada", "Lovelace", None, "Example Inc", tavily_client=client)

    show_error.assert_called_once_with("Tavily search aborted — RuntimeError: search unavailable")
    stop.assert_called_once()


@pytest.mark.parametrize("engine", ["brave", "tavily"])
@pytest.mark.parametrize("url,profile_id", [
    ("https://www.linkedin.com/in/ada-lovelace/", "ada-lovelace"),
    ("http://linkedin.com/in/ada-lovelace", "ada-lovelace"),
    ("https://uk.linkedin.com/in/ada-lovelace/?trk=public#about", "ada-lovelace"),
    ("HTTPS://WWW.LINKEDIN.COM/IN/Ada-Lovelace-123", "Ada-Lovelace-123"),
    ("https://linkedin.com/company/example/", None),
    ("https://linkedin.com.evil.test/in/ada-lovelace/", None),
    ("https://notlinkedin.com/in/ada-lovelace/", None),
    ("https://linkedin.com/in/", None),
    ("https://linkedin.com/in/ada-lovelace/details/", None),
    ("https://example.test/?url=https://linkedin.com/in/ada-lovelace", None),
])
def test_only_linkedin_personal_profile_urls_are_accepted(profiles, engine, url, profile_id):
    results = [{"url": url}]
    if engine == "brave":
        matches = profiles.parse_brave_results({"web": {"results": results}})
    else:
        matches = profiles.parse_tavily_results({"results": results})
    assert matches == ([] if profile_id is None else [profile_id])


@pytest.mark.parametrize("engine", ["brave", "tavily"])
def test_search_result_parsing_preserves_order_and_handles_empty_results(profiles, engine):
    results = [
        {"url": "https://linkedin.com/in/second/"},
        {"url": "https://example.test"},
        {"url": "https://linkedin.com/in/first/"},
    ]
    if engine == "brave":
        parse = lambda rows: profiles.parse_brave_results({"web": {"results": rows}})
    else:
        parse = lambda rows: profiles.parse_tavily_results({"results": rows})
    assert parse(results) == ["second", "first"]
    assert parse([]) == []


@pytest.mark.parametrize("first,second,expected", [
    (["preferred", "other"], ["other", "preferred"], "preferred"),
    (["unique", "shared"], ["shared"], "shared"),
    (["one"], ["two"], None),
    ([], ["one"], None),
    (["one"], [], None),
    ([], [], None),
])
def test_matching_profile_uses_first_shared_result(profiles, first, second, expected):
    assert profiles.find_matching_profile(first, second) == expected
