import json
import os
import re
import time
import uuid

import dotenv
import pandas as pd
import requests
import streamlit as st

from tavily import TavilyClient

if os.path.exists('.env'):
    dotenv.load_dotenv()

BRAVE_SEARCH_API_KEY = os.environ.get('BRAVE_SEARCH_API_KEY')
BRIGHTDATA_API_KEY = os.environ.get('BRIGHTDATA_API_KEY')
TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
TAVILY_CLIENT = TavilyClient(TAVILY_API_KEY)

def brave_search(first_name, last_name, middle_name, org, count=5, api_key=BRAVE_SEARCH_API_KEY):
    endpoint = 'https://api.search.brave.com/res/v1/web/search'
    headers = {'X-Subscription-Token': api_key}

    # Build query string
    query = f'{first_name} {middle_name} {last_name} {org} "LinkedIn"'
    
    params = {
        'q': query,
        'results_filter': 'web',
        'count': count
    }
    response = requests.get(endpoint, params=params, headers=headers) # type: ignore
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

def tavily_search(first_name, last_name, middle_name, org, count=10, tavily_client=TAVILY_CLIENT):
    """
    Search for individuals using the Tavily API

    Parameters:
        first_name (str): The first name of the individual
        last_name (str): The last name of the individual
        middle_name (str): The middle name of the individual
        org (str): The organization the individual is associated with
        count (int): The number of search results to return
    """
    # Build query string
    name_parts = [part for part in [first_name, middle_name, last_name] if not pd.isna(part)]
    search_string = ' '.join(name_parts)
    if not pd.isna(org):
        search_string += ' ' + org
    search_string += ' LinkedIn'

    response = TAVILY_CLIENT.search(
        query=search_string,
        search_depth="advanced",
        max_results=count,
        include_domains=["linkedin.com"],
        include_favicon=False,
        include_usage=False,
    )
    return response

def parse_tavily_results(results):
    """
    Parse the search results from the Tavily API

    Parameters:
        results (dict): The search results from the Tavily API

    Returns:
        list: A list of urls that match the LinkedIn pattern
    """

    pattern = r'https://www\.linkedin\.com/in/([^/]+)' 
    matches = []

    # Extract the relevant information from the search results
    for result in results['results']:
        match = re.fullmatch(pattern, result['url'])
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
            'database_id': str
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
        results2 = tavily_search(first_name, last_name, middle_name, org)
        profiles1 = parse_brave_results(results1)
        profiles2 = parse_tavily_results(results2)

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

        # Write database_id to the dataframe
        linkedin_id = df.at[index, 'linkedin_id']
        if pd.isna(linkedin_id):
            df.at[index, 'database_id'] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f'{first_name}_{middle_name}_{last_name}_{org}'))
        else:
            df.at[index, 'database_id'] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f'{first_name}_{last_name}_{linkedin_id}'))
        
        time.sleep(3)
        
    # Rearrange columns to have 'database_id' before 'linkedin_id' to preserve backward compatibility with older CSV files
    if 'database_id' in df.columns and 'linkedin_id' in df.columns:
        columns = list(df.columns)
        columns.remove('database_id')

        linkedin_index = columns.index('linkedin_id')
        columns.insert(linkedin_index, 'database_id')

        df = df[columns]

    st.dataframe(df)
    st.download_button('Download CSV', df.to_csv(index=False), file_name=f'{df.organization[0]}_{time.strftime("%Y-%m-%d-%H-%M-%S")}.csv', mime='text/csv')
    

