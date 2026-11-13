# Regression tests

From the repository root, install the locked dependencies (including test tools) and run:

```sh
uv sync --locked --group dev
uv run --locked pytest -q
```

Run just the Streamlit workflows or an individual test while making changes:

```sh
uv run --locked pytest tests/test_app.py -q
uv run --locked pytest -k profile_selection -q
```

The suite covers:

- PDF, HTML, and image preparation from file paths and Streamlit uploads.
- Structured name fields, response parsing, deduplication, and CSV output.
- OpenRouter request formats, transport/HTTP failures, invalid JSON, and provider errors.
- Brave and Tavily queries, LinkedIn URL filtering, and shared profile selection.
- Both Streamlit forms, required inputs, CSV handoff between pages, profile fallbacks, and deterministic database IDs.

All responses are in-memory fixtures or mocks. Tests supply dummy API keys and
disable `.env` loading, so no credentials or sample files are needed. The pytest
configuration uses `pytest-socket` to block TCP/IP sockets and DNS for every test.
Local Unix sockets remain available for Streamlit's test runner; no server or
browser is started. Unexpected live API calls cannot reach the network.

The tests check the application against representative provider responses; they
do not check the availability or accuracy of the live services.
