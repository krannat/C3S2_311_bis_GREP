import requests
import logging
import time
import os
import datetime
import inspect
from bs4 import BeautifulSoup
import config
from dbio import shared_funcs
from download import shared_download_requests

# https://epncb.oma.be/_networkdata/data_access/dailyandhourly/index.php
# Daily data
#
# All EPN stations upload daily (24 hour) RINEX files to two EPN data centres (the primary and secondary data centre)
# from where they flow to the two EPN Regional data centres following a well-defined data flow scheme indicated in the
# Guidelines for EPN Stations and Operational Centres. In order to minimize file size, the RINEX data are Hatanaka
# compressed before being uploaded. One week after the observation date, all daily RINEX data are copied to the EPN
# data archive at ROB (EPN CB). This archive also contains the historical data of the EPN stations from the period
# before they were integrated in the EPN.

# ROB (Royal Observatory of Belgium), is maintaining the EPN historical data centre. This archive contains only daily
# RINEX data and the RINEX header has been changed to be in accordance with the site logs. The archive contains more
# historical data from the EPN stations (often for periods before the station was included in the EPN) than the Regional
# Data Centres, but it does not have the last 3-months of data available. Each month, ROB updates the archive with one
# additional month of recent EPN data.
#
# daily data archive: https://epncb.oma.be/pub/obs/
# example: https://epncb.oma.be/pub/obs/1996/001/ANKR0010.96D.Z

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def download_rinex_files_epn(pf_name, remote_path, rinex_down_path):
    """
    Function to download a RINEX file from EPN.
    :param pf_name: The name of the RINEX file to download.
    :param remote_path: The remote URL path of the file.
    :param rinex_down_path: The local directory to download the file to.
    :return: The name of the downloaded (unzipped) file as returned by shared_download_requests.rinex_requests().
    """

    # Prepare the request
    req = requests.Request('GET', remote_path + pf_name)
    prepared_req = req.prepare()

    curr_func_name = inspect.currentframe().f_code.co_name
    unzipped_file_name = shared_download_requests.rinex_requests(prepared_req, pf_name, rinex_down_path,
                                                                 'EPN', curr_func_name)
    return unzipped_file_name


def get_site_logfile_epn(site):
    """
    Function to download the site logfile for a given site from EPN into the logfile archive, retrying up to 5 times.
    Example URL: https://epncb.oma.be/ftp/station/log_9char/acor00esp_20230724.log
    :param site: The site name; matched against the first 4 characters of the remote logfile names.
    :return: A tuple (log_name, download datetime, 'epn') on success, ('abort', None, None) if the logfile list
    could not be retrieved, or (None, None, None) if no logfile was found or the download failed.
    """
    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)

    url = config.epn_logfiles_url
    f_list_9char = get_logfile_list_epn(url, '.log')

    if f_list_9char == 'logfile list error':
        return 'abort', None, None

    max_retries = 5  # maximum number of attempts if process unsuccessful

    if f_list_9char:
        logs_found = [filename for filename in f_list_9char if site.lower() in filename[:4].lower()]
        if logs_found:
            log_name = logs_found[0]  # if there are many log files for the same station, just take the first one

            for attempt in range(max_retries):
                try:
                    r = requests.get(url + log_name, timeout=120)
                    with open(config.logfile_archive_path + log_name, 'wb') as fd:
                        for chunk in r.iter_content(chunk_size=1000):
                            fd.write(chunk)
                    return log_name, datetime.datetime.now(), 'epn'
                except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                        requests.exceptions.ConnectionError) as ex:
                    if attempt < max_retries - 1:  # if it's not the final attempt
                        err_log.warning(' %s - from get_site_logfile_epn() for site %s. Retrying in 10 seconds.'
                                        % (ex, site))
                        time.sleep(10)
                    else:
                        err_log.error(' %s - from get_site_logfile_epn() for site %s. Max retries reached. Aborting...'
                                      % (ex, site))
                except Exception as ex:
                    err_log.error(' Unknown exception in get_site_logfile_epn(): %s' % ex)
            return None, None, None  # return None if max retries are reached
        else:
            return None, None, None  # site log not found
    else:
        return None, None, None  # log file list is empty


def get_logfile_list_epn(url, ext):
    """
    Function to get the list of logfile names with the given extension from the links of an EPN web page,
    retrying up to 5 times, and to validate the first file name.
    :param url: The URL of the EPN logfile directory page.
    :param ext: The file extension to filter by (e.g. '.log').
    :return: The list of logfile names, or the string 'logfile list error' on failure or failed validation.
    """
    allowed_log_end_strs = [ext]
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            page = response.text
            soup = BeautifulSoup(page, 'html.parser')
            log_list = [node.get('href') for node in soup.find_all('a') if node.get('href').endswith(ext)]
            if not log_list:
                err_log.error(f' EPN logfile list completely empty. See get_logfile_list_epn(). Exiting...')
                return 'logfile list error'
            break

        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            if attempt < max_retries - 1:
                err_log.warning(' %s - from get_logfile_list_epn() for url %s. Retrying in 10 seconds.' % (ex, url))
                time.sleep(10)
            else:
                err_log.error(' %s - from get_logfile_list_epn() for url %s. Max retries reached. Aborting...'
                              % (ex, url))
                return 'logfile list error'
        except Exception as ex:
            if attempt < max_retries - 1:
                err_log.warning(' Unknown exception in get_logfile_list_epn(): %s. Retrying in 10 seconds.' % ex)
                time.sleep(10)
            else:
                err_log.error(' Unknown exception in get_logfile_list_epn(): %s. Max retries reached. Aborting...' % ex)
                return 'logfile list error'

    err_msg = shared_funcs.check_first_logfile_name(log_list[0], allowed_log_end_strs, 22, 'EPN')
    if not err_msg:
        return log_list
    else:
        return err_msg
