import os
import logging
import config
from compare import compare_rinex_log
from datetime import datetime
import time
import threading
import requests
import subprocess


res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


class DownloaderThread(threading.Thread):
    """
    Class for a thread that downloads a single file via SFTP and records whether the download succeeded.
    """
    def __init__(self, sftp, full_path, local_path):
        """
        Method to initialize the downloader thread.
        :param sftp: The SFTP client used for the download.
        :param full_path: The full remote path of the file.
        :param local_path: The local path to download the file to.
        :return: None.
        """
        threading.Thread.__init__(self)
        self.sftp = sftp
        self.full_path = full_path
        self.local_path = local_path
        self.success = False

    def run(self):
        """
        Method to download the remote file to the local path via SFTP; sets self.success to True on success.
        :return: None.
        """
        try:
            err_log.info(f" Starting download from {self.full_path} to {self.local_path}")
            self.sftp.get(self.full_path, self.local_path)
            self.success = True
            err_log.info(f" Completed download from {self.full_path} to {self.local_path}")
        except Exception as ex:
            err_log.warning(f" Threaded download exception for {self.full_path}: {ex}")


def download_rinex_files_amazon(filename, remote_path, rinex_down_path):
    """
    Function to download a RINEX file from the Geoscience Australia (AUSPOS) Amazon S3 bucket using the AWS CLI,
    retrying up to 5 times.
    :param filename: The name of the RINEX file to download.
    :param remote_path: The remote S3 path of the file.
    :param rinex_down_path: The local directory to download the file to.
    :return: The unzipped file name, or None if the download failed.
    """
    cmd = [
        'aws', 's3', '--region=eu-north-1', '--no-sign-request', 'cp',
        f'{remote_path}{filename}', rinex_down_path
    ]
    rinex_full_fn = f'{rinex_down_path}/{filename}'
    unzipped_file_name = None
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            rinex_lines, unzipped_file_name = compare_rinex_log.readlines_zipped(rinex_full_fn, get_only_path=True)

            if unzipped_file_name is not None:
                break  # break the loop if success, no need to retry.
            else:
                # err_log.warning(' AUSPOS: Extracting or reading %s unsuccessful. ' % rinex_full_fn)
                if attempt < max_attempts - 1:  # if not the last attempt
                    err_log.warning(' AUSPOS: Retrying to download %s in 10 seconds...' % filename)
                    time.sleep(10)  # wait before retrying
                    continue
                else:
                    err_log.error(' AUSPOS: %s download aborted. Max retries reached.' % filename)
                    return None

        except subprocess.CalledProcessError:
            if attempt < max_attempts - 1:
                err_log.warning(f' AUSPOS: Failed to download RINEX: {filename}. Retrying in 10 seconds...')
                time.sleep(10)
            else:
                err_log.error(f' AUSPOS: Failed to download RINEX after {max_attempts} attempts: {filename}. Skipping...')
                return None
    return unzipped_file_name


def find_latest_file(aus_log_down_path, site_4char, proc_date):
    """
    Function to find the latest already present AUSPOS XML logfile of a site with a date (from the file name)
    later than the processing date.
    :param aus_log_down_path: The path to the logfiles.
    :param site_4char: The site's 4-character identification.
    :param proc_date: The datetime object of the processing date.
    :return: A tuple (latest logfile name, its date), or (None, None) if no such logfile exists.
    """
    latest_file = None
    latest_date = None

    for filename in os.listdir(aus_log_down_path):
        if filename.endswith("_log.xml") and filename.startswith(site_4char):
            first_part = filename[:4]
            rest_parts = filename[5:].split("_")
            parts = [first_part] + rest_parts
            if len(parts) > 2:
                file_date = datetime.strptime(parts[1], '%Y-%m-%d')

                if file_date > proc_date and (latest_date is None or file_date > latest_date):
                    latest_file = filename
                    latest_date = file_date

    return latest_file, latest_date


def get_site_logfiles_auspos(site_4char, current_date, proc_date):
    """
    Function to get the GeodesyML (XML) site logfile of a site from Geoscience Australia (AUSPOS). An already present
    logfile newer than the processing date is reused; otherwise the logfile is downloaded with curl into the
    logfile archive, retrying up to 5 times.
    :param site_4char: The site's 4-character identification.
    :param current_date: The current date as a string YYYY-MM-DD (used in the logfile name).
    :param proc_date: The datetime object of the processing date.
    :return: A tuple (log_name, log date or download datetime, 'auspos'), or (None, None, None) if the download failed.
    """

    aus_log_down_path = config.logfile_archive_path
    if not os.path.exists(aus_log_down_path):
        os.makedirs(aus_log_down_path)

    os.chdir(aus_log_down_path)

    log_name = site_4char + '_' + current_date + '_log.xml'

    latest_log_name, latest_log_date = find_latest_file(aus_log_down_path, site_4char, proc_date)
    if latest_log_name is not None:
        res_log.info(f' Logfile for {site_4char} found: {latest_log_name}. Skipping the download...')
        return latest_log_name, latest_log_date, 'auspos'

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            # cmd = 'curl \'https://gws.geodesy.ga.gov.au/siteLogs/search/findByFourCharacterId?id=ALIC&format=geodesyml\' -i' \
            url_path = os.path.join(config.auspos_logfiles_url,
                                    'search/findByFourCharacterId?id=') + site_4char + '&format=geodesyml'
            cmd = ('curl -s \'' + url_path + '\' -i' + ' ' + '> ' + aus_log_down_path + site_4char + '_' +
                   current_date + '_log.tmp')
            os.system(cmd)

            # Must cut the useless content up to <?xml version="1.0" encoding="UTF-8"?>
            fi = open(site_4char + '_' + current_date + '_log.tmp', 'r')
            tmp_lines = fi.readlines()
            fi.close()

            fo = open(log_name, 'w')
            search_str = '<?xml version="1.0" encoding="UTF-8"?>'
            start_line = 0
            for i in range(len(tmp_lines)):
                if search_str in tmp_lines[i]:
                    start_line = i
                    fo.write(tmp_lines[i])
                    continue
                elif start_line > 0:
                    fo.write(tmp_lines[i])
                    continue
            fo.close()
            cmd1 = 'rm ' + site_4char + '_' + current_date + '_log.tmp'
            os.system(cmd1)

            # xml_to_json(site_4char + '_' + current_date + '_log.xml')
            res_log.info(' Logfile downloaded for site %s' % site_4char)
            return log_name, datetime.now(), 'auspos'
            # print(js)
        except (ConnectionError, IOError, FileNotFoundError) as e:
            if attempt < max_attempts - 1:
                err_log.warning(f' Failed to download auspos logfile for site: {site_4char}. Retrying in 10 seconds.')
                time.sleep(10)
            else:
                err_log.error(' Error with downloading logfile for auspos site %s: %s' % (site_4char, e))
                return None, None, None
