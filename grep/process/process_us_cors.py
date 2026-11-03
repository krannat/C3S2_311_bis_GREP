import logging
import requests
import config
from bs4 import BeautifulSoup
import os
import subprocess
import time

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def list_fd_uscors(url, ext):
    """
    Function to get the list of links (href) from an HTML directory page that end with the given extension.
    :param url: The URL of the directory page.
    :param ext: The ending to filter the links by.
    :return: List of matching link names, or None on request failure.
    """
    # logfiles for both operational and decommissioned can be downloaded from
    # https://geodesy.noaa.gov/corsdata/station_log/ by 4char site name like ssss.log.txt where ssss is lowercase
    try:
        # url = 'https://geodesy.noaa.gov/corsdata/station_log/'
        page = requests.get(url, timeout=60).text
        soup = BeautifulSoup(page, 'html.parser')
        return [node.get('href') for node in soup.find_all('a') if node.get('href').endswith(ext)]
    except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
            requests.exceptions.ConnectionError) as ex:
        print(' %s - from from list_fd_us_cors(url, ext)' % ex)


def remove_f_duplicates(sum_list):
    """
    Function to remove site duplicates from a list of RINEX file names, keeping the first file per 4-char site name.
    Logs the duplicated sites.
    :param sum_list: List of RINEX file names.
    :return: Sorted list of file names with one file per site.
    """

    stn_dup_list = []  # loop over dict and find stations with more than one file available
    site_dict = {}  # create dictionary for all sites, it will include only ONE RINEX per station
    for file in sum_list:
        site_acr = file[:4].lower()
        # in case of duplicates we do not know the resolution (RINEX has short name), just take the first one
        if site_acr not in site_dict:
            site_dict[site_acr] = file
        else:
            stn_dup_list.append(site_acr)

    if stn_dup_list:
        res_log.info(f' Duplicates were found for the following sites ({len(stn_dup_list)} in total): \n{stn_dup_list}')

    file_list = list(site_dict.values())

    return sorted(file_list)


def get_rinex_list_aws(year, doy):
    """
    Function to get the daily US CORS RINEX list from the NOAA AWS S3 bucket (via the 'aws s3 ls' command) by listing
    site directories and generating 'ssssDDD0.YYd.gz' names. Retries up to 5 times.
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: Sorted (case-insensitive) list of RINEX file names without site duplicates, or None on failure.
    """
    cmd = [
        'aws', 's3', '--region=eu-north-1', '--no-sign-request', 'ls',
        f's3://noaa-cors-pds/rinex/{year}/{str(doy).zfill(3)}/'
    ]

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            output = subprocess.check_output(cmd)
            output = output.decode('utf-8')  # convert bytes to string
            dirs = [d.split('/')[0] for d in output.split('\n') if 'PRE' in d]  # get directory names
            dirs = [dir.lstrip(' PRE') for dir in dirs]

            rinex_list = []
            for i in range(len(dirs)):
                rinex_list.append(dirs[i] + str(doy).zfill(3) + '0.' + str(year)[2:] + 'd.gz')

            if rinex_list:
                rinex_list = remove_f_duplicates(rinex_list)

            return sorted(rinex_list, key=str.casefold)

        except subprocess.CalledProcessError:
            if attempt < max_attempts - 1:  # if it's not the final attempt
                err_log.warning(' Failed to get RINEX list for us_cors. Retrying in 10 seconds...')
                time.sleep(10)  # wait for 10 seconds before retrying
            else:  # if it's the final attempt
                err_log.warning(' Failed to get RINEX list for us_cors after 5 attempts. Aborting...')
                return None
