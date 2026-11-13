"""Exercise the actual Streamlit forms and CSV exports with mocked providers."""

import io
import uuid
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
EXTRACT_PAGE = "Extract_Names.py"
PROFILES_PAGE = "pages/1_Find_LinkedIn_Profiles.py"


@pytest.fixture
def app_page():
    def run(page):
        return AppTest.from_file(str(ROOT / page), default_timeout=15).run()
    return run


@pytest.fixture
def download(monkeypatch):
    # Keep the real widget and also inspect the bytes offered to the user.
    capture = Mock(wraps=st.download_button)
    monkeypatch.setattr(st, "download_button", capture)
    return capture


def search_results(ids):
    return [{"url": f"https://www.linkedin.com/in/{profile_id}/"} for profile_id in ids]


def exported_csv(download):
    args, kwargs = download.call_args
    data = kwargs["data"] if "data" in kwargs else args[1]
    assert kwargs["mime"] == "text/csv"
    assert kwargs["file_name"].endswith(".csv")
    return data


@pytest.mark.parametrize("page,title", [
    (EXTRACT_PAGE, "Extract Names"),
    (PROFILES_PAGE, "Find LinkedIn Profiles"),
])
def test_pages_load_without_contacting_providers(app_page, api_mocks, page, title):
    app = app_page(page)
    assert not app.exception
    assert app.title[0].value == title
    assert len(app.get("file_uploader")) == 1
    assert len(app.button) == 1
    for api in api_mocks:
        api.assert_not_called()


def test_extract_form_requires_a_file(app_page, api_mocks):
    app = app_page(EXTRACT_PAGE)
    app.text_input[0].set_value("Example Inc")
    app.button[0].click().run()
    assert not app.exception
    assert app.error[0].value == "Please upload a file"
    for api in api_mocks:
        api.assert_not_called()


def test_extract_form_requires_an_organization(app_page, api_mocks):
    app = app_page(EXTRACT_PAGE)
    app.file_uploader[0].set_value(("people.html", b"<p>Ada Lovelace</p>", "text/html"))
    app.button[0].click().run()
    assert not app.exception
    assert app.error[0].value == "Please enter the name of the organization"
    for api in api_mocks:
        api.assert_not_called()


def test_profiles_form_requires_a_csv(app_page, api_mocks):
    app = app_page(PROFILES_PAGE)
    app.button[0].click().run()
    assert not app.exception
    assert "Please upload a CSV file." in [item.value for item in app.markdown]
    for api in api_mocks:
        api.assert_not_called()


def test_extract_export_can_be_uploaded_to_profiles_page(app_page, api_mocks, download, json_response):
    post, get, tavily = api_mocks
    app = app_page(EXTRACT_PAGE)
    app.text_input[0].set_value("Example, Inc.")
    app.file_uploader[0].set_value(("people.html", "<p>Ada Lovelace and José De La Cruz</p>".encode(), "text/html"))
    app.button[0].click().run()

    assert not app.exception
    assert not app.error
    post.assert_called_once()
    assert app.dataframe[0].value["first_name"].tolist() == ["Ada", "José"]
    names_csv = exported_csv(download)
    assert download.call_args.kwargs["file_name"] == "1_names_Example, Inc..csv"
    names = pd.read_csv(io.StringIO(names_csv))
    assert names["organization"].tolist() == ["Example, Inc.", "Example, Inc."]
    assert "Unnamed: 0" not in names.columns
    get.assert_not_called()
    tavily.assert_not_called()

    get.side_effect = [
        json_response({"web": {"results": search_results(["ada-lovelace"])}}),
        json_response({"web": {"results": search_results(["jose-de-la-cruz"])}}),
    ]
    tavily.side_effect = [
        {"results": search_results(["ada-lovelace"])},
        {"results": search_results(["jose-de-la-cruz"])},
    ]
    download.reset_mock()
    app = app_page(PROFILES_PAGE)
    app.file_uploader[0].set_value(("names.csv", names_csv.encode(), "text/csv"))
    app.button[0].click().run()

    assert not app.exception
    assert not app.error
    enriched = pd.read_csv(io.StringIO(exported_csv(download)))
    assert enriched["first_name"].tolist() == ["Ada", "José"]
    assert enriched["last_name"].tolist() == ["Lovelace", "De La Cruz"]
    assert enriched.loc[1, "suffix"] == "Jr."
    assert enriched["linkedin_id"].tolist() == ["ada-lovelace", "jose-de-la-cruz"]
    assert enriched["database_id"].tolist() == [
        str(uuid.uuid5(uuid.NAMESPACE_DNS, "Ada_Lovelace_ada-lovelace")),
        str(uuid.uuid5(uuid.NAMESPACE_DNS, "José_De La Cruz_jose-de-la-cruz")),
    ]
    assert get.call_count == tavily.call_count == 2
    # Enrichment must not send another extraction request.
    post.assert_called_once()


@pytest.mark.parametrize("brave_ids,tavily_ids,existing_id,expected_id,other_matches", [
    (["brave-only", "shared"], ["tavily-only", "shared"], None, "shared", "brave-only, tavily-only"),
    (["brave-only"], ["tavily-only"], None, "tavily-only", "brave-only"),
    (["brave-only"], [], None, "brave-only", ""),
    ([], ["tavily-only"], None, "tavily-only", ""),
    ([], [], None, None, ""),
    ([], [], "existing-profile", "existing-profile", "previous-alternative"),
], ids=["agreement", "tavily-preferred", "brave-only", "tavily-only", "no-results", "existing-profile"])
def test_profile_selection_and_stable_database_ids(
    app_page, api_mocks, download, json_response,
    brave_ids, tavily_ids, existing_id, expected_id, other_matches,
):
    _, get, tavily = api_mocks
    get.return_value = json_response({"web": {"results": search_results(brave_ids)}})
    tavily.return_value = {"results": search_results(tavily_ids)}
    row = {
        "first_name": "Ada", "last_name": "Lovelace", "middle_name": "Byron",
        "suffix": None, "organization": "Example Inc",
    }
    if existing_id:
        row.update(linkedin_id=existing_id, other_matches=other_matches, database_id="outdated-id")
    csv = pd.DataFrame([row]).to_csv(index=False).encode()
    app = app_page(PROFILES_PAGE)
    app.file_uploader[0].set_value(("names.csv", csv, "text/csv"))
    app.button[0].click().run()

    assert not app.exception
    assert not app.error
    result = pd.read_csv(io.StringIO(exported_csv(download)), keep_default_na=False)
    assert result.loc[0, "linkedin_id"] == (expected_id or "")
    assert result.loc[0, "other_matches"] == other_matches
    identity = f"Ada_Lovelace_{expected_id}" if expected_id else "Ada_Byron_Lovelace_Example Inc"
    assert result.loc[0, "database_id"] == str(uuid.uuid5(uuid.NAMESPACE_DNS, identity))
    assert result.columns.get_loc("database_id") + 1 == result.columns.get_loc("linkedin_id")
    assert result.loc[0, "middle_name"] == "Byron"
    get.assert_called_once()
    tavily.assert_called_once()


def test_search_error_stops_before_export(app_page, api_mocks, download, json_response):
    _, get, tavily = api_mocks
    get.return_value = json_response({"message": "rate limited"}, status=429)
    app = app_page(PROFILES_PAGE)
    app.file_uploader[0].set_value((
        "names.csv", b"first_name,last_name,middle_name,suffix,organization\nAda,Lovelace,Byron,,Example Inc\n", "text/csv",
    ))
    app.button[0].click().run()
    assert not app.exception
    assert "Brave search aborted" in app.error[0].value
    assert "429" in app.error[0].value
    tavily.assert_not_called()
    download.assert_not_called()
