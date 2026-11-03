import logging
import time

import requests
from bs4 import BeautifulSoup

import config

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def get_rinex_list_epn(year, doy):
    """
    Function to get the daily EPN RINEX list from the EPN archive, removing site duplicates (preferring '.Z' over
    '.gz' files).
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: Sorted list of RINEX file names without site duplicates, or None if no files were found.
    """
    url = config.epn_rinex_url + str(year) + '/' + str(doy).zfill(3) + '/'
    max_attempts = 5  # maximum number of attempts if process unsuccessful
    f_list_z, f_list_gz = [], []

    # Attempt to retrieve page
    for attempt in range(max_attempts):
        try:
            page = requests.get(url, timeout=120).text
            soup = BeautifulSoup(page, 'html.parser')
            # for '.Z'
            f_list_z = [node.get('href') for node in soup.find_all('a') if node.get('href').endswith('.Z')]
            # for '.gz'
            f_list_gz = [node.get('href') for node in soup.find_all('a') if node.get('href').endswith('.gz')]
            break  # if retrieval is successful, break out of the loop
        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            err_log.error(' %s - from get_rinex_list_epn(%s, %s)' % (ex, str(year), str(doy)))
            time.sleep(60)  # wait for 60 seconds before retrying

    sum_list = f_list_z + f_list_gz
    if not sum_list:
        return None

    site_dict = {}
    for file in sum_list:
        site_acr = file[:4].lower()
        if site_acr not in site_dict:
            site_dict[site_acr] = {}
        site_dict[site_acr][file.rsplit('.', 1)[-1]] = file

    stn_dup_list = []
    for stn, stn_files in site_dict.items():
        if len(stn_files) == 2:  # both .gz and .Z available
            stn_dup_list.append(stn)
        elif len(stn_files) == 3:
            err_log.error(' More than two duplicates were found for %s. Modify scripts to deal with this!' % stn)
    if stn_dup_list:
        res_log.info(
            ' Duplicates were found for the following sites (%s in total): \n%s' % (len(stn_dup_list), stn_dup_list))

    rinex_list_without_dup = []
    for stn, stn_files in site_dict.items():
        file_to_append = stn_files.get('Z') or stn_files.get('gz')
        if file_to_append is not None:
            rinex_list_without_dup.append(file_to_append)

    return sorted(rinex_list_without_dup)
