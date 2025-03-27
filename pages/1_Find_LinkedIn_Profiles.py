import streamlit as st
import os
import dotenv
import pandas as pd
import requests
import re
import json
import time
import uuid


if os.path.exists('.env'):
    dotenv.load_dotenv()

BRAVE_SEARCH_API_KEY = os.environ.get('BRAVE_SEARCH_API_KEY')
BRIGHTDATA_API_KEY = os.environ.get('BRIGHTDATA_API_KEY')

def brave_search(first_name, last_name, middle_name, org, count=5, api_key=BRAVE_SEARCH_API_KEY):
    endpoint = 'https://api.search.brave.com/res/v1/web/search'
    headers = {'X-Subscription-Token': api_key}

    # Build query string
    query = '{} {} {} {} "LinkedIn"'.format(first_name, middle_name, last_name, org)
    
    params = {
        'q': query,
        'results_filter': 'web',
        'count': count
    }
    response = requests.get(endpoint, params=params, headers=headers)
    return response.json()

def parse_brave_results(results):
    matches = []
    # For Brave results
    pattern = r'https://www\.linkedin\.com/in/([^/]+)/' 

    for item in results['web']['results']:
        match = re.fullmatch(pattern, item['url'])
        if match:
            matches.append(match.group(1))
    
    return matches

def brightdata_search(first_name, last_name, middle_name, org, count=10, api_key=BRIGHTDATA_API_KEY):
    """
    Search for individuals using the BrightData API

    Parameters:
        first_name (str): The first name of the individual
        last_name (str): The last name of the individual
        middle_name (str): The middle name of the individual
        org (str): The organization the individual is associated with
        count (int): The number of search results to return
        api_key (str): The API key for the BrightData API

    Returns:
        dict: A dictionary containing the search results
    """
    # Build query string
    # Filter out NaN values from name parts
    name_parts = [part for part in [first_name, middle_name, last_name] if not pd.isna(part)]

    # If any name parts have a space in them (e.g. the LLM failed to correctly parse the middle initial), split them and take only the first section
    name_parts = [part.split()[0] if ' ' in part else part for part in name_parts]

    # Create the search string by joining name parts and organization
    search_string = '+'.join(name_parts)
    if not pd.isna(org):
        search_string += '+' + '+'.join(org.split())
    
    # Add LinkedIn to the search string
    search_string += '+LinkedIn'

    # Check the search url for non-ascii characters
    url = requests.utils.requote_uri('https://www.google.com/search?q={}&gl=us&brd_json=1&num={}'.format(search_string, count))
    
    endpoint = 'https://api.brightdata.com/request'
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer {}".format(api_key)
    }

    payload = {
        "zone": "career_database_project",
        "url": url,
        "format": "raw"
    }

    response = requests.post(endpoint, headers=headers, json=payload)
    return response.text

def parse_brightdata_results(input_text):
    """
    Parse the search results from the BrightData API

    Parameters:
        input_text (str): The text containing the search results

    Returns:
        list: A list of urls that match the LinkedIn pattern
    """

    pattern = r'https://www\.linkedin\.com/in/([^/]+)' 
    matches = []
    
    # Extract the JSON data from the input text
    data = json.loads(input_text)

    # Extract the relevant information from the search results
    for result in data['organic']:
        match = re.fullmatch(pattern, result['link'])
        if match:
            matches.append(match.group(1))

    return matches

def find_matching_profile(list1, list2):
    """
    This function accepts two lists and returns the first matching value found.
    If no matching value exists, it returns None.
    
    Parameters:
        list1 (list): The first list of values.
        list2 (list): The second list of values.
    
    Returns:
        The first matching value found between the two lists, or None if there is no match.
    """
    for item in list1:
        if item in list2:
            return item
    return None

# Streamlit Application
st.title('Find LinkedIn Profiles')

with st.form(clear_on_submit=True, enter_to_submit=False, key='find_profiles'):
    user_upload = st.file_uploader('Upload a CSV file generated on the previous page.', type=['csv'])
    submit_csv = st.form_submit_button('Find LinkedIn Profiles')

if submit_csv:
    if user_upload is not None:
        df = pd.read_csv(user_upload, dtype={
            'first_name': str,
            'last_name': str,
            'middle_name': str,
            'suffix': str,
            'organization': str,
            'linkedin_id': str,
            'other_matches': str,
            'database_id': 'Int64'
            })
    else:
        st.write('Please upload a CSV file.')
        st.stop()
    
    for index, row in df.iterrows():
        first_name = row['first_name']
        last_name = row['last_name']
        middle_name = row['middle_name']
        org = row['organization']
        results1 = brave_search(first_name, last_name, middle_name, org)
        results2 = brightdata_search(first_name, last_name, middle_name, org)
        profiles1 = parse_brave_results(results1)
        profiles2 = parse_brightdata_results(results2)

        # Write database_id to the dataframe
        df.at[index, 'database_id'] = str(uuid.uuid4())

        # Update the dataframe with the results
        if len(profiles1) > 0 or len(profiles2) > 0:
            profile_match = find_matching_profile(profiles1, profiles2)
            if profile_match:
                df.at[index, 'linkedin_id'] = profile_match
                df.at[index, 'other_matches'] = ', '.join([profile for profile in profiles1 + profiles2 if profile != profile_match])
                st.write(f'{first_name} {last_name} from {org}. MATCH:', profile_match)
                st.write(f'{first_name} {last_name} from {org}:', ', '.join(profiles2 + profiles1))
            else:
                main_profile = profiles2[0] if len(profiles2) > 0 else profiles1[0]
                df.at[index, 'linkedin_id'] = profiles2[0] if len(profiles2) > 0 else profiles1[0]
                df.at[index, 'other_matches'] = ', '.join([profile for profile in profiles1 + profiles2 if profile != main_profile])
                st.write(f'{first_name} {last_name} from {org}:', ', '.join(profiles2 + profiles1))
        
        time.sleep(5)
    
    st.dataframe(df)
    st.download_button('Download CSV', df.to_csv(index=False), file_name='2_linkedin_identifiers.csv', mime='text/csv')
    

