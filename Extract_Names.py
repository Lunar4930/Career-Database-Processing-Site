import streamlit as st
import os
import base64
import pymupdf
import json
import dotenv
import requests
import re
import pandas as pd
from pydantic import BaseModel, Field
from bs4 import BeautifulSoup

# Configure constants
prompt = '''
Role: You are a precise data extraction assistant specialized in Natural Language Processing (NLP).
Task: Extract every individual person's name from the input and structure it according to the provided JSON schema.

Extraction Rules:
Titles & Prefixes: IGNORE titles (e.g., Mr., Ms., Dr., Prof., Cpt.). Do not include them in first_name.
Middle Names: If a person has a middle name or initial, map it to middle_name. If there are multiple middle names (e.g. "Mary Jo Ann"), combine them into this string.
Suffixes: Capture generational or professional suffixes (e.g., Jr., Sr., III, PhD, MD) in the suffix field.
Compound Surnames: Respect compound last names (e.g., "De La Hoya", "Van der Woodsen"). Keep them intact in last_name.
Missing Data: If a field (like middle_name or suffix) is not present in the text, you MUST return null. Do not use "N/A" or empty strings.
'''

model = "qwen/qwen3-vl-235b-a22b-instruct"

# Get API key from environment variable
if os.path.exists('.env'):
    dotenv.load_dotenv()

OPENROUTER_API_KEY=os.environ.get("OPENROUTER_API_KEY")

# Define structured output
class NameIndividual(BaseModel):
    # Required fields: A person almost always has these
    first_name: str = Field(..., description="The first or given name.")
    last_name: str = Field(..., description="The last or family name.")
    
    # Optional fields: Set to None by default
    middle_name: str | None = Field(None, description="Middle name or initial, if present.")
    suffix: str | None = Field(None, description="Generational suffix or post-nominal letters (e.g., Jr., III, Ph.D.), if present.")

class NameList(BaseModel):
    names: list[NameIndividual]

# Define schema dictionary
schema_param = {
    "type": "json_schema",
    "json_schema": {
        "name": "name_list",
        "schema": NameList.model_json_schema(),
        "strict": True
    }
}

# Application functions
def process_file(input_file):
    """Process different file types and prepare for API"""
    
    if isinstance(input_file, str): # If processing from file
        file_type = input_file.split('.')[-1].lower()
       
        if file_type == 'jpg': # Normalize jpg to jpeg for consistency and compatibility
            file_type = 'jpeg'

        if file_type in ['jpeg', 'png']:
            # Process image
            with open(input_file, "rb") as image_file:
                return (base64.b64encode(image_file.read()).decode('utf-8'), file_type)
                
        elif file_type == 'html':
            # Process HTML
            with open(input_file, "r") as html_file:
                soup = BeautifulSoup(html_file.read(), 'html.parser')
                return (soup.get_text(), file_type)
                
        elif file_type == 'pdf':
            # Process PDF
            text = ""
            with pymupdf.open(input_file) as doc:
                for page in doc:
                    text += page.get_text()
            return (text, file_type)
    
    else: # If processing from file upload
        file_type = input_file.type.split('/')[-1].lower()

        if file_type in ['jpg', 'jpeg', 'png']:
            # Process image
            return (base64.b64encode(input_file.read()).decode('utf-8'), file_type)
                
        elif file_type == 'html':
            # Process HTML
            soup = BeautifulSoup(input_file.read(), 'html.parser')
            return (soup.get_text(), file_type)
                
        elif file_type == 'pdf':
            # Process PDF
            pdf_bytes = input_file.read()
            text = ""
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text()
            return (text, file_type)

def send_to_openrouter(content, file_type, prompt=prompt, model=model):
    """
    Send content to OpenRouter API for name extraction.

    Args:
        content (str): The content to be processed (base64 for images, text for HTML/PDF).
        file_type (str): The type of the file ('jpg', 'png', 'html', 'pdf').
        prompt (str): The prompt to guide the LLM.
        model (str): The model to use for processing.
       
    Returns:
        requests.Response: The response from the OpenRouter API.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
}
    try:
        # For image content
        if file_type in ['jpg', 'jpeg', 'png']:
            payload = {
                "model": f"{model}",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{file_type};base64,{content}"
                                }
                            }
                        ]
                    }
                ],
                "response_format": schema_param,
                "temperature": 0
            }
        else:
            # For text content (HTML, PDF)
            payload = {
                "model": f"{model}",
                "messages": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": content
                            }
                        ]
                    }
                ],
                "response_format": schema_param,
                "temperature": 0
            }

        # Check for API response
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise an error for bad status codes
        
        # Parse the JSON to check for internal API errors
        class APIProviderError(Exception):
            """Exception raised for errors returned within a successful HTTP response."""
            def __init__(self, message, code=None):
                self.message = message
                self.code = code
                super().__init__(self.message)

        data = response.json()
        if isinstance(data, dict) and 'error' in data:
            error_info = data['error']
            error_code = error_info.get('code')
            error_msg = error_info.get('message')

            # Raise custom error with the details from the provider
            raise APIProviderError(f"[{error_code}] {error_msg}", code=error_code)
    
        return response
    
    except Exception as e:
        return f"Error processing content: {str(e)}"

def parse_response_output(response, organization):
    """
    Parse API response output and convert to csv format.

    Args:
        response (dict): The response from the LLM API.
        organization (str): The name of the organization to append to each row.

    Returns:
        pd.DataFrame: DataFrame containing extracted names with organization column.
    """
    content_str = response.json()['choices'][0]['message']['content']

    # Remove markdown code block markers (handles ```json or ```)
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content_str)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = content_str  # Fallback if no markdown fences found
    
    # Parse the JSON string into a Python object (list/dict)
    data = json.loads(json_str)

    df = pd.DataFrame(data)
    df['organization'] = organization # Append organization name to each row

    # Remove duplicate rows based on matching the first and last name
    df = df.drop_duplicates(subset=['first_name', 'last_name'], keep='first')

    return df


# Streamlit application
st.title('Extract Names')
st.write('v2026.02.02')

with st.form(clear_on_submit=True, enter_to_submit=False, key='extract_names'):
    organization = st.text_input('Enter the name of the organization.')
    uploaded_file = st.file_uploader('Upload a PDF, HTML, or image file containing names of people from the organization. Uploaded files will be sent to OpenAI.', type=['pdf', 'html', 'png', 'jpg', 'jpeg'])
    activate_process_file = st.form_submit_button('Process File')

if activate_process_file:
    if uploaded_file is None:
        st.error('Please upload a file')
        st.stop()
    elif organization == '':
        st.error('Please enter the name of the organization')
        st.stop()
    f = process_file(uploaded_file)
    result = send_to_openrouter(f[0], f[1])
    output = parse_response_output(result, organization)
    st.dataframe(output)
    st.download_button(label="Download CSV", data=output.to_csv(index=False), file_name='1_names.csv', mime='text/csv')


