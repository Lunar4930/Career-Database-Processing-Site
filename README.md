# Career Database Processing Site
*By [Brice Bowrey](https://bowrey.info/)*

A small Streamlit app for extracting names from uploaded files and finding matching LinkedIn profiles.

## What it does
- Uses language models to extract names from PDF/HTML/image files and exports them to CSV.
- Searches for LinkedIn profile IDs using Brave and BrightData APIs.
- Outputs structured data for subsequent processing.

## Setup
1. Create a `.env` file with:
   - `OPENROUTER_API_KEY`
   - `BRAVE_SEARCH_API_KEY`
   - `BRIGHTDATA_API_KEY`
2. Build a development and deployment environment from the devcontainer.json file

## Run
- `streamlit run Extract_Names.py`

## Demo
https://github.com/user-attachments/assets/52b6d124-a4bb-45e7-9676-6b6630a1bb9d

