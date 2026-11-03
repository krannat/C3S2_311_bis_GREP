import time
import logging
import requests

from earthscope_sdk.auth.device_code_flow import DeviceCodeFlowSimple, RequestDeviceTokensError, PollingError
from earthscope_sdk.auth.auth_flow import NoTokensError, InvalidRefreshTokenError, NoRefreshTokenError

import config

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


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


def f_list_unavco(url, ext):
    """
    Function to get the list of files from a UNAVCO/EarthScope URL filtered by extension, using an EarthScope SDK
    access token. Site duplicates are removed for RINEX lists. Retries up to 5 times.
    :param url: The remote directory URL.
    :param ext: The file name ending to filter by (e.g. 'd.Z', 'o.Z' or 'log.txt').
    :return: Sorted list of file names; on failure None for 'd.Z' or the string 'unavco logfile list error' otherwise.
    """

    # choose where you want the token saved - the default file name is sso_tokens.json
    token_path = config.unavco_token_path

    # instantiate the device code flow subclass
    device_flow = DeviceCodeFlowSimple(token_path)
    try:
        # get access token from local path
        device_flow.get_access_token_refresh_if_necessary()
    except NoTokensError:
        # if no token was found locally, do the device code flow
        try:
            device_flow.do_flow()
        except (NoRefreshTokenError, InvalidRefreshTokenError, RequestDeviceTokensError, PollingError) as e:
            err_log.error(f'Error in device_flow(): %s' % e)
    token = device_flow.access_token

    # to get file list
    url = url + '?list'

    f_names = []
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            r = requests.get(url, headers={"authorization": f"Bearer {token}"}, timeout=60)
            if r.status_code == requests.codes.ok:
                rl = r.text
                s_lines = rl.split('\n')
                for i in range(len(s_lines)):
                    f_name_tmp = s_lines[i].split(' ')[0]
                    if f_name_tmp.endswith(ext):     # filter
                        f_names.append(s_lines[i].split(' ')[0])
            if f_names and ext != 'log.txt':
                f_names = remove_f_duplicates(f_names)
            return sorted(f_names)
        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            if attempt < max_attempts - 1:
                err_log.warning(f' Failed in f_list_unavco({url}). Retrying in 10 seconds...')
                time.sleep(10)
            else:
                if ext == 'd.Z':
                    err_log.error(' Could not handle the exception from f_list_unavco when requesting RINEX list: %s. '
                                  'Aborting...' % ex)
                    return None
                else:
                    err_log.error(' Could not handle the exception from f_list_unavco when requesting logfiles list: '
                                  '%s. Aborting...' % ex)
                    return 'unavco logfile list error'
