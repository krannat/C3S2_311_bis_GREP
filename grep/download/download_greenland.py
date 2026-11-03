import pycurl
import certifi
import os
import time
import logging
from datetime import datetime

from process import process_greenland
import config
from compare import compare_rinex_log


res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')

# https://go-gnet.org/data-and-site-log *.log
# RINEX2: ftps://ftp.dataforsyningen.dk/GNSS/RINEX2/GRL/
# RINEX3: ftps://ftp.dataforsyningen.dk/GNSS/RINEX3/GRL/    since 2020 DOY168 *_30S_MO.crx.gz


def download_rinex_file_greenland(f_name, remote_path, rinex_down_path):
    """
    Function to download one RINEX file from Greenland using pycurl, retrying up to 5 times.
    :param f_name: The name of the RINEX file to download.
    :param remote_path: The remote URL path, according to "sec key" from {} of process_greenland.get_rinex_file_list().
    :param rinex_down_path: The local directory to download the file to.
    :return: The unzipped file name, or None if the download failed.
    """
    unzipped_file_name = None
    rep = 0
    max_rep = 5
    file_url = f"{remote_path}/{f_name}"
    local_file_path = os.path.join(rinex_down_path, f_name)
    while not unzipped_file_name and rep < 5:  # added condition to avoid infinite loop if unable to get file
        try:
            with open(local_file_path, 'wb') as f:
                c = pycurl.Curl()
                c.setopt(c.URL, file_url)
                c.setopt(c.WRITEDATA, f)
                c.setopt(pycurl.CONNECTTIMEOUT, 30)
                c.setopt(pycurl.TIMEOUT, 30)
                c.setopt(pycurl.CAINFO, certifi.where())
                c.setopt(pycurl.SSL_VERIFYPEER, 0)  # Disable SSL verification
                c.setopt(pycurl.SSL_VERIFYHOST, 0)  # Disable SSL verification
                c.perform()
                c.close()

            rinex_lines, unzipped_file_name = compare_rinex_log.readlines_zipped(local_file_path, get_only_path=True)
            if unzipped_file_name is not None:
                break

        except pycurl.error as ex:
            err_log.error(' Greenland: Download error using url %s - %s.' % (file_url, ex))

        if rep < max_rep - 1:
            err_log.warning(' Greenland: Retrying to download %s in 10 seconds...' % f_name)
            time.sleep(10)
            rep += 1

    if not unzipped_file_name:
        err_log.error(' Greenland: %s download aborted. Max retries reached.' % f_name)

    return unzipped_file_name


def get_site_logfile_greenland(site):
    """
    Function to download the site logfile for a given site from Greenland (config.greenland_logfiles_url) using
    pycurl into the logfile archive, retrying up to 5 times.
    :param site: The site name to search for in the remote logfile list.
    :return: A tuple (log_name, download datetime, 'greenland') on success, ('abort', None, None) if the logfile
    list is empty, or (None, None, None) if no logfile was found or the download failed.
    """

    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)
    rep = 0
    got_file = False

    while not got_file and rep < 5:  # added condition to avoid infinite loop if unable to get file
        try:
            # get file list
            log_list = process_greenland.get_log_list_greenland()
            if not log_list:
                return 'abort', None, None

            logs_found = [filename for filename in log_list if site.lower() in filename]

            if logs_found:
                # if there are many log files for the same station, just take the first one
                log_name = logs_found[0]
                # file_url = f"ftps://{username}:{password}@{hostname}:990{remote_log_dir}{log_name}"
                file_url = f"{config.greenland_logfiles_url}{log_name}"
                local_file_path = os.path.join(config.logfile_archive_path, log_name)

                # Open the local file to write
                with open(local_file_path, 'wb') as f:
                    c = pycurl.Curl()
                    c.setopt(c.URL, file_url)
                    c.setopt(c.WRITEDATA, f)
                    c.setopt(pycurl.CONNECTTIMEOUT, 30)
                    c.setopt(pycurl.TIMEOUT, 30)
                    c.setopt(pycurl.CAINFO, certifi.where())
                    c.perform()
                    c.close()
                    got_file = True

                return log_name, datetime.now(), 'greenland'
            else:
                return None, None, None

        except pycurl.error as ex:
            err_log.error(' %s - from get_site_logfile_greenland(). Retrying in 10 seconds.' % ex)
            time.sleep(10)
            rep += 1
            if rep >= 5:
                return None, None, None
