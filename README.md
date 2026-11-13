# Career Database Processing Site

A Streamlit app for extracting names from uploaded files and finding matching LinkedIn profiles.

## What it does
- Uses language models to extract names from PDF/HTML/image files and exports them to CSV.
- Searches for LinkedIn profile IDs using Brave and BrightData APIs.
- Outputs structured data for subsequent processing.

## Setup
1. Install [UV](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it already.
2. Create a `.env` file with:
   - `OPENROUTER_API_KEY`
   - `BRAVE_SEARCH_API_KEY`
   - `TAVILY_API_KEY`
3. Install dependencies and create a virtual environment:
   - `uv sync`

## Run
- `uv run streamlit run Extract_Names.py`

## Demo
*Note: The Safari Browser may have trouble playing this video*

https://github.com/user-attachments/assets/52b6d124-a4bb-45e7-9676-6b6630a1bb9d

## Development

For regression tests: from the repository root, install the development dependencies and run the full suite:

```sh
uv sync --locked --group dev
uv run --locked pytest -q
```

`uv run` runs pytest in the project's virtual environment. `--locked` requires `uv.lock` to match the project configuration and fails if it needs updating. `-q` shows compact progress, failure details, and a final summary.

See [tests/README.md](tests/README.md) for more details.
