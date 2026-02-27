# -*- coding: utf-8 -*-
"""
Created on Sun Oct  6 11:44:49 2024

@author: Artoss
"""

import requests
from bs4 import BeautifulSoup
from dateutil import parser
from datetime import datetime


def test(stuff):
    """
    

    Parameters
    ----------
    stuff : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    """


# Get list of all URLs to check for download links

# Validate URL

# JOBS AND SKILLS - DOWNLOADS

# CSS extractors
css_extractions = [{'release_date': 'div.field:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > p:nth-child(2) > strong:nth-child(1)'},
                   {'reference_date': 'html.js body.layout-no-sidebars.page-node-474.path-node.node--type-govcms-standard-page.darkMode.normalContrastMode.scrolled.scrollup div.dialog-off-canvas-main-canvas div#page-wrapper div#page div#main-wrapper.layout-main-wrapper.clearfix div#main.container-fluid div.row.row-offcanvas.row-offcanvas-left.clearfix main#content.main-content.col section.section div#block-mainpagecontent.block.block-system.block-system-main-block div.content article.node.node--type-govcms-standard-page.node--view-mode-full.clearfix.container div.node__content.clearfix div.mainArticle div.field.field--name-field-paragraphs.field--type-entity-reference-revisions.field--label-hidden.field__items div.field__item div.paragraph.paragraph--type--plain.paragraph--view-mode--default.spaceSTop.spaceSBottom div.wrapper.accent div.content div.paragraph-plain--body div.clearfix.text-formatted.field.field--name-field-html.field--type-text-long.field--label-hidden.field__item h2#junequarter2024.copyLink'}
                   ]

html_tag_extractions = {{'release_date': ['div', 'class', "field--type-text-long"]},
                        {'reference_date': ''}
                        }


salm_url = 'https://www.jobsandskills.gov.au/data/small-area-labour-markets'
resp = requests.get(salm_url)
salm_soup = BeautifulSoup(resp.content, 'lxml')
salm_soup = BeautifulSoup(resp.content, 'html.parser')


# EXTRACT METADATA FROM HTML - reference and release dates
try:
    reference_date = salm_soup.find_all('div', 
                                        attrs={'class': "field--type-text-long"}
                                        )[0].find('h2').text.strip()
except:
    # Alternative code - extract all text from first text-box and then split
    reference_date = salm_soup.find('div', 
                                    attrs={'class': "field--type-text-long"}
                                    ).text.strip().split('\n')[0]

try:
    release_date = salm_soup.find_all('div', 
                                        attrs={'class': "field--type-text-long"}
                                        )[0].find('strong').text.strip()
except:
    # Alternative code - extract all text from first text-box and then split
    release_date = salm_soup.find('div', 
                                  attrs={'class': "field--type-text-long"}
                                  ).text.strip().split('\n')[1]

try:
    full_text = bbb = salm_soup.find('div', 
                                     attrs={'class': 'mainArticle'}
                                     ).text.strip().replace('\n\n\n', '')
except:
    full_text = 'Not avaialble'


# Convert RELEASE DATE STRING and covert to UTC time zone as timestamp
try:
    release_month = parser.parse(release_date[9:]).month
    if (release_month >=4) and (release_month <= 9):
        # Australian Eastern STANDARD Time (AEST) from 
        # first Sunday in April to first Sunday in October
        timestamp = parser.parse(release_date[9:] + ' AEST', 
                                 tzinfos={'AEST': "UTC+10"}
                                 )
    else:
        # Australian Eastern DAYLIGHT Time (AEDT) from 
        # first Sunday in October to first Sunday in April
        timestamp = parser.parse(release_date[9:] + ' AEDT', 
                                 tzinfos={'AEDT': "UTC+11"}
                                 )

except AttributeError as err:
    # Alternative approach using datetime
    timestamp = datetime.strptime(release_date[9:], '%H:%M%p %A, %d %B %Y')
    print(err)
