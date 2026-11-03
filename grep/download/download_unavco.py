import requests
import os
import time
import logging
import inspect
from datetime import datetime
from process import process_unavco
from earthscope_sdk.auth.device_code_flow import DeviceCodeFlowSimple
from earthscope_sdk.auth.auth_flow import NoTokensError
import config
from download import shared_download_requests

err_log = logging.getLogger('error_logger')


def download_rinex_file_unavco(pf_name, remote_path, rinex_down_path):  # sites is one of the chunks
    """
    Function to download a RINEX file from UNAVCO (EarthScope) using an authorization token.
    :param pf_name: The name of the RINEX file to download.
    :param remote_path: The remote URL path of the file.
    :param rinex_down_path: The local directory to download the file to.
    :return: The name of the downloaded (unzipped) file as returned by shared_download_requests.rinex_requests().
    """

    token_path = config.unavco_token_path
    device_flow = DeviceCodeFlowSimple(token_path)
    try:
        # get access token from local path
        device_flow.get_access_token_refresh_if_necessary()
    except NoTokensError:
        device_flow.do_flow()

    token = device_flow.access_token

    # Prepare the request
    headers = {"Authorization": f"Bearer {token}"}
    req = requests.Request('GET', remote_path + pf_name, headers=headers)
    prepared_req = req.prepare()

    curr_func_name = inspect.currentframe().f_code.co_name
    unzipped_file_name = shared_download_requests.rinex_requests(prepared_req, pf_name, rinex_down_path,
                                                                 'UNAVCO', curr_func_name)
    return unzipped_file_name


def get_site_logfile_unavco(site):
    """
    Function to download the site logfile for a given site from UNAVCO (EarthScope) into the logfile archive,
    retrying up to 5 times on request errors.
    :param site: The site name to search for in the remote logfile list.
    :return: A tuple (log_name, download datetime, 'unavco') on success, ('abort', None, None) if the logfile list
    could not be retrieved, or (None, None, None) if no logfile was found or the download failed.
    """

    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)

    token_path = config.unavco_token_path
    # instantiate the device code flow subclass
    device_flow = DeviceCodeFlowSimple(token_path)

    try:
        # get access token from local path
        device_flow.get_access_token_refresh_if_necessary()
    except NoTokensError:
        # if no token was found locally, do the device code flow
        device_flow.do_flow()

    token = device_flow.access_token

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            # get file list
            url = config.unavco_logfiles_url
            f_list = process_unavco.f_list_unavco(url, 'log.txt')  # get logfiles' list
            if f_list == 'unavco logfile list error':
                return 'abort', None, None

            logs_found = [filename for filename in f_list if site.lower() in filename]
            if logs_found:
                # if there are many log files for the same station, just take the first one
                log_name = logs_found[0]
                r = requests.get(url + '/' + log_name, headers={"authorization": f"Bearer {token}"}, timeout=60)

                if r.status_code == 403:  # Access forbidden
                    url_log = url + log_name
                    err_log.error(f' Forbidden access to the site logfile using {url_log}. Skipping this logfile.')
                    return None, None, None

                with open(config.logfile_archive_path + log_name, 'wb') as fd:
                    for chunk in r.iter_content(chunk_size=1000):
                        fd.write(chunk)
                return log_name, datetime.now(), 'unavco'
            else:
                return None, None, None

        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            if attempt < max_attempts - 1:
                err_log.warning(f' Failed in get_site_logfile_unavco({site}). Retrying in 10 seconds...')
                time.sleep(10)
            else:
                err_log.error(' %s - from get_site_logfile_unavco() for %s. Max retries reached. Aborting...'
                              % (ex, site))
                return None, None, None
