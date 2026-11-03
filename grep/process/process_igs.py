import logging
import time

import requests
import config

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def request_rinex_list(url, max_attempts):
    """
    Function to request a file list page from the given URL, retrying on timeouts/request errors.
    :param url: The URL to request.
    :param max_attempts: The maximum number of request attempts.
    :return: The response text, or None if all attempts failed.
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Connection": "keep-alive"
    }

    for attempt in range(max_attempts):
        try:
            r = requests.get(
                url,
                timeout=(5, 15),      # (connect timeout, read timeout)
                headers=headers
            )
            r.raise_for_status()
            return r.text

        except (requests.exceptions.Timeout,
                requests.exceptions.RequestException) as ex:

            if attempt < max_attempts - 1:
                err_log.warning(
                    f" request_rinex_list() failed: {ex}. "
                    f"Retrying in 10 seconds ({attempt+1}/{max_attempts})..."
                )
                time.sleep(10)
            else:
                err_log.error(
                    f" request_rinex_list(): {ex}. Max retries reached, aborting."
                )
                return None


def get_rinex_list_igs(year, doy):
    """
    Function to get the daily IGS RINEX list from the /YYYY/DOY/YYo/ directory, removing site duplicates
    (preferring '.Z' over '.gz' files).
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: Sorted list of RINEX file names without site duplicates, or None if the request failed or the list is empty.
    """
    url = config.igs_rinex_url + str(year) + '/' + str(doy).zfill(3) + '/' + str(year)[2:] + 'o/'
    if not url.endswith("*?list"):
        url = url + "*?list"

    res = request_rinex_list(url, 5)
    if res is None:
        return None

    f_list_z, f_list_gz = [], []
    f_list = res.split('\n')

    for i in range(len(f_list) - 1):
        filename = f_list[i].split()[0].strip()
        extension = filename.rsplit('.', 1)[-1]
        if extension == 'gz':
            f_list_gz.append(filename)
        elif extension == 'Z':
            f_list_z.append(filename)

    sum_list = f_list_z + f_list_gz
    if len(sum_list) == 0:
        return None

    site_dict = {}  # create dictionary for all sites, including duplicates for each site
    for file in sum_list:
        site_acr = file[:4].lower()
        file_ext = file.rsplit('.', 1)[-1]
        if site_acr not in site_dict:
            site_dict[site_acr] = {}
        site_dict[site_acr][file_ext] = file

    stn_dup_list = []  # loop over dict and find stations with more than one file available
    for stn, stn_files in site_dict.items():
        if len(stn_files) > 1:  # both .gz and .Z available
            stn_dup_list.append(stn)

    if stn_dup_list:
        res_log.info(f' Duplicates were found for the following sites ({len(stn_dup_list)} in total): \n{stn_dup_list}')

    # create new list from dict that does NOT contain duplicates
    rinex_list_without_dup = []
    for stn, stn_files in site_dict.items():
        # Pick the .Z file first if it's available, else pick the .gz file
        file_choice_order = ['Z', 'gz']
        for ext in file_choice_order:
            if ext in stn_files:
                rinex_list_without_dup.append(stn_files[ext])
                break

    return sorted(rinex_list_without_dup)
