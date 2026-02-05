# Career Database Processing Site
*By (Brice Bowrey)[https://bowrey.info/]*

A small Streamlit app for extracting names from uploaded file sand finding matching LinkedIn profiles.

## What it does
- Extracts person names from PDF/HTML/image files and exports them to CSV.
- Searches for LinkedIn profile IDs using Brave and BrightData APIs.
- Uses language models to extract structured data for subsequent processing.

## Usability
The Streamlit GUI is designed to make the workflow accessible and easy for collaborators and project stakeholders, with clear steps for uploading documents, reviewing results, and exporting files.

## Setup
1. Create a `.env` file with:
   - `OPENROUTER_API_KEY`
   - `BRAVE_SEARCH_API_KEY`
   - `BRIGHTDATA_API_KEY`
2. Build a development and deployment environment from the devcontainer.json file

## Run
- `streamlit run Extract_Names.py`

## Demo