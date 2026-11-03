import time
import logging
import requests
import urllib3

from bs4 import BeautifulSoup
import config

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def list_fd(url, ext):
    """
    Function to get the list of links (href) from an HTML directory page that end with the given extension.
    Retries up to 5 times and falls back to disabled SSL verification on SSL errors.
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
        except requests.exceptions.SSLError as ex:
            err_log.warning(' %s - from brazil_ibge list_fd(). SSL verification failed. '
                            'Retrying with certificate verification disabled...' % ex)
            try:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                page = requests.get(url, timeout=60, verify=False).text
                soup = BeautifulSoup(page, 'html.parser')
                return [node.get('href') for node in soup.find_all('a') if node.get('href').endswith(ext)]
            except requests.exceptions.RequestException as ex:
                if attempt < max_attempts - 1:  # if it's not the final attempt
                    err_log.error(' %s - from brazil_ibge list_fd(). Retrying in 30 seconds...' % ex)
                    time.sleep(30)  # wait for 30 seconds before retrying
                    continue
                else:  # if it's the final attempt
                    err_log.error(' %s - from brazil_ibge list_fd(). No more retries left. Aborting...' % ex)
                    return None  # after max_attempts, the function gives up and returns None
        except (urllib3.exceptions.MaxRetryError, requests.exceptions.Timeout, requests.exceptions.RequestException,
                requests.exceptions.ConnectionError) as ex:
            if attempt < max_attempts - 1:  # if it's not the final attempt
                err_log.error(' %s - from brazil_ibge list_fd(). Retrying in 30 seconds...' % ex)
                time.sleep(30)  # wait for 30 seconds before retrying
                continue
            else:  # if it's the final attempt
                err_log.error(' %s - from brazil_ibge list_fd(). No more retries left. Aborting...' % ex)
                return None  # after max_attempts, the function gives up and returns None


def get_rinex_list_brazil_ibge(year, doy):
    """
    Function to get the daily IBGE RINEX lists: RINEX3 '.gz' files (since 2018 DOY 242) and RINEX2 '.zip' files.
    :param year: The year of the RINEX files (int).
    :param doy: The day of year of the RINEX files (int).
    :return: Tuple (gz_list, zip_list) of sorted RINEX file names, (None, None) if a listing failed, or None on exception.
    """
    f_list_gz, f_list_zip = [], []
    try:
        # At first, get the sites with RINEX3 already available. These sites should be later downloaded from
        #  /dados_RINEX3/ Then, the second step - check the rest of the sites in /dados
        if year >= 2019 or (year == 2018 and doy >= 242):
            url = config.brazil_ibge_rinex3_url + str(year) + '/' + str(doy).zfill(3) + '/'
            f_list_gz = list_fd(url, '.gz')

        # after RINEX3 sites found, check for any *.zip
        url = config.brazil_ibge_rinex_url + str(year) + '/' + str(doy).zfill(3) + '/'
        f_list_zip = list_fd(url, '.zip')
        if f_list_gz is None or f_list_zip is None:
            return None, None
        return sorted(f_list_gz), sorted(f_list_zip)

    except Exception as ex:
        err_log.error(' Could not handle the exception from get_rinex_list_brazil_ibge: %s' % ex)


def get_brazil_ibge_site_name_list(year, doy):
    """
    Function to get the unique 4-char site names (lowercase) from the IBGE RINEX3 '.gz' and RINEX2 '.zip' lists.
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: Sorted list of unique site names, or None if a listing failed.
    """
    l_gz, l_zip = get_rinex_list_brazil_ibge(year, doy)
    if l_gz is None or l_zip is None:
        return None
    s_gz, s_zip, s_sum = [], [], []
    for i in range(len(l_gz)):
        s_gz.append(l_gz[i][:4].lower())
    for i in range(len(l_zip)):
        s_zip.append(l_zip[i][:4].lower())
    s_sum = s_gz
    for i in range(len(s_zip)):
        if s_zip[i][:4].lower() not in s_gz:
            s_sum.append(s_zip[i][:4].lower())
    return sorted(s_sum)


def merge_gz_zip_lists(f_gz, f_zip, s_list):
    """
    Function to merge the RINEX '.gz' and '.zip' lists into one list: '.gz' files of sites in s_list are taken first,
    and '.zip' files are added only for sites without a '.gz' file.
    :param f_gz: List of RINEX '.gz' files.
    :param f_zip: List of RINEX '.zip' files.
    :param s_list: List of 4-char site names (lowercase).
    :return: Case-insensitively sorted merged list of RINEX file names.
    """
    obs_rinex = []
    tmp_sites_gz = []
    for i in range(len(f_gz)):
        if f_gz[i][:4].lower() in s_list:
            obs_rinex.append(f_gz[i])
            tmp_sites_gz.append(f_gz[i][:4].lower())
    for i in range(len(f_zip)):
        if f_zip[i][:4].lower() not in tmp_sites_gz:
            obs_rinex.append(f_zip[i])
    obs_rinex = sorted(obs_rinex, key=lambda x: str.casefold(x) if isinstance(x, str) else x)
    return obs_rinex
