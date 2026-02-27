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
import urllib3
from urllib.parse import urlparse, urljoin
import os
from scraper_tools import log, get_engine, get_postgresql_engine


urllib3.disable_warnings()

# SALM data sources
data_sources = [
    'https://www.jobsandskills.gov.au/data/small-area-labour-markets', 
    'https://www.jobsandskills.gov.au/work/small-area-labour-markets/methodology'
    ]

"""  
First crawl the webpage to extract all the download links 
and then download each file to the specified path/folder.

JAVASCRIPT option: See https://stackoverflow.com/questions/65836824/how-to-scrape-hyperlink-from-function-inside-javascript-tag-no-elements-used-in
and https://gist.github.com/usahg/1702880
https://thepythoncode.com/article/extract-all-website-links-python
"""

# Supress warnings 'InsecureRequestWarning: Unverified HTTPS request'
# See https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings


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
            # if link['href'].endswith(('xls', 'xlsx', 'csv')):
            if link['href'].endswith(('xls', 'xlsx')):
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

    print ("All files downloaded") 
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


def main():
    """
    Returns
    -------
    None.
    """
    return None


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
# engine = get_postgresql_engine()

if links:

    with pd.ExcelFile(links[1]) as xlsx:
        for sheet_n in xlsx.sheet_names:
            d_name = sheet_n.replace(' ', '_')
            # Create dataframe using row 3 as headers, first two columns as multi-index
            # (in reversed order 1,0), and converting a dashes '-' to NaN values
            df_salm[sheet_n] = pd.read_excel(xlsx, 
                                            sheet_name=sheet_n, 
                                            header=3, 
                                            index_col=[1,0], 
                                            na_values='-'
                                            )
            if 'rate' in sheet_n:
                # Data are unemployment 'rate's accurate to 1 decimal point
                try:
                    # Assumes all columns are data only (no index values)
                    df_salm[sheet_n] = df_salm[sheet_n].astype('float32')
                except Exception as err:
                    print(err)
            else:
                # Data are not unemployment 'rate', therefore must be integers 
                # - either no. enemployed or no. in labour force
                try:
                    # Assumes all columns are data only (no index values)
                    df_salm[sheet_n] = df_salm[sheet_n].astype('Int64')
                except Exception as err:
                    print(err)

            df_salm[sheet_n].insert(0, 'Dataset_type', "SALM_" + d_name)
            # df_salm[sheet_n] = df_salm[sheet_n].reset_index()  # No index
            # Convert multi-index back to single index as primary key in PostgreSQL
            df_salm[sheet_n] = df_salm[sheet_n].set_index([df_salm[sheet_n].index.droplevel(1)])
            schema_name = 'public'
            df_salm[sheet_n].to_sql(d_name, 
                                    get_engine(), 
                                    if_exists='replace', 
                                    schema=schema_name, 
                                    index=False, 
                                    method='multi', 
                                    chunksize=1000
                                    )
    # Note - Need to dispose of engine after use: https://docs.sqlalchemy.org/en/20/core/connections.html#engine-disposal
else:
    print('No download links available from the web page.')
