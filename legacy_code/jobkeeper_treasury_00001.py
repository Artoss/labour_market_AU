# -*- coding: utf-8 -*-
"""
Created on Fri Aug  7 17:04:43 2020

Australian Treasury COVID19 JobKeeper data
https://treasury.gov.au/coronavirus/jobkeeper/data

https://stackoverflow.com/questions/16694907/download-large-file-in-python-with-requests

@author: artos
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import json


url_base = 'https://treasury.gov.au'
url = 'https://treasury.gov.au/coronavirus/jobkeeper/data'


def download_file(url_file):
    filename = url_file.split('/')[-1]
    with requests.get(url_file, stream=True) as r:
        r.raise_for_status()
        with open('Output/' + filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                # If you have chunk encoded response uncomment if
                # and set chunk_size parameter to None.
                #if chunk:
                f.write(chunk)
        return filename


response = requests.get(url)
soup = BeautifulSoup(response.content, 'lxml')

factsheets = soup.find('p', attrs={'class': 'factsheets_link'})
if factsheets is not None:
    url_link = factsheets.find('a')['href']

datestamps = dict()
datestamps['date_string'] = factsheets.find('font').text
datestamps['last_updated_date'] = url_link.split('-')[-1].split('.')[0]

url_file = url_base + url_link
# download_file(url_file)


with open('Output/jobkeeper.json', 'w') as f:
    json.dump(datestamps, f)

with open('Output/jobkeeper.json', 'r') as f:
    date_read = json.load(f)


# # Alternative approach to download file
# import wget
# fname = wget.download(url_file, out = 'Output/')

#%%
# Read downloaded Excel spreadsheet into DataFrame
df_full = pd.read_excel("JobKeeper-data-20200731.xlsx", 
                        sheet_name="Data", 
                        skiprows=1
                        )

df_pc = pd.read_excel("JobKeeper-data-20200731.xlsx", 
                      sheet_name="Data", 
                      skiprows=1, 
                      skipfooter=2
                      )

# Extract the file timestamp from cell "A1" on sheet "Data"
file_created = pd.read_excel("JobKeeper-data-20200731.xlsx", 
                          sheet_name="Data", 
                          nrows=1,
                          header=None,
                          usecols = 'A',
                          names = ['Timestamp']
                          )

data_date_str = file_created.loc[0,'Timestamp'].split(', ')[-1]
# data_date_list = file_created.loc[0,'Timestamp'].split(', ')[-1].split(' ')
# datetime.strftime(year=data_date_list[2], 
#                   month=data_date_list[1], 
#                   day=data_date_list[0])
# print(datetime.strptime('0'+data_date_str, "$d %B %Y"))

file_timestamp = datetime.strptime(data_date_str, '%d %B %Y')




