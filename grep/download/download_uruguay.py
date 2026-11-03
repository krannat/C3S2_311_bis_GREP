import os
import urllib
import logging
import time
from paramiko import SSHClient, AutoAddPolicy
import ftplib
from datetime import datetime
import config
from urllib.parse import urlparse
from compare import compare_rinex_log


res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def download_rinex_files_sftp(pf_name, uri, local_path):
    """
    Function to download a RINEX file from Uruguay via SFTP, retrying the connection and the download up to 5 times.
    :param pf_name: The name of the RINEX file to download.
    :param uri: The remote URI (host and directory) of the file.
    :param local_path: The local directory to download the file to.
    :return: The unzipped file name, or None if the connection or download failed.
    """

    local_full_fn = os.path.join(local_path, pf_name)
    # Parse the URI
    url = urllib.parse.urlparse(uri)

    max_retries = 5  # same for creating the connection and for download
    wait_time = 10
    ssh_conn = False
    sftp_conn = False
    for n in range(max_retries):
        try:
            if not ssh_conn:
                ssh = SSHClient()
                ssh.set_missing_host_key_policy(AutoAddPolicy())
                ssh.connect(url.hostname, 2222, username="regna", password="historico", banner_timeout=200)
                ssh_conn = True

            if not sftp_conn and ssh_conn:
                sftp = ssh.open_sftp()
                sftp_conn = True

            # Exit the loop if both the SSH and SFTP connections were successful
            if ssh_conn and sftp_conn:
                break
        except Exception as e:
            err_log.warning(f" URUGUAY: SSH connection failed in download_uruguay.download_rinex_files_sftp() "
                            f"with error: {e}. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

    if not ssh_conn or not sftp_conn:
        err_log.error(f" URUGUAY: SSH connection failed in download_uruguay.download_rinex_files_sftp(). "
                      f"Max retries reached. Aborting...")
        return None

    # Construct the full remote filename
    remote_full_fn = os.path.join(url.path, pf_name)

    rep = 0
    unzipped_file_name = None
    while not unzipped_file_name and rep < max_retries:
        try:
            sftp.get(remote_full_fn, local_full_fn)
            rinex_lines, unzipped_file_name = compare_rinex_log.readlines_zipped(local_full_fn, get_only_path=True)
            if unzipped_file_name is not None:
                break
            else:
                if rep < max_retries - 1:
                    err_log.warning(f' URUGUAY: download_rinex_files_sftp(). '
                                    f'Retrying to download {pf_name} in {wait_time} seconds...')
                    time.sleep(10)
                    rep += 1
                else:
                    err_log.error(f' URUGUAY: download_rinex_files_sftp(). {pf_name} download aborted. '
                                  f'Max retries reached.')
                    return None
        except Exception as ex:
            if rep < max_retries - 1:
                err_log.warning(f' URUGUAY: Exception in download_rinex_files_sftp(): {ex}. '
                                f'Retrying to download {pf_name} in {wait_time} seconds...')
                time.sleep(10)
                rep += 1
            else:
                err_log.error(f' URUGUAY: Exception in download_rinex_files_sftp(): {ex}. {pf_name} download aborted. '
                              f'Max retries reached.')
                return None

    sftp.close()
    ssh.close()
    return unzipped_file_name


def download_rinex_files_ftp(pf_name, uri, local_path):
    """
    Function to download a RINEX file from Uruguay via anonymous FTP in EPSV mode, retrying the download up to 5 times.
    :param pf_name: The name of the RINEX file to download.
    :param uri: The remote URI (host and directory) of the file.
    :param local_path: The local directory to download the file to.
    :return: The unzipped file name, or None if the download failed.
    """
    local_full_fn = os.path.join(local_path, pf_name)
    # Parse URI
    url = urllib.parse.urlparse(uri)
    # Construct the full remote filename
    remote_full_fn = url.path + '/' + pf_name

    # Create a new FTP client
    ftp = ftplib.FTP(url.hostname)
    # Connect to the server
    ftp.login('Anonymous')

    # use EPSV-only mode
    ftp.sendcmd("EPSV ALL")
    ftp.set_pasv(True)
    ftp.makepasv = makeepsv.__get__(ftp, ftplib.FTP)

    max_retries = 5
    rep = 0
    wait_time = 10
    unzipped_file_name = None
    while not unzipped_file_name and rep < max_retries:
        try:
            with open(local_full_fn, 'wb') as local_file:
                ftp.retrbinary('RETR ' + remote_full_fn, local_file.write)
            rinex_lines, unzipped_file_name = compare_rinex_log.readlines_zipped(local_full_fn, get_only_path=True)
            if unzipped_file_name is not None:
                break
            else:
                if rep < max_retries - 1:
                    err_log.warning(f' URUGUAY: download_rinex_files_ftp(). '
                                    f'Retrying to download {pf_name} in {wait_time} seconds...')
                    time.sleep(10)
                    rep += 1
                else:
                    err_log.error(f' URUGUAY: download_rinex_files_ftp(). {pf_name} download aborted. '
                                  f'Max retries reached.')
                    return None
        except Exception as ex:
            if rep < max_retries - 1:
                err_log.warning(f' URUGUAY: Exception in download_rinex_files_ftp(): {ex}. '
                                f'Retrying to download {pf_name} in {wait_time} seconds...')
                time.sleep(10)
                rep += 1
            else:
                err_log.error(f' URUGUAY: Exception in download_rinex_files_ftp(): {ex}. {pf_name} download aborted. '
                              f'Max retries reached.')
                return None
    ftp.quit()
    return unzipped_file_name


def makeepsv(self):
    """
    Function to force EPSV (Extended Passive Mode); bound to an ftplib.FTP instance so it is called instead of PASV.
    :param self: The ftplib.FTP instance.
    :return: A tuple (host, port) parsed from the EPSV response.
    """
    resp = self.sendcmd("EPSV")
    if not resp.startswith("229"):
        raise ftplib.error_proto(resp)

    # Parse: 229 Entering Extended Passive Mode (|||port|)
    start = resp.find("(")
    end = resp.find(")")
    if start < 0 or end < 0:
        raise ftplib.error_proto("Invalid EPSV response")

    inside = resp[start + 1:end]  # |||port|
    parts = inside.split("|")
    port = int(parts[3])

    return self.host, port


def get_site_logfile_uruguay(site):
    """
    Function to download the site logfile for a given site from Uruguay via anonymous FTP into the logfile archive,
    retrying up to 5 times.
    :param site: The site name to search for in the remote logfile list.
    :return: A tuple (log_name, download datetime, 'uruguay') on success, ('abort', None, None) if the logfile list
    could not be retrieved, or (None, None, None) if no logfile was found or the download failed.
    """
    if not os.path.exists(config.logfile_archive_path):
        os.makedirs(config.logfile_archive_path)
    max_attempts = 5
    url = urlparse(config.uruguay_log_url)
    hostname = url.netloc  # This gives 'pp.igm.gub.uy'
    directory = url.path  # This gives '/hatanaka/LogFiles'

    for attempt in range(max_attempts):
        try:
            ftp = ftplib.FTP(hostname, timeout=60)
            ftp.login("Anonymous")

            # Force EPSV-only behavior
            ftp.sendcmd("EPSV ALL")
            ftp.set_pasv(True)
            ftp.makepasv = makeepsv.__get__(ftp, ftplib.FTP)

            # Stepwise CWD
            parts = [p for p in directory.split("/") if p]
            if directory.startswith("/"):
                ftp.cwd("/")
            for p in parts:
                ftp.cwd(p)

            # Normal passive-mode NLST now works (EPSV)
            files = ftp.nlst()
            break

        except (Exception, ftplib.error_perm, ftplib.error_proto, ftplib.error_temp) as e:
            if attempt < max_attempts - 1:
                err_log.warning(f' Failed to get logfile list for uruguay using get_site_logfile_uruguay(): '
                                f'{str(e)}. Retrying in 10 seconds...')
                time.sleep(10)
            else:
                err_log.warning(f' Failed to get logfile list for uruguay using get_site_logfile_uruguay(): '
                                f'{str(e)}. Max attempts reached. Aborting...')
                ftp.close()
                return 'abort', None, None

    logs_found = [filename for filename in files if site.lower() in filename]
    if logs_found:
        log_name = logs_found[0]
        res_log.info(f' Trying to download the log file for {site}')
        local_path = os.path.join(config.logfile_archive_path, log_name)
        for attempt in range(max_attempts):
            try:
                with open(local_path, 'wb') as f:
                    ftp.retrbinary('RETR ' + log_name, f.write)
                ftp.close()

                res_log.info(f' Log {log_name} downloaded for uruguay site {site}')
                return log_name, datetime.now(), 'uruguay'
            except (Exception, ftplib.error_perm, ftplib.error_proto, ftplib.error_temp) as e:
                if attempt < max_attempts - 1:
                    err_log.warning(f' Failed to download {log_name} for uruguay using get_site_logfile_uruguay(): '
                                    f'{str(e)}. Retrying in 10 seconds...')
                    time.sleep(10)
                else:
                    err_log.warning(f' Failed to download {log_name} for uruguay using get_site_logfile_uruguay(): '
                                    f'{str(e)}. Max attempts reached. Aborting...')
                    ftp.close()
                    return None, None, None
    else:
        err_log.warning(f' No logfile for uruguay site {site} found')
        ftp.close()
        return None, None, None
