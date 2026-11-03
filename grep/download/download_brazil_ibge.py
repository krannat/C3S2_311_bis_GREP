import requests
import logging
import time
import os
import datetime
import inspect
import config
from process import process_brazil_ibge
from download import shared_download_requests

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def download_brazil_ibge_rinex_fileOLD(pf_name, remote_path, rinex_down_path, year, doy):
    """
    Function (old version) to download a RINEX file from IBGE (Brazil). A *.crx.gz file is downloaded directly into
    rinex_down_path; a *.zip folder is downloaded into a tmp folder, unzipped, and the *.YYd file moved to rinex_down_path.
    :param pf_name: The name of the RINEX file (*.zip or *.crx.gz) to download.
    :param remote_path: The remote URL path (replaced by a URL built from config, year and doy for *.zip/*.crx.gz).
    :param rinex_down_path: The local directory to download the file to.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :return: True if the file was downloaded.
    """

    yy = str(year)[-2:]
    zipped = False
    if pf_name.endswith('crx.gz'):
        remote_path = os.path.join(config.brazil_ibge_rinex3_url,
                                   str(year) + '/' + str(doy).zfill(3) + '/')
    if pf_name.endswith('.zip'):
        zipped = True
        remote_path = os.path.join(config.brazil_ibge_rinex_url,
                                   str(year) + '/' + str(doy).zfill(3) + '/')

    rep = 0  # maximum number of attempts if process unsuccessful
    got_file = False

    while got_file is False:
        try:
            if zipped:  # getting a zipped folder, with *.YYd

                rinex_full_fn = os.path.join(rinex_down_path + 'tmp/', pf_name)
                if not os.path.exists(rinex_down_path + 'tmp/'):
                    os.makedirs(rinex_down_path + 'tmp/')
                r = requests.get(remote_path + pf_name, timeout=120, stream=True)
                r.raise_for_status()
                with open(rinex_full_fn, 'wb') as fd:
                    for chunk in r.iter_content(chunk_size=1000):
                        fd.write(chunk)

                cwd = os.getcwd()
                os.chdir(rinex_down_path + 'tmp/')
                cmd = 'unzip ' + pf_name
                os.system(cmd)
                cmd1 = 'mv *.' + yy + 'd ' + rinex_down_path    # move *.YYd to where it belongs
                os.system(cmd1)
                os.chdir(rinex_down_path)
                cmd2 = 'rm -fr tmp'
                os.system(cmd2)
                os.chdir(cwd)
                got_file = True
            else:
                rinex_full_fn = os.path.join(rinex_down_path, pf_name)
                r = requests.get(remote_path + pf_name, timeout=120, stream=True)
                r.raise_for_status()
                with open(rinex_full_fn, 'wb') as fd:
                    for chunk in r.iter_content(chunk_size=1000):
                        fd.write(chunk)
                got_file = True

        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            err_log.error(' Exception in download_brazil_ibge_rinex_file(): %s. Retrying in 10 seconds.' % ex)
            time.sleep(10)  # increase the delay 10 --> 120 (for test)
            rep += 1

        except Exception as ex:
            err_log.error(' Exception in download_brazil_ibge_rinex_file(): %s' % ex)
            raise ex

    return got_file


def download_brazil_ibge_rinex_file(pf_name, remote_path, rinex_down_path, year, doy):
    """
    Function to download a RINEX file (*.zip or *.crx.gz) from IBGE (Brazil).
    :param pf_name: The name of the RINEX file to download.
    :param remote_path: The remote URL path (replaced by a URL built from config, year and doy for *.zip/*.crx.gz).
    :param rinex_down_path: The local directory to download the file to.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :return: The name of the downloaded (unzipped) file as returned by shared_download_requests.rinex_requests().
    """

    if pf_name.endswith('crx.gz'):
        remote_path = os.path.join(config.brazil_ibge_rinex3_url,
                                   str(year) + '/' + str(doy).zfill(3) + '/')
    if pf_name.endswith('.zip'):
        remote_path = os.path.join(config.brazil_ibge_rinex_url,
                                   str(year) + '/' + str(doy).zfill(3) + '/')

    # Prepare the request
    req = requests.Request('GET', remote_path + pf_name)
    prepared_req = req.prepare()

    curr_func_name = inspect.currentframe().f_code.co_name
    unzipped_file_name = shared_download_requests.rinex_requests(prepared_req, pf_name, rinex_down_path,
                                                                          'BRAZIL', curr_func_name)
    return unzipped_file_name


def get_site_logfile_brazil_ibge(site):
    """
    Function to download the site logfile for a given site from IBGE (Brazil) into the logfile archive,
    retrying up to 5 times on errors. A "403 Forbidden" response skips the download.
    :param site: The site name; matched against the first 4 characters of the remote logfile names.
    :return: A tuple (log_name, download datetime, 'brazil_ibge') on success, ('abort', None, None) if the logfile
    list could not be retrieved, or (None, None, None) if no logfile was found or the download failed.
    """
    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)

    url = config.brazil_ibge_logfiles_url
    max_attempts = 5

    for attempt in range(max_attempts):
        try:
            log_list = process_brazil_ibge.list_fd(url, '.log')
            if log_list is None:
                return 'abort', None, None

            logs_found = [filename for filename in log_list if site.lower() in filename[:4].lower()]
            if not logs_found:  # If no log files for the specific site found, abort.
                return None, None, None

            log_name = logs_found[0]
            r = requests.get(url + log_name, verify=False, timeout=120)
            r.raise_for_status()

            with open(config.logfile_archive_path + log_name, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=1000):
                    fd.write(chunk)
            return log_name, datetime.datetime.now(), 'brazil_ibge'

        except requests.exceptions.HTTPError as http_err:
            if http_err.response.status_code == 403:  # Access forbidden
                err_log.error(f' Forbidden access to the site logfile using {url}')
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
                err_log.warning(
                    f' Exception in get_site_logfile_brazil_ibge() for {site}: {ex}. Retrying in 10 seconds.')
                time.sleep(10)
            else:
                err_log.error(f' Exception in get_site_logfile_brazil_ibge() for {site}: {ex}. Max retries reached. '
                              f'Aborting...')
                return None, None, None
        except Exception as ex:
            if attempt < max_attempts - 1:  # if it's not the final attempt
                err_log.warning(f' Unknown exception in get_site_logfile_brazil_ibge(): {ex}. Retrying in 10 seconds.')
                time.sleep(10)
            else:
                err_log.error(
                    f' Unknown exception in get_site_logfile_brazil_ibge(): {ex}. Max retries reached. Aborting...')
                return None, None, None

