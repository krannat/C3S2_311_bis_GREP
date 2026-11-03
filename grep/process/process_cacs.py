import time
import logging
import requests
import urllib3
import config

from bs4 import BeautifulSoup

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def list_fd(url, ext):
    """
    Function to get the list of links (href) from an HTML directory page that end with the given extension.
    Retries up to 5 times.
    :param url: The URL of the directory page.
    :param ext: The ending to filter the links by.
    :return: List of matching link names, or None if all attempts failed.
    """
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            page = requests.get(url, timeout=60).text
            soup = BeautifulSoup(page, 'html.parser')
            return [node.get('href') for node in soup.find_all('a') if node.get('href').endswith(ext)]
        except (urllib3.exceptions.MaxRetryError, requests.exceptions.Timeout, requests.exceptions.RequestException,
                requests.exceptions.SSLError, requests.exceptions.ConnectionError) as ex:
            if attempt < max_attempts - 1:  # if it's not the final attempt
                err_log.warning(' %s - from cacs list_fd(). Retrying in 30 seconds...' % ex)
                time.sleep(30)  # wait for 30 seconds before retrying
                continue
            else:  # if it's the final attempt
                err_log.error(' %s - from cacs list_fd(). No more retries left. Aborting...' % ex)
                return None  # after max_attempts, the function gives up and returns None


def get_rinex_list_cacsa(year, doy):
    """
    Function to get the daily CACS (Canada) RINEX list, removing site duplicates (preferring '.Z' over '.gz' files).
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: Sorted list of RINEX file names without site duplicates, or None on failure.
    """
    try:
        # get file list
        url = config.cacs_rinex_url + str(year)[2:] + str(doy).zfill(3) + '/' + str(year)[2:] + 'd/'
        f_list_z = list_fd(url, '.Z')
        f_list_gz = list_fd(url, '.gz')

        if f_list_z is None or f_list_gz is None:
            return None

        sum_list = f_list_z + f_list_gz

        # Each directory in CACS has mixed *.gz and *.Z with different versions of Compact RINEX and with
        #  different naming conventions. Get both and check for site duplicates. Prefer *.Z data.
        site_dict = {}  # create dictionary for all sites, including duplicates for each site (if present)
        for file in sum_list:
            site_acr = file[:4].lower()
            if site_acr not in site_dict:
                site_dict[site_acr] = {}
            site_dict[site_acr][file.rsplit('.', 1)[-1]] = file

        stn_dup_list = []  # loop over dict and find stations with more than one file available
        for stn, stn_files in site_dict.items():
            if len(stn_files) == 2:  # both .gz and .Z available
                stn_dup_list.append(stn)
            elif len(stn_files) == 3:
                print('More than two duplicates were found for %s. Modify scripts to deal with this!' % stn)
        if len(stn_dup_list) > 0:
            res_log.info(' Duplicates were found for the following sites (%s in total): \n%s' %
                         (len(stn_dup_list), stn_dup_list))

        # create new list from dict that does NOT contain duplicates
        rinex_list_without_dup = []
        for stn, stn_files in site_dict.items():
            try:  # if .Z file present
                rinex_list_without_dup.append(stn_files['Z'])
            except KeyError:  # then .gz must be present
                rinex_list_without_dup.append(stn_files['gz'])
        # print(rinex_list_without_dup)
        return sorted(rinex_list_without_dup)

    except Exception as ex:
        err_log.error(' Could not handle the exception from get_rinex_list_cacsa: %s' % ex)
