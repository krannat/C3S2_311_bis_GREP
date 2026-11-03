import datetime
import logging
import os
import time
import sys
import requests
import config
from bs4 import BeautifulSoup

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')



def get_chile_file_list_html(year, doy, down_path):
    """
    Function to download the CSN Chile daily directory listing (https://gps.csn.uchile.cl/data/YYYY/DOY/) with curl
    and save it as 'csn_YYYY_DOY.html' in down_path (changes the working directory temporarily).
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :param down_path: The local directory to save the HTML file to.
    :return: True if the curl command was executed, otherwise False.
    """
    base_url = 'https://gps.csn.uchile.cl/data/'
    remote_url = base_url + str(year) + '/' + str(doy).zfill(3) + '/'
    d_fname= 'csn_' + str(year) + '_' + str(doy).zfill(3) + '.html'
    rep: int = 0  # initializing
    max_retries = 5  # maximum number of attempts if process unsuccessful
    got_file = False
    cur_dir = os.getcwd()
    os.chdir(down_path)
    while not got_file and rep < max_retries:
        try:
            cmd = 'curl -s --list-only ' + remote_url + ' -o ' + d_fname
            os.system(cmd)
            got_file = True

        except Exception as ex:
            err_log.warning(' get_chile_file_list_html(): %s. Retrying in 10 seconds.' % ex)
            time.sleep(10)  # increase the delay 10 --> 120 (for test)
            rep += 1

    os.chdir(cur_dir)
    return got_file


def file_list_from_html(fp_name):
    """
    Function to parse a locally saved HTML directory listing and extract the file names ending with 'd.Z'.
    :param fp_name: The path of the HTML file.
    :return: List of RINEX file names, or None on (request) exception.
    """

    try:
        f = open(fp_name, 'r')
        page = f.read()
        f.close()

        soup = BeautifulSoup(page, 'html.parser')
        tbl = soup.find('table')
        tbl_links = tbl.find_all(class_='link')
        sites_list = []

        for i in range(len(tbl_links)):
            l_temp = BeautifulSoup(str(tbl_links[i]), "lxml").get_text()
            if l_temp.endswith('d.Z'):
                sites_list.append(l_temp)
        return sites_list
    except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
            requests.exceptions.ConnectionError) as ex:
        print(' %s - from from list ' % ex)


def file_list_from_local_dir(dir_path):
    """
    Function to list the files ending with 'd.Z' in a local directory.
    :param dir_path: The local directory path.
    :return: List of file names (empty list on OS error).
    """
    try:
        return [f for f in os.listdir(dir_path) if f.endswith('d.Z')]
    except OSError as ex:
        print(f' {ex} - from file_list_from_dir')
        return []


def get_chile_file_list(remote_url, year, doy, down_path):
    """
    Function to get the CSN Chile RINEX file list for a day by downloading the HTML directory listing to down_path
    and parsing it.
    :param remote_url: The remote directory URL (currently not used).
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :param down_path: The local directory for the HTML file.
    :return: List of RINEX file names (empty list if the listing could not be downloaded).
    """
    # f_list = file_list_from_url(remote_url)  # Worked once in Hannes' env

    f_fname = 'csn_' + str(year) + '_' + str(doy).zfill(3) + '.html'
    fpath = down_path + f_fname
    f_list = []
    if get_chile_file_list_html(year, doy, down_path):
        f_list = file_list_from_html(fpath)
    return f_list


def download_rinex_csn(year, from_doy, to_doy):
    """
    Function to download all daily CSN Chile RINEX files ('d.Z') for a range of days with curl into
    config.chile_rinex_temp_down_path/YYYY/DOY/ (directories are created if missing).
    :param year: The year of the RINEX files.
    :param from_doy: The first day of year to download.
    :param to_doy: The last day of year to download (inclusive).
    :return: None.
    """
    base_path = config.chile_rinex_temp_down_path
    start_time = datetime.datetime.now()
    from_doy = int(from_doy)
    to_doy = int(to_doy)
    for i in range(from_doy, to_doy + 1):
        tmp_doy = i
        print(f'Downloading CSN RINEXes for {year} {tmp_doy}')

        # Setup paths
        #tmp_down_path = os.path.join(base_path, str(year), str(i).zfill(3))
        tmp_down_path = base_path + str(year) + '/' + str(i).zfill(3) + '/'
        if not os.path.exists(tmp_down_path):
            os.makedirs(tmp_down_path)

        base_url = 'https://gps.csn.uchile.cl/data/'
        remote_url = base_url + str(year) + '/' + str(i).zfill(3) + '/'

        files_to_download = get_chile_file_list(remote_url, year, tmp_doy, tmp_down_path)

        # download all files for one day
        for j in range(len(files_to_download)):
            tmp_fname = files_to_download[j]
            rep: int = 0  # initializing
            max_retries = 5  # maximum number of attempts if process unsuccessful
            got_file = False
            cur_dir = os.getcwd()
            os.chdir(tmp_down_path)
            while not got_file and rep < max_retries:
                try:
                    cmd = 'curl -s -O ' + remote_url + tmp_fname
                    os.system(cmd)
                    got_file = True

                except Exception as ex:
                    err_log.warning(' Error in download_rinex_csn: %s. Retrying in 10 seconds.' % ex)
                    time.sleep(10)  # increase the delay 10 --> 120 (for test)
                    rep += 1

            os.chdir(cur_dir)
            # return got_file
    end_time = datetime.datetime.now()
    print(f'Time spent for downloading days {from_doy} {to_doy}: {end_time - start_time}')


def main(year, from_doy, to_doy):
    """
    Function to run the CSN Chile RINEX download for a range of days.
    :param year: The year of the RINEX files.
    :param from_doy: The first day of year to download.
    :param to_doy: The last day of year to download (inclusive).
    :return: None.
    """
    print(f'Starting CSN RINEX download for {year} doys {from_doy} to {to_doy}')
    download_rinex_csn(year, from_doy, to_doy)
    print('FINISHED!')


if __name__ == '__main__':
    if len(sys.argv) == 4:
        main(sys.argv[1], sys.argv[2], sys.argv[3])  # python script.py arg1 arg2 arg3
    else:
        main(2013, 2, 2)
