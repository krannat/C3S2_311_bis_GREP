import datetime
import os
import requests
import time
import logging
import shutil
import inspect
from download import shared_download_requests
import config
from bs4 import BeautifulSoup

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def get_site_logfile_us_cors(s_name):
    """
    Function to download the site logfile for a given site from US CORS into the logfile archive,
    retrying up to 5 times on request errors.
    :param s_name: The 4-character site name; matched against the first 4 characters of the remote logfile names.
    :return: A tuple (log_name, download datetime, 'us_cors') on success, ('abort', None, None) if the logfile list
    is invalid, or (None, None, None) if the list is empty or the download failed.
    """

    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)

    os.chdir(config.logfile_archive_path)

    retry_attempts = 5

    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)
    cwd = os.getcwd()
    os.chdir(config.logfile_archive_path)

    while retry_attempts > 0:
        try:
            # =========
            url = config.uscors_logfiles_url
            f_list = list_fd_uscors(url, '.txt')  # US_CORS logfiles *.log.txt
            if f_list == 'US_CORS logfile list error':
                return 'abort', None, None
            if f_list:
                # =========
                logs_found = [filename for filename in f_list if s_name.lower() in filename[:4].lower()]
                if logs_found:
                    # if there are many log files for the same station, just take the first one
                    log_name = logs_found[0]
                    r = requests.get(url + log_name, timeout=120)

                    with open(config.logfile_archive_path + log_name, 'wb') as fd:
                        for chunk in r.iter_content(chunk_size=1000):
                            fd.write(chunk)
                    os.chdir(cwd)  # job done, back to cwd
                    return log_name, datetime.datetime.now(), 'us_cors'
            else:
                return None, None, None

        except (requests.exceptions.Timeout, requests.exceptions.RequestException,
                requests.exceptions.SSLError, requests.exceptions.ConnectionError) as ex:
            retry_attempts -= 1

            if retry_attempts > 0:
                time.sleep(10)  # wait for 10 seconds before next attempt
                err_log.warning(f' {ex} - from get_site_logfile_us_cors(). Failed attempt. Retrying in 10 seconds. '
                                f'Current site to process {s_name}')
                continue
            else:
                err_log.error(
                    f' {ex} - from get_site_logfile_us_cors(). All attempts failed. Current site to process {s_name}')
                print(f' {ex} - from from get_site_logfile_us_cors(). All attempts failed. '
                      f'Current site to process {s_name}')
                return None, None, None

        except Exception as ex:
            raise ex


def download_rinex_files_us_cors(pf_name, remote_path, rinex_down_path):
    """
    Function to download one RINEX file from US CORS.
    :param pf_name: The name of the RINEX file to download.
    :param remote_path: The remote URL path (the site subdirectory pf_name[:4] is appended).
    :param rinex_down_path: The local directory to download the file to.
    :return: The name of the downloaded (unzipped) file as returned by shared_download_requests.rinex_requests().
    """
    # Prepare the request
    file_url = remote_path + pf_name[:4] + '/' + pf_name
    req = requests.Request('GET', file_url)
    prepared_req = req.prepare()

    curr_func_name = inspect.currentframe().f_code.co_name
    unzipped_file_name = shared_download_requests.rinex_requests(prepared_req, pf_name, rinex_down_path,
                                                                 'US_CORS', curr_func_name)
    return unzipped_file_name


def list_fd_uscors(url, ext):
    """
    Function to get the list of US CORS logfile names with the given extension from the links of a web page
    and to validate the first file name.
    :param url: The URL of the US CORS logfile directory page.
    :param ext: The file extension to filter by (e.g. '.txt').
    :return: The list of logfile names, the string 'US_CORS logfile list error' if the list is empty or invalid,
    or None on request errors.
    """
    # logfiles for both operational and decommissioned can be downloaded from
    # https://geodesy.noaa.gov/corsdata/station_log/ by 4char site name like ssss.log.txt where ssss is lowercase
    try:
        # url = 'https://geodesy.noaa.gov/corsdata/station_log/'
        page = requests.get(url, timeout=120).text
        soup = BeautifulSoup(page, 'html.parser')
        log_list = [node.get('href') for node in soup.find_all('a') if node.get('href').endswith(ext)]
        if not log_list:
            err_log.error(f' US_CORS logfile list completely empty. See list_fd_uscors(). Exiting...')
            return 'US_CORS logfile list error'
        fname_end = log_list[0][-4:]
        fname_len = len(log_list[0])
        if fname_end == '.txt':
            if fname_len < 27:
                return log_list
        else:
            err_log.error(f' The first element in US_CORS logfile list does not end with ".txt." or the '
                          f'length of the text string > 26. See list_fd_uscors(). Exiting...')
            return 'US_CORS logfile list error'
    except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
            requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as ex:
        print(' %s - from list_fd_uscors(url, ext)' % ex)
        return None


def get_site_logfile_us_cors_aws(s_name):
    """
    Function to download the site logfile for a given site from the US CORS Amazon AWS bucket, retrying up to 5 times,
    check that it exists and move it into the logfile archive.
    :param s_name: The 4-character site name.
    :return: A tuple (log_name, download datetime, 'us_cors') on success, ('abort', None, None) if the logfile
    cannot be decoded, or (None, None, None) if the logfile does not exist or the download failed.
    """

    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)

    cwd = os.getcwd()
    os.chdir(config.BASE_PATH + 'tmp')

    log_name = s_name.lower() + '.log.txt'
    url = config.us_cors_logfiles_url_amazon + log_name

    retry_attempts = 5
    for attempt in range(retry_attempts):
        try:
            response = requests.get(url, timeout=120, stream=True)  # timeout values in seconds.
            response.raise_for_status()  # If response was successful, no Exception will be raised.
            break
        except requests.HTTPError as http_err:
            if http_err.response.status_code == 403:  # Access forbidden
                err_log.warning(f" Forbidden access to us_cors url: {url}. Skipping this logfile.")
                os.chdir(cwd)
                return None, None, None
            err_log.warning(f' HTTP error occurred: {http_err}')
        except requests.Timeout as timeout_err:
            err_log.warning(f' Timeout error occurred: {timeout_err}')
        except requests.ConnectionError as conn_err:
            err_log.warning(f' Connection error occurred: {conn_err}')
        except requests.RequestException as req_err:
            err_log.warning(f' Other request error occurred: {req_err}')
        except Exception as ex:
            err_log.warning(f' Unknown error occurred: {ex}')
        time.sleep(10)
    else:
        err_log.error(f' Could not download the us_cors file from {url} after {retry_attempts} attempts')
        os.chdir(cwd)
        return None, None, None

    with open(log_name, 'wb') as file:
        for chunk in response.iter_content(chunk_size=1024):
            file.write(chunk)

    try:
        with open(log_name, 'r', encoding='utf-8') as f_in:  # trying with utf-8
            r_lines = f_in.readlines()
        if 'key does not exist' in r_lines[1]:
            err_log.warning(' Logfile does not exist for us_cors site ' + str(s_name))
            os.remove(log_name)
            os.chdir(cwd)
            return None, None, None
    except UnicodeDecodeError:
        try:
            with open(log_name, 'r', encoding='ISO-8859-1') as f_in:  # trying with latin1
                r_lines = f_in.readlines()
            if 'key does not exist' in r_lines[1]:
                err_log.warning(' Logfile does not exist for us_cors site ' + str(s_name))
                os.remove(log_name)
                os.chdir(cwd)
                return None, None, None
        except UnicodeDecodeError as e:  # neither utf-8 and latin1 did work
            os.remove(log_name)
            err_log.error(f" Cannot read us_cors logfile {log_name} downloaded from {url}: {e}")
            os.chdir(cwd)
            return 'abort', None, None

    shutil.move(log_name, config.logfile_archive_path + log_name)
    os.chdir(cwd)
    return log_name, datetime.datetime.now(), 'us_cors'
