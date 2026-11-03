import requests
import os
import time
import logging
import inspect
from datetime import datetime
from process import process_cacs
import config
from download import shared_download_requests

err_log = logging.getLogger('error_logger')


def download_rinex_files(pf_name, remote_path, rinex_down_path):  # sites is one of the chunks
    """
    Function to download a RINEX file from CACS (Canada).
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
                                                                 'CACS', curr_func_name)
    return unzipped_file_name


def get_site_logfiles_cacs(site):
    """
    Function to download the site logfile for a given site from CACS (Canada) into the logfile archive,
    retrying up to 5 times on errors. A "403 Forbidden" response skips the download.
    :param site: The site name to search for in the remote logfile list.
    :return: A tuple (log_name, download datetime, 'cacs') on success, ('abort', None, None) if the logfile list
    is empty, or (None, None, None) if no logfile was found or the download failed.
    """
    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)

    url = config.cacsa_logfiles_remote_url
    max_attempts = 5

    for attempt in range(max_attempts):
        try:
            f_list = process_cacs.list_fd(url, '.log')
            if not f_list:
                return 'abort', None, None

            logs_found = [filename for filename in f_list if site.lower() in filename]
            if not logs_found:  # If no log files for the specific site found, abort.
                return None, None, None

            log_name = logs_found[0]
            r = requests.get(url + log_name, timeout=120)
            r.raise_for_status()

            with open(config.logfile_archive_path + log_name, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=1000):
                    fd.write(chunk)
            return log_name, datetime.now(), 'cacs'

        except requests.exceptions.HTTPError as http_err:
            if http_err.response.status_code == 403:  # Access forbidden
                err_log.error(f' Forbidden access to the site logfile using {url}. Skipping this logfile.')
                return None, None, None
            if attempt < max_attempts - 1:
                err_log.warning(f' HTTP error occurred: {http_err}. Retrying in 10 seconds...')
                time.sleep(10)
            else:
                err_log.error(f' HTTP error occurred: {http_err}. Max retries reached. Aborting...')
                return None, None, None
        except (requests.exceptions.Timeout, requests.exceptions.RequestException,
                requests.exceptions.SSLError, requests.exceptions.ConnectionError) as ex:
            if attempt < max_attempts - 1:  # if it's not the final attempt
                err_log.warning(f' Exception in get_site_logfiles_cacs() for {site}: {ex}. Retrying in 10 seconds.')
                time.sleep(10)
            else:
                err_log.error(f' Exception in get_site_logfiles_cacs() for {site}: {ex}. Max retries reached. '
                              f'Aborting...')
                return None, None, None
        except Exception as ex:
            if attempt < max_attempts - 1:  # if it's not the final attempt
                err_log.warning(f' Unknown exception in get_site_logfiles_cacs(): {ex}. Retrying in 10 seconds.')
                time.sleep(10)
            else:
                err_log.error(f' Unknown exception in get_site_logfiles_cacs(): {ex}. Max retries reached. Aborting...')
                return None, None, None