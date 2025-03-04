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

def api_search(first_name, last_name, middle_name, org, count=5, api_key=BRAVE_SEARCH_API_KEY):
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

def parse_search_results(results):
    matches = []
    # For Brave results
    pattern = r'https://www\.linkedin\.com/in/([^/]+)/' 

    for item in results['web']['results']:
        match = re.fullmatch(pattern, item['url'])
        if match:
            matches.append(match.group(1))
    
    return matches

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
        results = api_search(first_name, last_name, middle_name, org)
        profiles = parse_search_results(results)

        # Write database_id to the dataframe
        df.at[index, 'database_id'] = uuid.uuid4()

        # Update the dataframe with the results
        if len(profiles) > 0:
            df.at[index, 'linkedin_id'] = profiles[0]
            df.at[index, 'other_matches'] = ', '.join(profiles[1:])
        
        st.write(f'{first_name} {last_name} from {org}:', ','.join(profiles))
        time.sleep(5)
    
    st.dataframe(df)
    st.download_button('Download CSV', df.to_csv(), file_name='2_linkedin_identifiers.csv', mime='text/csv')
    

