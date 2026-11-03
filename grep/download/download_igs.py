import requests
import logging
import time
import os
import datetime
import inspect
import config
from dbio import shared_funcs
from download import shared_download_requests


res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def get_logfile_list(url):
    """
    Function to get the sorted list of IGS 9-character logfile names (*.log) from a URL, retrying up to 5 times,
    and to validate the first file name.
    :param url: The URL of the IGS logfile directory ("*?list" is appended if missing).
    :return: The sorted list of logfile names, the string 'logfile list error' if validation fails,
    or ('abort', None, None) if the request failed or the list is empty.
    """

    if not url.endswith("*?list"):
        url = url + "*?list"
    file_list = []
    allowed_log_end_strs = ['.log']
    max_attempts = 5

    for attempt in range(max_attempts):
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            res = response.text
            break
        except requests.exceptions.RequestException as ex:
            if attempt < max_attempts - 1:  # If not last attempt yet
                err_log.warning(f' Failed in IGS get_logfile_list(). Retrying in 10 seconds...')
                time.sleep(10)
            else:  # This was the last attempt
                err_log.error(' %s - from IGS get_logfile_list(). Max retries reached. Aborting...' % ex)
                return 'abort', None, None  # Aborting if unable to create a connection
        except Exception as ex:
            if attempt < max_attempts - 1:  # If not last attempt yet
                err_log.warning(f' Unknown exception in IGS get_logfile_list(): %s. Retrying in 10 seconds...' % ex)
                time.sleep(10)
            else:  # This was the last attempt
                err_log.warning(f' Unknown exception in IGS get_logfile_list(): %s. Max retries reached. Aborting...'
                                % ex)
                return 'abort', None, None  # Aborting if unable to create a connection

    f_list = res.split()
    if not f_list:
        err_log.warning(f'Exception in IGS get_logfile_list(). File list empty from URL {url}. Aborting ...')
        return 'abort', None, None

    for i in range(len(f_list)):
        if any(end_str in f_list[i] for end_str in allowed_log_end_strs):
            file_list.append(f_list[i])
    file_list = sorted(file_list)
    err_msg = shared_funcs.check_first_logfile_name(file_list[0], allowed_log_end_strs, 22, 'IGS')
    if not err_msg:
        return file_list
    else:
        return err_msg


def download_rinex_files(pf_name, remote_path, rinex_down_path):
    """
    Function to download a RINEX file from IGS.
    :param pf_name: The name of the RINEX file to download.
    :param remote_path: The remote URL path of the file.
    :param rinex_down_path: The local directory to download the file to.
    :return: The name of the downloaded (unzipped) file as returned by shared_download_requests.rinex_requests_igs().
    """

    # Prepare the request
    req = requests.Request('GET', remote_path + pf_name)
    prepared_req = req.prepare()

    curr_func_name = inspect.currentframe().f_code.co_name
    unzipped_file_name = shared_download_requests.rinex_requests_igs(prepared_req, pf_name, rinex_down_path,
                                                                 'IGS', curr_func_name)
    return unzipped_file_name


def write_log_file(url, file_path, max_attempts=5):
    """
    Function to download a logfile from a URL and write it to a local file, retrying on errors.
    :param url: The URL of the logfile.
    :param file_path: The local path to write the logfile to.
    :param max_attempts: The maximum number of download attempts.
    :return: True if the file was downloaded and written, False otherwise.
    """
    for attempt in range(max_attempts):
        try:
            r = requests.get(url, timeout=120, stream=True)
            with open(file_path, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=1000):
                    fd.write(chunk)
            return True  # the file was successfuly downloaded and written
        except (requests.exceptions.HTTPError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException,
                requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            # Handle exceptions caused by the requests library
            if attempt < max_attempts - 1:  # Not the final attempt
                err_log.warning(f' Failed to download logfile from {url}. Retrying in 10 seconds...')
                time.sleep(10)
            else:
                err_log.error(f' Failed to download logfile from {url}. Max retries reached. Aborting...')
                return False
        except Exception as ex:
            # Handle unexpected exceptions
            if attempt < max_attempts - 1:
                err_log.warning(f' An unexpected error occurred when attempting to download logfile from {url}: {ex}. '
                                f'Retrying in 10 seconds...')
                time.sleep(10)
            else:
                err_log.error(
                    f' Unable to download logfile from {url} after max_attempts attempts due to unexpected error: {ex}.'
                    f' Aborting...')
                return False


def get_site_logfiles_igs(site):
    """
    Function to download the site logfile for a given site from IGS (active sites first, then decommissioned sites)
    into the logfile archive. Some sites (PAMA, WETT, HOB1, MASP, OATT) are skipped.
    :param site: The site name; matched against the first 4 characters of the remote logfile names.
    :return: A tuple (log_name, download datetime, 'igs') on success, ('abort', None, None) if a logfile list
    could not be retrieved, or (None, None, None) if no logfile was found or the download failed.
    """

    if (site.upper() == 'PAMA') or (site.upper() == 'WETT') or (site.upper() == 'HOB1') or (site.upper() == 'MASP') or (site.upper() == 'OATT'):
        return None, None, None

    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)

    # get file list
    url = config.igs_log_url
    url_hist = config.igs_log_url_decommissioned

    f_list_9char = get_logfile_list(url)
    f_list_hist = get_logfile_list(url_hist)

    if f_list_9char == 'logfile list error' or f_list_hist == 'logfile list error':
        return 'abort', None, None

    logs_found = [filename for filename in f_list_9char if site.lower() in filename[:4].lower()]

    if logs_found:
        # If there are many log files for the same station, just take the first one
        success = write_log_file(url + logs_found[0], os.path.join(config.logfile_archive_path, logs_found[0]))
        if success:
            return logs_found[0], datetime.datetime.now(), 'igs'

    # Check if log in historical sites
    logs_found = [filename for filename in f_list_hist if site.lower() in filename[:4].lower()]
    if logs_found:
        # If there are many log files for the same station, just take the first one
        success = write_log_file(url_hist + logs_found[0], os.path.join(config.logfile_archive_path, logs_found[0]))
        if success:
            return logs_found[0], datetime.datetime.now(), 'igs'

    err_log.warning(f' Site log not found neither in active nor in the historical IGS sites for {site}')
    return None, None, None
