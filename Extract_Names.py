import streamlit as st
import os
import base64
import pymupdf
import json
import dotenv
import pandas as pd
from openai import OpenAI
from pydantic import BaseModel
from bs4 import BeautifulSoup


# Define structured output of openai completion
class name_individual(BaseModel):
    last_name: str
    first_name: str
    middle_name: str
    suffix: str

class name_list(BaseModel):
    names: list[name_individual]

# Application functions
def process_file(input_file):
    """Process different file types and prepare for OpenAI API"""
    
    if isinstance(input_file, str): # If processing from file
        file_type = input_file.split('.')[-1].lower()

        if file_type in ['jpg', 'jpeg', 'png']:
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

    # else:
    #     return "Unsupported file type"

# prompt = '''Analyze the provided file and extract the names of individuals holding leadership positions or offices, breaking the names down into last name, first name, middle name (or middle initial, such as "J." or "M."), and suffixes (such as "Jr." and "Ph.D."). Return this information in JSON format. If a field is not applicable or unknown, leave it blank.'''
prompt = '''
SYSTEM ROLE: You are a text analysis expert tasked with extracting leadership information from a provided file.

TASK INSTRUCTIONS:

UNDERSTAND: Review the provided file and identify all mentions of individuals holding leadership positions or offices.

BASICS: Determine the format for extracting names, which includes last name, first name, middle name (or middle initial), and suffixes (such as "Jr." and "Ph.D.").

BREAK DOWN: Extract each name into its constituent parts:

Last Name: The family name or surname.
First Name: The given name.
Middle Name/Middle Initial: Any additional names or initials between the first and last names (e.g., "John M. Doe" would have "M." as a middle initial).
Suffixes: Any titles or designations following the full name (e.g., "Jr.", "Ph.D.", etc.).

ANALYZE: If a field is not applicable or unknown, leave it blank. Ensure all extracted information is accurate and consistent in format.

BUILD: Organize the extracted data into JSON format for easy reference.

FINAL ANSWER:Provide the extracted leadership information in JSON format as specified above."
'''

# Get API key from environment variable
if os.path.exists('.env'):
    dotenv.load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def send_to_openai(content, file_type, prompt=prompt, client=client):
    """Send processed content to OpenAI API"""
    try:
        if file_type in ['jpg', 'jpeg', 'png']:
            # For images, use vision capability
            response = client.beta.chat.completions.parse(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "".format(prompt.strip())},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{file_type};base64,{content}"
                                }
                            }
                        ],
                    },
                ],
                response_format=name_list
            )
        else:
            # For text content (HTML, PDF)
            response = client.beta.chat.completions.parse(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "".format(prompt)},
                    {"role": "user", "content": content}
                ],
                response_format=name_list
            )
        
        return response.choices[0].message.content
    
    except Exception as e:
        return f"Error processing content: {str(e)}"

def parse_openai_output(output, organization):
    """Parse OpenAI API output and convert to csv format"""
    data = json.loads(output)
    df = pd.DataFrame(data['names'])
    df['organization'] = organization # Append organization name to each row

    # Remove duplicate rows based on matching the first and last name
    df = df.drop_duplicates(subset=['first_name', 'last_name'], keep='first')

    return df


# Streamlit application
st.title('Extract Names')

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
    result = send_to_openai(f[0], f[1])
    output = parse_openai_output(result, organization)
    st.dataframe(output)
    st.download_button(label="Download CSV", data=output.to_csv(index=False), file_name='1_names.csv', mime='text/csv')


