# -*- coding: utf-8 -*-
"""
Created on Mon Jan 22 20:14:49 2024

Austrlian Labolur Market - National Skills Commission

@author: Artoss
"""

import requests
import json
import pandas as pd
from bs4 import BeautifulSoup


cookies = {
    'ak_bmsc': 'CF595EEB9D8A0E9138E21AB950DE0AB6~000000000000000000000000000000~YAAQjZZUuE3uly+NAQAAxm0NMRafYb4oC3ydhrYb8mlPQJWPOuWgYc99d1zBI64Ec2AFAeMwy1v4Ny3jMgup8BnyU2uduzngCRc1X2HXEv69d/9IWrQHT9Gwvzx/gTSXqVeMHyyf4CyuRCtFqbC9UnO3qat2Yhq5alduNCsZrquheGTdm+EEZ92RZiSaNR8pCqORJkGn0+dLqRWmwEm/G0QN21MWmzqygDEp1ZNs4ELepLqvWIagVXQpdKpIwzUfernVNqvKJgEWHDDO/WALqExp/DgHMTy3+LVODmxi8CxF072wU3YE7CqIZTpsPHonrsom7AYCqRbYRcnwnZrxgIkOI955hsJpNETV1WoMrhNJCU8XaH36BDm5lnfrkUVrw5eb8xGkURFQY/fxZYNzI5k/Ia/mJH3Sqk1Gdqp5RhuWyLtmrjTjvOAD9eDiUZ7MHPagJGB5nk0QTnLiqDSsDwRk4f1M+AilYdX59qDsf+FScISvrz8KGnqqVM9ipwkOLF2HXrCkDOGnwTc=',
    'bm_sv': '5B9F13DCC49343D4DC76CBFCF9CB256F~YAAQjZZUuG8GmC+NAQAAd0wRMRZjO5fAgFprRaTBsUkO7Ac2y+I2S7kOFCSqCDWIZNfqhk/RCSmO4xcVfgS3Lvh0rcWvZeOPS7usGaLAKQlQhkEKlqmOmcRTBK8evCbBW6d06UuvpOg9zWZl6gC7I8DzVkjayz+ZqWFucRXa1EjeXq7jDnAVfWlqawzE9tXeUuF+pediQ637FAS/YppiOkHKwVa9hdvArDgJrwQhSeshupwCp+lck5iXLz2WVTCxTPVH5zQuKjMSvDo=~1',
    'ai_user': 'jBoeT6M4E5fMZ6nNw11+wB|2024-01-22T12:02:57.994Z',
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.5',
    # 'Accept-Encoding': 'gzip, deflate, br',
    'X-NewRelic-ID': 'VwEGWVNWCxAEVVJQBQkAUVU=',
    'newrelic': 'eyJ2IjpbMCwxXSwiZCI6eyJ0eSI6IkJyb3dzZXIiLCJhYyI6IjM3MTg1NTMiLCJhcCI6IjUzNTg5MjM3OSIsImlkIjoiZWRkMmI5NmZhMzI2M2IwOCIsInRyIjoiMTkwNGRkMmY2Mjg4OWEyNDhlZTlmYjM5NGNjMzkwZDMiLCJ0aSI6MTcwNTkyNTIzMzYyMH19',
    'traceparent': '00-1904dd2f62889a248ee9fb394cc390d3-edd2b96fa3263b08-01',
    'tracestate': '3718553@nr=0-1-3718553-535892379-edd2b96fa3263b08----1705925233620',
    'X-Requested-With': 'XMLHttpRequest',
    'Connection': 'keep-alive',
    'Referer': 'https://www.jobsandskills.gov.au/jobs-and-skills-atlas-dashboard?nav=sa4&tab=sa4-map&region=101',
    # 'Cookie': 'ak_bmsc=CF595EEB9D8A0E9138E21AB950DE0AB6~000000000000000000000000000000~YAAQjZZUuE3uly+NAQAAxm0NMRafYb4oC3ydhrYb8mlPQJWPOuWgYc99d1zBI64Ec2AFAeMwy1v4Ny3jMgup8BnyU2uduzngCRc1X2HXEv69d/9IWrQHT9Gwvzx/gTSXqVeMHyyf4CyuRCtFqbC9UnO3qat2Yhq5alduNCsZrquheGTdm+EEZ92RZiSaNR8pCqORJkGn0+dLqRWmwEm/G0QN21MWmzqygDEp1ZNs4ELepLqvWIagVXQpdKpIwzUfernVNqvKJgEWHDDO/WALqExp/DgHMTy3+LVODmxi8CxF072wU3YE7CqIZTpsPHonrsom7AYCqRbYRcnwnZrxgIkOI955hsJpNETV1WoMrhNJCU8XaH36BDm5lnfrkUVrw5eb8xGkURFQY/fxZYNzI5k/Ia/mJH3Sqk1Gdqp5RhuWyLtmrjTjvOAD9eDiUZ7MHPagJGB5nk0QTnLiqDSsDwRk4f1M+AilYdX59qDsf+FScISvrz8KGnqqVM9ipwkOLF2HXrCkDOGnwTc=; bm_sv=5B9F13DCC49343D4DC76CBFCF9CB256F~YAAQjZZUuG8GmC+NAQAAd0wRMRZjO5fAgFprRaTBsUkO7Ac2y+I2S7kOFCSqCDWIZNfqhk/RCSmO4xcVfgS3Lvh0rcWvZeOPS7usGaLAKQlQhkEKlqmOmcRTBK8evCbBW6d06UuvpOg9zWZl6gC7I8DzVkjayz+ZqWFucRXa1EjeXq7jDnAVfWlqawzE9tXeUuF+pediQ637FAS/YppiOkHKwVa9hdvArDgJrwQhSeshupwCp+lck5iXLz2WVTCxTPVH5zQuKjMSvDo=~1; ai_user=jBoeT6M4E5fMZ6nNw11+wB|2024-01-22T12:02:57.994Z',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-GPC': '1',
    # 'If-Modified-Since': 'Mon, 15 Jan 2024 06:25:29 GMT',
    # Requests doesn't support trailers
    # 'TE': 'trailers',
}

s = requests.Session()
# s.update(headers)
s.get('https://www.jobsandskills.gov.au/jobs-and-skills-atlas-dashboard?nav=sa4&tab=sa4-map&region=101')

url = 'https://www.jobsandskills.gov.au/system/files/datasets/glmdOccRecent-2023-11_0.json'

url_base = 'https://www.jobsandskills.gov.au/'
url_path = 'system/files/datasets/'
url_file = 'glmdOccRecent-2023-11_0.json'

urlfull = f"{url_base}{url_path}(url_file)"

response = requests.get(
    'https://www.jobsandskills.gov.au/system/files/datasets/glmdOccRecent-2023-11_0.json',
    cookies=cookies,
    headers=headers,
)

print(response.status_code, response.reason)

df_data = pd.DataFrame(response.json())

#%%

import requests

# Get ANZCO codes (?? only retrieves ~37 codes)

cookies = {
    'ak_bmsc': 'CF595EEB9D8A0E9138E21AB950DE0AB6~000000000000000000000000000000~YAAQjZZUuE3uly+NAQAAxm0NMRafYb4oC3ydhrYb8mlPQJWPOuWgYc99d1zBI64Ec2AFAeMwy1v4Ny3jMgup8BnyU2uduzngCRc1X2HXEv69d/9IWrQHT9Gwvzx/gTSXqVeMHyyf4CyuRCtFqbC9UnO3qat2Yhq5alduNCsZrquheGTdm+EEZ92RZiSaNR8pCqORJkGn0+dLqRWmwEm/G0QN21MWmzqygDEp1ZNs4ELepLqvWIagVXQpdKpIwzUfernVNqvKJgEWHDDO/WALqExp/DgHMTy3+LVODmxi8CxF072wU3YE7CqIZTpsPHonrsom7AYCqRbYRcnwnZrxgIkOI955hsJpNETV1WoMrhNJCU8XaH36BDm5lnfrkUVrw5eb8xGkURFQY/fxZYNzI5k/Ia/mJH3Sqk1Gdqp5RhuWyLtmrjTjvOAD9eDiUZ7MHPagJGB5nk0QTnLiqDSsDwRk4f1M+AilYdX59qDsf+FScISvrz8KGnqqVM9ipwkOLF2HXrCkDOGnwTc=',
    'bm_sv': '5B9F13DCC49343D4DC76CBFCF9CB256F~YAAQjZZUuG8GmC+NAQAAd0wRMRZjO5fAgFprRaTBsUkO7Ac2y+I2S7kOFCSqCDWIZNfqhk/RCSmO4xcVfgS3Lvh0rcWvZeOPS7usGaLAKQlQhkEKlqmOmcRTBK8evCbBW6d06UuvpOg9zWZl6gC7I8DzVkjayz+ZqWFucRXa1EjeXq7jDnAVfWlqawzE9tXeUuF+pediQ637FAS/YppiOkHKwVa9hdvArDgJrwQhSeshupwCp+lck5iXLz2WVTCxTPVH5zQuKjMSvDo=~1',
    'ai_user': 'jBoeT6M4E5fMZ6nNw11+wB|2024-01-22T12:02:57.994Z',
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.5',
    # 'Accept-Encoding': 'gzip, deflate, br',
    'X-NewRelic-ID': 'VwEGWVNWCxAEVVJQBQkAUVU=',
    'newrelic': 'eyJ2IjpbMCwxXSwiZCI6eyJ0eSI6IkJyb3dzZXIiLCJhYyI6IjM3MTg1NTMiLCJhcCI6IjUzNTg5MjM3OSIsImlkIjoiNDgzMGQ4NTZlM2M2MDVjMyIsInRyIjoiNTRkMDUyNTQ3YzM2YWMzOTViYTk3NDE5MWU3YTEwY2IiLCJ0aSI6MTcwNTkyNTIzMzYyNH19',
    'traceparent': '00-54d052547c36ac395ba974191e7a10cb-4830d856e3c605c3-01',
    'tracestate': '3718553@nr=0-1-3718553-535892379-4830d856e3c605c3----1705925233624',
    'X-Requested-With': 'XMLHttpRequest',
    'Connection': 'keep-alive',
    'Referer': 'https://www.jobsandskills.gov.au/jobs-and-skills-atlas-dashboard?nav=sa4&tab=sa4-map&region=101',
    # 'Cookie': 'ak_bmsc=CF595EEB9D8A0E9138E21AB950DE0AB6~000000000000000000000000000000~YAAQjZZUuE3uly+NAQAAxm0NMRafYb4oC3ydhrYb8mlPQJWPOuWgYc99d1zBI64Ec2AFAeMwy1v4Ny3jMgup8BnyU2uduzngCRc1X2HXEv69d/9IWrQHT9Gwvzx/gTSXqVeMHyyf4CyuRCtFqbC9UnO3qat2Yhq5alduNCsZrquheGTdm+EEZ92RZiSaNR8pCqORJkGn0+dLqRWmwEm/G0QN21MWmzqygDEp1ZNs4ELepLqvWIagVXQpdKpIwzUfernVNqvKJgEWHDDO/WALqExp/DgHMTy3+LVODmxi8CxF072wU3YE7CqIZTpsPHonrsom7AYCqRbYRcnwnZrxgIkOI955hsJpNETV1WoMrhNJCU8XaH36BDm5lnfrkUVrw5eb8xGkURFQY/fxZYNzI5k/Ia/mJH3Sqk1Gdqp5RhuWyLtmrjTjvOAD9eDiUZ7MHPagJGB5nk0QTnLiqDSsDwRk4f1M+AilYdX59qDsf+FScISvrz8KGnqqVM9ipwkOLF2HXrCkDOGnwTc=; bm_sv=5B9F13DCC49343D4DC76CBFCF9CB256F~YAAQjZZUuG8GmC+NAQAAd0wRMRZjO5fAgFprRaTBsUkO7Ac2y+I2S7kOFCSqCDWIZNfqhk/RCSmO4xcVfgS3Lvh0rcWvZeOPS7usGaLAKQlQhkEKlqmOmcRTBK8evCbBW6d06UuvpOg9zWZl6gC7I8DzVkjayz+ZqWFucRXa1EjeXq7jDnAVfWlqawzE9tXeUuF+pediQ637FAS/YppiOkHKwVa9hdvArDgJrwQhSeshupwCp+lck5iXLz2WVTCxTPVH5zQuKjMSvDo=~1; ai_user=jBoeT6M4E5fMZ6nNw11+wB|2024-01-22T12:02:57.994Z',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-GPC': '1',
    # Requests doesn't support trailers
    # 'TE': 'trailers',
}

res2 = requests.get('https://www.jobsandskills.gov.au/system/files/datasets/clean.json', cookies=cookies, headers=headers)

if res2.status_code == 200:
    res2_json = res2.json()

else:
    print(f'Error: {res2.status_code}, {res2.reason}')


#%%

# Lists of web pages with content

data_sources = [
    'https://www.jobsandskills.gov.au/data/employment-projections', 
    'https://www.jobsandskills.gov.au/data/labour-market-updates/labour-force-updates', 
    'https://www.jobsandskills.gov.au/data/small-area-labour-markets', 
    'https://www.jobsandskills.gov.au/work/small-area-labour-markets/methodology',
    'https://www.jobsandskills.gov.au/data/internet-vacancy-index', 
    'https://www.jobsandskills.gov.au/data/recruitment-experiences-and-outlook-survey', 
    'https://www.jobsandskills.gov.au/data/labour-market-insights',
    'https://www.jobsandskills.gov.au/data/skills-shortages-analysis', 
    'https://www.jobsandskills.gov.au/data/vet-national-data-asset-vnda'
    ]

# Data tools includes metadata for various datasets
data_tools = [
    'https://www.jobsandskills.gov.au/data/australian-skills-classification',
    'https://www.jobsandskills.gov.au/data/skills-priority-list',
    'https://www.jobsandskills.gov.au/data/labour-market-insights/industries',
    'https://www.jobsandskills.gov.au/data/labour-market-insights/occupations',
    'https://www.jobsandskills.gov.au/data/qualification-similarity-analysis'
    ]

dashboards = [
    'https://www.jobsandskills.gov.au/data/jobs-and-skills-atlas', 
    'https://www.jobsandskills.gov.au/data/employment-region-dashboards-and-profiles', 
    'https://www.jobsandskills.gov.au/data/nero'
    ]


#%%

"""  
First crawl the webpage to extract all the download links 
and then download each file to the specified path/folder.

JAVASCRIPT option: See https://stackoverflow.com/questions/65836824/how-to-scrape-hyperlink-from-function-inside-javascript-tag-no-elements-used-in
and https://gist.github.com/usahg/1702880
https://thepythoncode.com/article/extract-all-website-links-python
"""

import requests
import urllib3
from urllib.parse import urlparse, urljoin


# Supress warnings 'InsecureRequestWarning: Unverified HTTPS request'
# See https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings
urllib3.disable_warnings()


def get_uri_links(archive_url):
    """
    Get a list of links from a webpage (archive_url) that meet criteria
    
    Parameters
    ----------
    archive_url : string
        URL of the webpage that has the download links required.

    Returns
    -------
    links : string
        List of URI to files (http/s protocol).

    """
    
    base_url = archive_url.split('/')[0] + "//" + archive_url.split('/')[2]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
      }
    
    # create response object
    r = requests.get(archive_url, verify=False, headers=headers)

    # create beautiful-soup object
    soup = BeautifulSoup(r.content,'lxml')

    # find all links on web-page
    hyperlinks = soup.findAll('a')

    # filter the link sending with required file extension
    # links = [link['href'] for link in links if link['href'].endswith(('xls', 'xlsx', 'csv'))]
    # REFACTOR try/except - Explicit check that 'href' is in <a> tag
        # for a_href in soup.find_all("a", href=True):
        # print(a_href["href"])
    
    links = []
    for link in hyperlinks:
        try:
            if link['href'].endswith(('xls', 'xlsx', 'csv')):
                if link['href'].startswith('http'):
                    links.append(link['href'])
                elif link['href'].startswith('/'):
                    links.append(base_url + link['href'])
                else:
                    links.append(base_url + "/" + link['href'])
        except(KeyError):
            continue

    return links


def download_url_series(url_links):
    """
    Download files to local drive from list of url_links.

    Parameters
    ----------
    url_links : LIST of STRINGS
        DESCRIPTION.
        Full url to file including file extension
    Returns
    -------
    None.

    """
    for link in url_links:  
  
        '''iterate through all links in links and download them one by one'''

        # Check valid url link
        if is_valid_url(link):
            # All good
            pass
        else:
            # Url is not valid, loop to next link in url_links
            continue

        # obtain filename by splitting url and getting  
        # last string
        if link:
            try:
                file_name = link.split('/')[-1]  
            except Exception as err:
                print(err)
                break

        print( "Downloading file:%s"%file_name)  

        # create response object  
        r = requests.get(link, stream = True, verify=False)

        # download started  
        with open('./Output/'+file_name, 'wb') as f:  
            for chunk in r.iter_content(chunk_size = 1024*1024):  
                if chunk:  
                    f.write(chunk)  

        print( "%s downloaded!\n"%file_name ) 

    print ("All files downloaded!") 
    return


def is_valid_url(url):
    """
    Checks whether `url` is a valid URL.

    Parameters
    ----------
    url : STRING
        DESCRIPTION.
        Full url to be validated.
    Returns
    -------
    Boolean: TRUE if valid url

    """
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)


if __name__ == "__main__":  

    # specify the URL of the archive here  
    # archive_url = data_sources[2]
    
    # WA Government rental bond data - EXAMPLE
    # bond_webpage = "https://housing-data-exchange.ahdap.org/dataset/west-australia-rental-bonds-data-2023-current"
    # archive_url = bond_webpage
    links = list()
    # Other
    print("Getting URL file links")
    for ele in data_sources:
    # for ele in data_tools:
        links.extend(get_uri_links(ele))
    
    # getting all links  
    # links = get_uri_links(archive_url)

    # download all files
    print('Downloading files')
    download_url_series(links)

# for url in data_sources:
# aaa = get_uri_links(data_sources[2])

#%%

# SALM data - smoothed

# Read csv file from web url into a Pandas dataframe
# df = pd.read_csv(links[2], header=1, na_values='-', index_col=[0,1])

# Create a blank dictionary to store dataframes
df_salm = dict()

# Read Excel files from the web link and then create dataframe(s) from sheet(s)
# NB 'links[1]' is URL of the spreadsheet to import to dataframe(s)
with pd.ExcelFile(links[1]) as xlsx:
    for sheet_n in xlsx.sheet_names:
        d_name = sheet_n.replace(' ', '_')
        df_salm[sheet_n] = pd.read_excel(xlsx, sheet_name=sheet_n, header=3, 
                                         index_col=[1,0], na_values='-'
                                         )
        if 'rate' in sheet_n:
            try:
                df_salm[sheet_n] = df_salm[sheet_n].astype('float32')
            except Exception as err:
                print(err)
        else:
            try:
                df_salm[sheet_n] = df_salm[sheet_n].astype('Int64')
            except Exception as err:
                print(err)

        df_salm[sheet_n].insert(0, 'Dataset_type', d_name)

