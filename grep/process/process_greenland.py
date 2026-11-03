import logging
import time
import config
import pycurl
from io import BytesIO

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')

# https://go-gnet.org/data-and-site-log *.log
# RINEX2: ftps://ftp.dataforsyningen.dk/GNSS/RINEX2/GRL/
# RINEX3: ftps://ftp.dataforsyningen.dk/GNSS/RINEX3/GRL/    since 2020 DOY168 *_30S_MO.crx.gz


def get_sample_directory_list_rinex2(year, doy):
    """
    Function to get the list of sampling interval subdirectories ('secXX') for Greenland RINEX2 data of a given day
    from the remote FTP server (retries up to 5 times).
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: List of subdirectory names (e.g. 'sec01', 'sec15', 'sec30'), or an empty list on failure.
    """
    year = str(year)
    doy = str(doy).zfill(3)
    rinex_version = 'RINEX2'

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            # Initiate the connection and setup for passive connection
            c = pycurl.Curl()
            c.setopt(c.URL, f"{config.greenland_main_url}{rinex_version}/GRL/{year}/{doy}/")
            c.setopt(c.FTP_USE_EPSV, 0)  # 0=Passive, 1=Active
            c.setopt(c.SSL_VERIFYPEER, 0)
            c.setopt(c.SSL_VERIFYHOST, 0)
            c.setopt(c.VERBOSE, 0)

            # Prepare to save the response
            buffer = BytesIO()
            c.setopt(c.WRITEDATA, buffer)

            # Send the request
            c.perform()
            c.close()

            # Get the response and decode it to get the lines (the file-list)
            body = buffer.getvalue()
            body_decoded = body.decode('utf-8')
            lines = body_decoded.split('\n')
            sec_dir_list = [line.split()[-1] for line in lines if line and 'sec' in line]
            return sec_dir_list
        except pycurl.error as ex:  #
            if attempt < max_attempts - 1:
                err_log.warning(f' Failed in get_sample_directory_list_rinex2(). Retrying in 10 seconds...')
                time.sleep(10)
            else:
                err_log.error(' %s - get_sample_directory_list_rinex2()' % ex)
                return []


def get_rinex_file_list(year, doy):
    """
    Function to get the Greenland observation RINEX file lists for a given day, grouped by sampling interval
    directory. RINEX2 is used for years 1995-2021 (sec15 and sec30, no site duplicates), RINEX3 30S files for years >= 2022.
    :param year: The year of the RINEX files (int).
    :param doy: The day of year of the RINEX files.
    :return: Dictionary with sampling interval directory names ('sec15', 'sec30') as keys and lists of RINEX file names as values.
    """
    # If 1995 <= year <= 2020? only RINEX2 available. RINEX3 since 2020 DOY168 *_30S_MO.crx.gz. For RINEX list we don't
    # care about sample interval and RINEX version. RINEX2 filenames all converted to RINEX3-standard long filenames
    # with 'sample_interval' found by Anubis.

    # set RINEX version according to year RINEX2 1995 DOY126 - 2021 DOY365, starting with /sec30 but later years also
    # nav files in the same directory and /sec30 consists of only navigation RINEXes, data in /sec15
    # RINEX2 for years 2020 (partly) and 2021 ovelaps with RINEX3 (but the numbers of sites are different)

    # For years 1995-2021 choosing rinex_version = 'RINEX2'
    # OVERLAPPING 2020 DOY168 - 2021 DOY365 ==> 1) search sites from RINEX3 and 2) later take all not found from RINEX3
    # for years >= 2022 rinex_version = RINEX3
    files_by_intervals = {}
    s_year = str(year)
    s_doy = str(doy).zfill(3)

    if 1995 <= year <= 2021:
        sum_list = []
        rinex_version = 'RINEX2'
        sec_dir = get_sample_directory_list_rinex2(year, doy)  # list of /secXX for RINEX2
        for i in range(len(sec_dir)):
            directory_path = f"{config.greenland_rinex2_url}{s_year}/{s_doy}/{sec_dir[i]}/"
            sum_list.append(get_file_list_by_rinex_version(rinex_version, directory_path))

        # Now all sites in sec_dir lists, start to select by sampling interval and avoid find site duplicates
        sites_sum = []
        for i in range(len(sum_list)):
            if sec_dir[i] == 'sec01':  # ignore sites 1s directory
                continue
            if sec_dir[i] == 'sec15':
                tmp_rin = []
                for j in range(len(sum_list[i])):
                    site_tmp = sum_list[i][j][:4]
                    if site_tmp not in sites_sum:
                        sites_sum.append(site_tmp)
                        tmp_rin.append(sum_list[i][j])
                files_by_intervals[sec_dir[i]] = tmp_rin
            if sec_dir[i] == 'sec30':
                tmp_rin = []  # reset
                for j in range(len(sum_list[i])):
                    site_tmp = sum_list[i][j][:4]
                    if site_tmp not in sites_sum:
                        sites_sum.append(site_tmp)
                        tmp_rin.append(sum_list[i][j])
                files_by_intervals[sec_dir[i]] = tmp_rin
        # Now having all sites' RINEXes in files_by_intervals selected by 'sampling_interval', no site duplicates
        return files_by_intervals

    # in RINEX3 all data in /GNSS/RINEX3/GRL/YYYY/DOY/ as '_15S_MO' and/or '_30S_MO' *.crx.gz and we take _30S files
    if year >= 2022:  # only RINEX3 and taking 30s, but since 2024 DOY333 the number of sites drops ca 3x,
        # probably the files are added later (last checked 09. January 2025)
        sample_interval = '_30S_MO'  # selecting 30S RINEX only
        # sec30 is "fake" -- for RINEX3 all intervals in the same /YYYY/DOY/ directory, but selecting 30S files
        sec_dir = 'sec30'  # selecting 30S RINEX only
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                # Initiate the connection and setup for passive connection
                c = pycurl.Curl()
                u = f"{config.greenland_rinex3_url}{s_year}/{s_doy}"
                c.setopt(c.URL, f"{config.greenland_rinex3_url}{s_year}/{s_doy}/")
                c.setopt(c.FTP_USE_EPSV, 0)  # 0=Passive, 1=Active
                c.setopt(c.SSL_VERIFYPEER, 0)
                c.setopt(c.SSL_VERIFYHOST, 0)
                c.setopt(c.VERBOSE, 0)

                # Prepare to save the response
                buffer = BytesIO()
                c.setopt(c.WRITEDATA, buffer)
                c.setopt(pycurl.CONNECTTIMEOUT, 30)
                c.setopt(pycurl.TIMEOUT, 30)

                # Send the request
                c.perform()
                c.close()

                # Get the response and decode it to get the lines (the file-list)
                body = buffer.getvalue()
                body_decoded = body.decode('utf-8')
                lines = body_decoded.split('\n')

                file_list = [line.split()[-1] for line in lines if line and sample_interval in line]
                files_by_intervals[sec_dir] = file_list
                return files_by_intervals
            except pycurl.error as ex:  #
                if attempt < max_attempts - 1:
                    err_log.warning(f' Failed in get_rinex_file_list({s_year}, {s_doy}). Retrying in 10 seconds...')
                    time.sleep(10)
                else:
                    err_log.error(' %s - get_rinex_file_list(%s, %s)' % (ex, s_year, s_doy))
                    return files_by_intervals


def get_file_list_by_rinex_version(rinex_version, directory_path):
    """
    Function to get the list of observation RINEX files from a remote directory, filtered by RINEX version
    ('_30S_MO.crx.gz' for RINEX3, 'd.gz' for RINEX2). Retries up to 5 times.
    :param rinex_version: The RINEX version ('RINEX2' or 'RINEX3').
    :param directory_path: The remote directory URL.
    :return: List of RINEX file names, or an empty list on failure.
    """
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            # Initiate the connection and setup for passive connection
            c = pycurl.Curl()
            c.setopt(c.URL, directory_path)
            c.setopt(c.FTP_USE_EPSV, 0)  # 0=Passive, 1=Active
            c.setopt(c.SSL_VERIFYPEER, 0)
            c.setopt(c.SSL_VERIFYHOST, 0)
            c.setopt(c.VERBOSE, 0)

            # Prepare to save the response
            buffer = BytesIO()
            c.setopt(c.WRITEDATA, buffer)
            c.setopt(pycurl.CONNECTTIMEOUT, 30)
            c.setopt(pycurl.TIMEOUT, 30)

            # Send the request
            c.perform()
            c.close()

            # Get the response and decode it to get the lines (the file-list)
            body = buffer.getvalue()
            body_decoded = body.decode('utf-8')
            lines = body_decoded.split('\n')
            if rinex_version == 'RINEX3':
                sample_interval = '_30S_MO.crx.gz'
                file_list = [line.split()[-1] for line in lines if line and sample_interval in line]  # for RINEX3 only
            else:
                # using a filter by 'd.gz' to avoid navigation data files in 'secXX'
                file_list = [line.split()[-1] for line in lines if line and 'd.gz' in line]     # for RINEX2
            return file_list
        except pycurl.error as ex:  #
            if attempt < max_attempts - 1:
                err_log.warning(f' Failed in get_file_list_by_rinex_version(). Retrying in 10 seconds...')
                time.sleep(10)
            else:
                err_log.error(' %s - get_file_list_by_rinex_version' % ex)
                return []


def get_log_list_greenland():
    """
    Function to get the list of Greenland site log files ('.log') from the remote site log directory
    (config.greenland_logfiles_url). Retries up to 5 times.
    :return: List of log file names, or None on failure.
    """
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            # Initiate the connection and setup for passive connection
            c = pycurl.Curl()
            c.setopt(c.URL, f"{config.greenland_logfiles_url}")
            c.setopt(c.FTP_USE_EPSV, 0)  # 0=Passive, 1=Active
            c.setopt(c.SSL_VERIFYPEER, 0)
            c.setopt(c.SSL_VERIFYHOST, 0)
            c.setopt(c.VERBOSE, 0)

            # Prepare to save the response
            buffer = BytesIO()
            c.setopt(c.WRITEDATA, buffer)
            c.setopt(pycurl.CONNECTTIMEOUT, 30)
            c.setopt(pycurl.TIMEOUT, 30)

            # Send the request
            c.perform()
            c.close()

            # Get the response and decode it to get the lines (the file-list)
            body = buffer.getvalue()
            body_decoded = body.decode('utf-8')
            lines = body_decoded.split('\n')

            # file_list = [line.split()[-1] for line in lines if line and sample_interval in line]
            log_list = [line.split()[-1] for line in lines if line and '.log' in line]
            return log_list
        except pycurl.error as ex:  #
            if attempt < max_attempts - 1:
                err_log.warning(f' Failed in get_log_list_greenland(). Retrying in 30 seconds...')
                time.sleep(30)
            else:
                err_log.error(' %s - from get_log_list_greenland(). No more retries left. Aborting...' % ex)
                return None


def get_sample_interval_dir(f_name, file_lists_dir):
    """
    Function to find the remote sampling interval subdirectory ('secXX') to which the given RINEX file belongs.
    :param f_name: The RINEX file name.
    :param file_lists_dir: Dictionary with sampling interval directory names as keys and lists of RINEX file names as values.
    :return: The subdirectory name (e.g. 'sec15' or 'sec30') containing the file.
    """
    # file_list = get_rinex_file_list(2010, 1)  # (2024, 1)
    file_list = file_lists_dir
    keys = list(file_list.keys())

    for i in range(len(keys)):
        if f_name in file_list.get(keys[i]):
            # print(f"RINEX from {keys[i]}")
            sec_dir = keys[i]
    return sec_dir


def get_rinex_list_and_remote_dir_list(year, doy):
    """
    Function to get the sorted Greenland observation RINEX list and a matching list of remote directory URLs
    (one URL per RINEX file; RINEX2 or RINEX3 detected by file name).
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: Tuple (obs_rinex, tmp_remote_dir) of RINEX file names and their remote directory URLs.
    """
    obs_files_dir = get_rinex_file_list(year, doy)  # gets a directory
    obs_files_dir.keys()
    d_keys = list(obs_files_dir.keys())
    obs_files = []
    # NB! For RINEX3 the fake key "sec30" is misleading but used for consistency
    for i in range(len(d_keys)):
        obs_files = obs_files + obs_files_dir.get(d_keys[i])
    obs_rinex = sorted(obs_files)

    s_year = str(year)
    s_doy = str(doy).zfill(3)
    tmp_remote_dir = []

    for i in range(len(obs_rinex)):
        if '_30S_MO.crx.gz' in obs_rinex[i]:    # RINEX3
            tmp_fileurl = f"{config.greenland_rinex3_url}{s_year}/{s_doy}"
            tmp_remote_dir.append(tmp_fileurl)
        else:   # RINEX2
            sec_dir = get_sample_interval_dir(obs_rinex[i], obs_files_dir)
            tmp_fileurl = f"{config.greenland_rinex2_url}{s_year}/{s_doy}/{sec_dir}"
            tmp_remote_dir.append(tmp_fileurl)
    return obs_rinex, tmp_remote_dir
