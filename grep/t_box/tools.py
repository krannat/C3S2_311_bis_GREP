import ftplib
import pandas as pd
import logging
import os
from os import listdir
from os.path import isfile, join
import glob
import shutil
import time
from math import pi, sqrt, cos, fabs, atan, atan2

from datetime import date, timedelta, datetime

import requests
import urllib3

import config
from download import download_us_cors
from process import process_unavco

from earthscope_sdk.auth.device_code_flow import DeviceCodeFlow, DeviceCodeFlowSimple
from earthscope_sdk.auth.auth_flow import NoTokensError

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib

import xmltodict
import json

matplotlib.use('TkAgg')
import matplotlib.pyplot as plt  # TODO matplotlib incompatible or incomplete ??

from compare import compare_rinex_log

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def cartesian2geodetic(x, y, z):
    """ ECEF2WGS84 converts earth-centered, earth-fixed coordinates to geodetic
    latitude, longitude, and HAE (WGS84) using the improved Bowring method.
    [LAT, LON, ELE] = ECEF2WGS84(X, Y, Z) converts ECEF cartesian coordinates
    X, Y, Z in meters into an array of coordinates. Both LAT and LON are in
    degrees. ELE is in meters.
    References:
    [1] Toms, R. M., "An Efficient Algorithm for Geocentric to Geodetic
    Coordinate Conversion", Lawrence Livermore National Laboratory, 1995,
    http://www.osti.gov/energycitations/servlets/purl/110235-MLuPMu/
    webviewable/110235.pdf
    """
    # not changing the notation of the variables, leaving the lowercase and uppercase "as used in the source"
    # corrected errors in the source (probably written in FORTRAN)

    a = 6378137.0  # WGS84 equatorial radius (m)
    c = 6356752.3142  # WGS84 polar radius (m)
    aD_c = 1.0026  # only valid below 2000 km HAE

    f = (a - c) / a
    e2 = (a * a - c * c) / (a * a)
    E2 = (a * a - c * c) / (c * c)

    w = sqrt(x * x + y * y)
    t_0 = z * aD_c
    s_0 = sqrt((z * aD_c) ** 2 + w ** 2)

    sin_b_0 = t_0 / s_0
    cos_b_0 = w / s_0
    t_1 = z + c * E2 * sin_b_0 ** 3
    s_1 = sqrt(t_1 ** 2 + (w - a * e2 * cos_b_0 ** 3) ** 2)
    sin_p_1 = t_1 / s_1
    cos_p_1 = (w - a * e2 * cos_b_0 ** 3) / s_1
    r_n = a / sqrt(1 - e2 * sin_p_1 ** 2)

    if fabs(cos_p_1) >= cos(67.5 * (pi / 180)):
        ele = w / fabs(cos_p_1) - r_n
    else:
        ele = z / sin_p_1 + r_n * (e2 - 1)
    lat = atan(sin_p_1 / cos_p_1) * (180 / pi)
    lon = atan2(y, x) * (180 / pi)
    return lat, lon, ele


def time_label_to_datetime(t_label):
    """

    :param t_label: string like 'LDB0_A15:001:00450'
    :return: d_time
    """
    # t_label = 'LDB0_A15:001:00450'
    ts = t_label.split(':')
    year = str(20) + ts[0][-2:]
    doy = ts[1]
    sec = ts[2]
    # dt = doy_to_date(doy, year)
    # hhmmss = str(timedelta(seconds=int(sec)))
    my_date = doy_to_date(doy, year) + ' ' + str(timedelta(seconds=int(sec)))
    return my_date


def doy_to_date(doy, year):
    """
    :param doy: str 'yyyy'
    :param year: str 'xxx'
    :return:
    """
    d = int(doy)
    dt = datetime.strptime(year + "-" + doy, "%Y-%j").strftime("%Y-%m-%d")
    return dt


def datetime_to_timestamp(date_time):
    """

    :param date_time: type datetime (formatted "%Y-%m-%d %H:%M:%S")
    :return: unix_timestamp [s]
    """
    dts = date_time.strftime("%Y-%m-%d %H:%M:%S")
    date_format = datetime.strptime(dts, "%Y-%m-%d %H:%M:%S")
    return datetime.timestamp(date_format)


def remove_duplicate_site_names(fin_pathname1, fout_pathname):
    """

    :return:
    """
    fin = open(fin_pathname1, 'r')
    in_lines = fin.readlines()
    fin.close()
    in_sites = []
    for i in range(len(in_lines)):
        in_sites.append(in_lines[i].split()[0].lower())  # all to lowercase before searching for duplicates
    # get free of duplicate site-names
    uniq = []
    seen = set()
    for x in in_sites:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    unic = sorted(uniq)
    fo = open(fout_pathname, 'w')
    for i in range(len(uniq)):
        fo.write(uniq[i] + '\n')
    fo.close()


def is_number(nr_str):
    """

    :param nr_str:
    :return: boolean True if nr_str is float and False if not
    """
    try:
        float(nr_str)
        return True
    except ValueError:
        return False


def url_accessible(url):
    """
    Check if URL accessible. If Yes, return True, else return False
    :param url:
    :return: boolean
    """
    try:
        get = requests.get(url)
        if get.status_code == 200:
            return True
        else:
            return False
    except requests.exceptions.RequestException as e:
        print(f'{url}: is not reachable: {e}')


def line_starts_with(check_line, check_str):
    """
    For using in compare_logfile_rinex() for checking if the line in logfile starts with substring check_str
    :param check_line:
    :param check_str:
    :return: boolean True (if check_line starts with check_str)
    """
    chk_len = len(check_str)
    if not check_line.strip() == '' and check_line[:chk_len] == check_str:
        return True
    else:
        return False


def if_rinex_used_in_igs_repro3(year, doy, rinex_file_name):
    """
    For checking if the RINEX-file has been already used in any earlier IGS reanalysis performed by AC (COD and TUG)
    Assumption made: if the site has tropospheric product for YYYY and DOY then the RINEX must have been used.
    It can be foreseen that in the future there will be not only IGS repro3 for COD and TUG in the repository,
    but different reprocessed time series from different ACs (inside one network there should not be any duplicated
    site-names). Site detection by 4char site-name (both 4char and 9char filenames can exist in parallel in the same
    repository). In other repositories the site_names can be also lowercase.

    :param doy: int
    :param year: int
    :param rinex_file_name: string RINEX file name
    :return: [] of agencies
    """
    # Checking existence in COD and TUG extracted ZTDs /f_path/YYYY/DOY/COD/ and /f_path/YYYY/DOY/TUG/ only
    f_path = config.igs_repro3_ztd
    site_name = rinex_file_name[:4].upper()  # in repro3 ZTDs the site names are uppercase

    # get files' list from ZTDs by YYYY and DOY from COD and TUG
    try:
        cod_list = sorted(os.listdir(f_path + str(year) + '/' + str(doy).zfill(3) + '/' + 'COD/'))
    except FileNotFoundError:
        cod_list = []

    try:
        tug_list = sorted(os.listdir(f_path + str(year) + '/' + str(doy).zfill(3) + '/' + 'TUG/'))
    except FileNotFoundError:
        tug_list = []

    agencies = []
    if cod_list:
        for i in range(len(cod_list)):
            if site_name in cod_list[i][:4]:
                agencies.append('COD IGS-repro3')
                break
    if tug_list:
        for i in range(len(tug_list)):
            if site_name in tug_list[i][:4]:
                agencies.append('TUG IGS-repro3')
                break
    # print('agencies = ', agencies)
    return agencies


def if_rinex_used_in_epn_repro2(year, doy, rinex_file_name):
    """
    For checking if the RINEX-file has been already used in EPN-repro2

    :param doy: int
    :param year: int
    :param rinex_file_name: string RINEX file name
    :return: in_epn_repro2, Boolean (True, if in epn_repro2)
    """
    # Checking existence in COD and TUG extracted ZTDs /f_path/YYYY/DOY/ and /f_path/YYYY/DOY/
    f_path = config.epn_repro2_ztd
    site_name = rinex_file_name[:4].upper()  # in repro3 ZTDs the site names are uppercase
    # get files' list from ZTDs by YYYY and DOY
    try:
        epn_list = sorted(os.listdir(f_path + str(year) + '/' + str(doy).zfill(3) + '/'))
    except FileNotFoundError:
        epn_list = []

    in_epn_repro2 = False
    if epn_list:
        for i in range(len(epn_list)):
            if site_name in epn_list[i][:4]:
                in_epn_repro2 = True
                break
    return in_epn_repro2


def get_header_txt(f_path):
    """
    Reads rinex-logfile-comparing header as a text from a file from f_path
    :param f_path:
    :return: [] of header lines (strings)
    """
    f = open(config.rinex_logfile_header_file, 'r')
    lines = f.readlines()
    f.close()
    header_lines = []
    for i in range(len(lines)):
        header_lines.append(lines[i])
    return header_lines


def get_brdc_mixed_rinex3_cddis(year, doy, brdc_down_path):
    """
    Get BRDC from CDDIS for RINEX QC (Anubis)
    Only downloading and gunzip
    :param year:
    :param doy:
    :param brdc_down_path:  ../YYYY/DOY/
    :return:
    """

    # BRDC00IGS_R_20210030000_01D_MN.rnx in YYYY/brdc/BRDC00IGS_R_YYYYDDDHHMM_01D_MN.rnx.gz
    brdc_name = 'BRDC00IGS_R_' + str(year) + str(doy).zfill(3) + '0000_01D_MN.rnx.gz'
    remote_url = 'https://cddis.nasa.gov/archive/gnss/data/daily/' + str(year) + '/brdc/' + brdc_name

    got_file = False
    print(remote_url)

    # Add /brdc to have ephemeris separated from YYYY/DOY path
    brdc_path = brdc_down_path + 'brdc/'

    if not os.path.exists(brdc_path):
        os.makedirs(brdc_path)

    while got_file is False:
        try:
            r = requests.get(remote_url, timeout=120)
            with open(brdc_path + brdc_name, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=1000):
                    fd.write(chunk)
            fd.close()
            got_file = True
            print('      %s downloaded' % brdc_name)
            # unzip downloaded rinex for free version of ANUBIS!!
            print('      unzipping %s' % brdc_name)
            os.system('gunzip ' + brdc_path + brdc_name)
            break  # file downloaded

        except (requests.exceptions.Timeout, requests.exceptions.RequestException, urllib3.exceptions.SSLError,
                urllib3.exceptions.NewConnectionError) as ex:
            err_log.error(' %s - from get_brdc_mixed_rinex3_cddis(). Retrying in 10 seconds.' % ex)
            print(' %s - get_brdc_mixed_rinex3_cddis(). Retrying in 10 seconds. Current site to process %s' % (
                ex, brdc_name))
            time.sleep(10)  # increase the delay 10 --> 120 (for test)
            pass
        except Exception as ex:
            raise ex


def get_brdc_rinex2_cddis(year, doy, brdc_down_path):
    """
    Get BRDC from CDDIS for RINEX QC (for TEQC)
    Only downloading and gunzip
    :param year:
    :param doy:
    :param brdc_down_path:
    :return:

    Daily RINEX V2 GPS Broadcast Ephemeris Files
    The daily GPS broadcast ephemeris file is a merge of the individual site RINEX V2 navigation files into one,
    non-redundant file that can be utilized by users instead of the many individual navigation files.
    The starting directory for the daily files is:
    https://cddis.nasa.gov/archive/gnss/data/daily/
    WARNING! Note, for data created before December 1, 2020, the files are Unix compressed with extension .Z
    YYYY/brdc/brdcDDD0.YYn.gz   (merged GPS broadcast ephemeris file)
    """

    # Note, in CDDIS RINEX v2 daily BRDC created before December 1, 2020 are Unix compressed with extension .Z
    # REQUIRED: installation of ncompress !!!
    if (year >= 2020 and doy >= 336) or year > 2021:
        brdc_gps = 'brdc' + str(doy).zfill(3) + '0.' + str(year)[2:] + 'n.gz'
        brdc_glonass = 'brdc' + str(doy).zfill(3) + '0.' + str(year)[2:] + 'g.gz'
    else:
        brdc_gps = 'brdc' + str(doy).zfill(3) + '0.' + str(year)[2:] + 'n.Z'
        brdc_glonass = 'brdc' + str(doy).zfill(3) + '0.' + str(year)[2:] + 'g.Z'

    # Add /brdc to have ephemeris separated from YYYY/DOY path
    brdc_path = brdc_down_path + '/brdc/'

    if not os.path.exists(brdc_path):
        os.makedirs(brdc_path)

    cwd = os.getcwd()
    os.chdir(brdc_path)

    try:
        # for GPS first
        brdc_name = brdc_gps
        remote_url = 'https://cddis.nasa.gov/archive/gnss/data/daily/' + str(year) + '/brdc/' + brdc_name
        r = requests.get(remote_url, timeout=120)
        with open(brdc_path + brdc_name, 'wb') as fd:
            for chunk in r.iter_content(chunk_size=1000):
                fd.write(chunk)
        fd.close()
        got_file = True
        print('      %s downloaded' % brdc_name)
        # unzip downloaded rinex (TEQC doesn't like *.gz files)
        print('      unzipping %s' % brdc_name)
        os.system('gunzip ' + brdc_path + brdc_name)

        # the same for GLONASS
        brdc_name = brdc_glonass
        remote_url = 'https://cddis.nasa.gov/archive/gnss/data/daily/' + str(year) + '/brdc/' + brdc_name
        r = requests.get(remote_url, timeout=120)
        with open(brdc_path + brdc_name, 'wb') as fd:
            for chunk in r.iter_content(chunk_size=1000):
                fd.write(chunk)
        fd.close()
        got_file = True
        print('      %s downloaded' % brdc_name)
        # unzip downloaded rinex (TEQC doesn't like *.gz files)
        print('      unzipping %s' % brdc_name)
        if brdc_name[-2:] == 'gz':
            os.system('gunzip ' + brdc_path + brdc_name)
        else:
            os.system('uncompress ' + brdc_path + brdc_name)
        os.chdir(cwd)  # job done, back to cwd

    except (requests.exceptions.Timeout, requests.exceptions.RequestException, urllib3.exceptions.SSLError,
            urllib3.exceptions.NewConnectionError) as ex:
        err_log.error(' %s - from get_brdc_rinex2_cddis(). Retrying in 10 seconds.' % ex)
        print(
            ' %s - from get_brdc_rinex2_cddis(). Retrying in 10 seconds. Current site to process %s' % (ex, brdc_name))
        time.sleep(10)  # increase the delay 10 --> 120 (for test)
        pass
    except Exception as ex:
        raise ex


def url_accessible(url):
    """
    Check if URL accessible. If Yes, return True, else return False
    :param url:
    :return: boolean
    """
    try:
        get = requests.get(url)
        if get.status_code == 200:
            return True
        else:
            return False
    except requests.exceptions.RequestException as e:
        print(f'{url}: is not reachable: {e}')


def get_header_txt(f_path):
    """
    Reads rinex-logfile-comparing header as a text from a file from f_path
    :param f_path:
    :return: [] of header lines (strings)
    """
    f = open(config.rinex_logfile_header_file, 'r')
    lines = f.readlines()
    f.close()
    header_lines = []
    for i in range(len(lines)):
        header_lines.append(lines[i])
    return header_lines


def sirgas_get_site_list(country, year, doy):
    """

    :param doy:
    :param year:
    :param country: string country (uruguay, chile, ...)
    :return:
    """
    if country.lowercase(country) == 'chile':
        url = 'https://gnss.csn.uchile.cl/data/'
        pass
    elif country.lowercase(country) == 'uruguay':  # FTP only
        url_1 = 'ftp://pp.igm.gub.uy'  # port 21, Anonymous no pwd
        url_2 = 'sftp://sftp.igm.gub.uy'  # port 22, regna, pwd = historico
        pass
    elif country.lowercase(country) == 'sirgas_chile':
        url = 'https://www.sirgas.cl'  # requires registration and personal ID?
        pass
    elif country.lowercase(country) == 'ecuador':
        url = 'https://www.geoportaligm.gob.ec/downloads/public/estaciones/opcion2'  # gmail + pwd
        pass
    elif country.lowercase(country) == 'argentina':
        url = ''


def get_sirgas_logfile_list():
    """
    logfiles like ab2100usa_20240802.log
    from ftp://ftp.sirgas.org/pub/gps/DGF/station/log
    :return: [] of logfile names
    """
    url = 'ftp.sirgas.org'
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            with ftplib.FTP(url) as ftp:
                ftp.login()
                ftp.cwd('/pub/gps/DGF/station/log')
                f_list = ftp.nlst()
                ftp.close()
            return f_list

        except (ConnectionError, IOError) as ex:
            if attempt < max_attempts - 1:  # if it's not the final attempt
                err_log.error(' %s - from get_sirgas_logfile_list(). Retrying in 10 seconds...' % ex)
                time.sleep(30)  # wait for 30 seconds before retrying
                continue
            else:  # if it's the final attempt
                err_log.error(' %s - from get_sirgas_logfile_list(). No more retries left. '
                              'Aborting...' % ex)
                return None  # after max_attempts, the function gives up and returns None


def download_all_sirgas_logfiles(to_where):
    """

    :param to_where: string directory to where to download
    :return:
    """
    f_list = get_sirgas_logfile_list()

    url = 'ftp.sirgas.org'
    ftp = ftplib.FTP(url)
    ftp.login()
    ftp.cwd('/pub/gps/DGF/station/log')

    for f_name in f_list:
        if '.log' in f_name:
            fo = open(to_where + f_name, 'w+b')
            ftp.retrbinary('RETR %s' % f_name, fo.write)
    ftp.quit()


def get_sirgas_site_coordinates_from_logfiles(log_dir, out_dir):
    """

    :param out_dir: string path to output file 'sirgas_site_coordinates.txt'
    :param log_dir: string path to the logfiles
    :return:
    """
    # -rw-r--r--. 1 kr kr 12968 Nov 20 20:18 aacr00cri_20150504.log
    # -rw-r--r--. 1 kr kr 13363 Nov 20 20:18 ab2100usa_20240802.log
    cwd = os.getcwd()
    files = os.listdir(log_dir)
    fo = open('/Data/C3S2/SIRGAS_logfiles/sirgas_site_coordinates.txt', 'w')
    os.chdir(log_dir)
    for file in files:
        f_tmp = open(file, 'r', encoding='latin-1')
        ll = f_tmp.readlines()
        site_tmp = file[:4]
        c_code = file[6:9]
        # print(site_tmp)
        #        X coordinate (m)       :   644008.99
        #        Y coordinate (m)       : -6251064.27
        #        Z coordinate (m)       :  1093780.86
        try:
            for i in range(len(ll)):
                if 'X coordinate' in ll[i]:
                    x = float(ll[i].split(':')[-1])
                if 'Y coordinate' in ll[i]:
                    y = float(ll[i].split(':')[-1])
                if 'Z coordinate' in ll[i]:
                    z = float(ll[i].split(':')[-1])
                    break
            lat, lon, ele = cartesian2geodetic(x, y, z)
            w_str = site_tmp + ',' + c_code + ',' + str(lat) + ',' + str(lon) + ',' + str(ele) + '\n'
            fo.write(w_str)
        except ValueError as e:
            print('ValueError for site', site_tmp)
            e_str = site_tmp + ',' + c_code + ',' + 'ValueError' + '\n'
            fo.write(e_str)

    fo.close()
    os.chdir(cwd)
    print('Finished')


def get_sirgas_sites_not_in_unavco():
    """

    :return:
    """
    site_f = '/Data/C3S2/SIRGAS_logfiles/sirgas_site_coordinates.txt'

    f = open(site_f)  # sirgas
    lines_1 = f.readlines()
    f.close()

    sirgas_sites = []
    for i in range(len(lines_1)):
        sirgas_sites.append(lines_1[i][:4])

    list_unavco = process_unavco.f_list_unavco(config.unavco_logfiles_url, 'log.txt')  # get logfiles' list
    unavco_sites = []
    for i in range(len(list_unavco)):
        unavco_sites.append(list_unavco[i][:4])

    fo = open('/Data/C3S2/abi/sirgas_sites_not_in_unavco.txt', 'w')
    for i in range(len(sirgas_sites)):
        tmp_site = sirgas_sites[i]
        if tmp_site not in unavco_sites:
            fo.write(lines_1[i])
    fo.close()
    print('DONE')


def sirgas_sites_not_in_us_cors():
    """

    :return:
    """
    # UNAVCO sites_dates from https://geodesy.noaa.gov/CORS/dates_sites.txt
    # AA  AA  ARUBANETHARU2013      CN19   2021034   NULL      15     60  UNAVPS   Operational
    # AC  AC  BGGY__ANTIGUABGG      BGGY   2012266   NULL      15     60  UNAVPS   Operational
    # AC  AC  BARBUDAWBHCR2012      CN00   2012234   NULL      15   1440  UNAVPS   Non-Operational
    us_cors_file = '/Data/C3S2/abi/US_CORS_dates_sites.txt'  # 2912 sites (operational + decommissioned)
    # 2804 logfiles collected in /Data/C3S2/NOAA_US_CORS_logfiles
    # TODO: US_CORS like for SIRGAS
    #  bavc,bra,-40.80270245310875,-14.888312235076782,875.1814187346026, to get site coordinates


def us_cors_site_coordinates(f_path):
    """
    EXPERIMENTAL
    :param f_path: data file from https://geodesy.noaa.gov/CORS/dates_sites.txt, recorded in local file system
    :return:
    """
    log_dir = '/Data/C3S2/us_cors_logfiles/'

    fi = open(f_path, 'r', encoding='latin-1')
    lines = fi.readlines()
    fi.close()

    u_sites, u_sites_sorted = [], []
    for i in range(len(lines) - 1):
        # site names must be cut by positions, not by splitting !!!!
        tmp_site = lines[i][30:35]
        u_sites.append(tmp_site.lower())

    cwd = os.getcwd()
    files = sorted(os.listdir(log_dir))
    fo = open(log_dir + 'us_cors_site_coordinates.txt', 'w')
    os.chdir(log_dir)

    for file in files:
        try:
            f_tmp = open(file, 'r', encoding='latin-1')
            ll = f_tmp.readlines()
            for j in range(len(ll)):
                if 'Four Character ID        :' in ll[j]:
                    site_tmp = ll[j].split(':')[1].strip()
                if 'Country                  :' in ll[j]:
                    country = ll[j].split(':')[1].strip()  # Country                  : United States

                if 'X coordinate' in ll[j]:
                    x = float(ll[j].split(':')[-1])
                if 'Y coordinate' in ll[j]:
                    y = float(ll[j].split(':')[-1])
                if 'Z coordinate' in ll[j]:
                    z = float(ll[j].split(':')[-1])
                    break
            lat, lon, ele = cartesian2geodetic(x, y, z)
            w_str = site_tmp.lower() + ',' + country + ',' + str(lat) + ',' + str(lon) + ',' + str(ele) + '\n'
            fo.write(w_str)
        except ValueError as e:
            print('ValueError for site', site_tmp, file)
            e_str = site_tmp + ',' + country + ',' + 'ValueError' + '\n'
            fo.write(e_str)
    fo.close()
    os.chdir(cwd)
    print('DONE')


def get_logfile_us_cors_aws(s_name):
    """
    EXPERIMENTAL, for downloading a logfile from url by site name
    For getting us_cors logfiles from Amazon AWS.
    """
    down_path = '/Data/C3S2/us_cors_logfiles'
    if not os.path.exists(down_path):
        os.makedirs(down_path)

    cwd = os.getcwd()
    os.chdir(down_path)

    log_name = s_name.lower() + '.log.txt'
    url = 'https://noaa-cors-pds.s3.amazonaws.com/station_log/' + log_name

    retry_attempts = 5
    for attempt in range(retry_attempts):
        try:
            response = requests.get(url, timeout=120, stream=True)  # timeout values in seconds.
            response.raise_for_status()  # If response was successful, no Exception will be raised.
            break
        except requests.HTTPError as http_err:
            if http_err.response.status_code == 403:  # Access forbidden
                err_log.warning(f"Forbidden access to: {url}")
                os.chdir(cwd)
                return None
            err_log.error(f'HTTP error occurred: {http_err}')
        except requests.Timeout as timeout_err:
            err_log.error(f'Timeout error occurred: {timeout_err}')
        except requests.ConnectionError as conn_err:
            err_log.error(f'Connection error occurred: {conn_err}')
        except requests.RequestException as req_err:
            err_log.error(f'Other request error occurred: {req_err}')
        except Exception as ex:
            err_log.error(f'Unknown error occurred: {ex}')
        time.sleep(10)
    else:
        err_log.error(f' Could not download the file from {url} after {retry_attempts} attempts')
        os.chdir(cwd)
        return None

    with open(log_name, 'wb') as file:
        for chunk in response.iter_content(chunk_size=1024):
            file.write(chunk)

    try:
        with open(log_name, 'r', encoding='utf-8') as f_in:  # trying with utf-8
            r_lines = f_in.readlines()
        if 'key does not exist' in r_lines[1]:
            err_log.error(' Logfile does not exist for us_cors site ' + str(s_name))
            os.remove(log_name)
            os.chdir(cwd)
            return None
    except UnicodeDecodeError:
        try:
            with open(log_name, 'r', encoding='ISO-8859-1') as f_in:  # trying with latin1
                r_lines = f_in.readlines()
            if 'key does not exist' in r_lines[1]:
                err_log.error(' Logfile does not exist for us_cors site ' + str(s_name))
                os.remove(log_name)
                os.chdir(cwd)
                return None
        except UnicodeDecodeError as e:  # neither utf-8 and latin1 did work
            os.remove(log_name)
            err_log.warning(f" Cannot read {log_name}: {e}")
            os.chdir(cwd)
            return None

    # shutil.move(log_name, config.logfile_archive_path + log_name)
    os.chdir(cwd)
    return log_name


def get_all_logfiles_us_cors(to_where):
    """
    EXPERIMENTAL for downloading all us_cors logfiles found from https://geodesy.noaa.gov/CORS/dates_sites.txt
    :param to_where: string
    :return:
    """
    logfiles = download_us_cors.list_fd_uscors('https://geodesy.noaa.gov/corsdata/station_log/', '.txt')
    s_list = []
    for i in range(len(logfiles)):
        s_list.append(logfiles[i][:4])

    for site in s_list:
        get_logfile_us_cors_aws(site)
    print('done')
    print('DONE')


def get_all_logfiles_unavco(to_where):
    """
    EXPERIMENTAL
    :param to_where:
    :return:
    """
    f_list = process_unavco.f_list_unavco(config.unavco_logfiles_url, 'log.txt')  # logfile list
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

    for log_file in f_list:
        try:
            url = config.unavco_logfiles_url
            r = requests.get(url + '/' + log_file, headers={"authorization": f"Bearer {token}"}, timeout=60)
            if r.status_code == 403:  # Access forbidden
                url_log = url + log_file
                print('Forbidden access to ', url_log)
                err_log.error('Forbidden access to %s' % url_log)

            with open('/Data/C3S2/unavco_logfiles/' + log_file, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=1000):
                    fd.write(chunk)

        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            err_log.error(' %s - from get_logfiles_navco(). Retrying in 10 seconds.' % ex)
            time.sleep(10)
            return None
    print('UNAVCO logfiles downloaded to: ', to_where)


def unavco_site_coordinates(f_path):
    """
    EXPERIMENTAL find country and coordinates from logfiles, recording to txt-file. All logfiles initially downloaded
    to a local file system (with get_all_logfiles_unavco()
    :param f_path:  string to where to output
    :return:
    """

    # fi = open(f_path, 'r', encoding='latin-1')
    # lines = fi.readlines()
    # fi.close()

    # u_sites, u_sites_sorted = [], []
    # for i in range(len(lines) - 1):
    #    # site names must be cut by positions, not by splitting !!!!
    #    tmp_site = lines[i][30:35]
    #    u_sites.append(tmp_site.lower())

    cwd = os.getcwd()
    files = sorted(os.listdir(f_path))
    fo = open(f_path + 'unavco_site_coordinates.txt', 'w')
    os.chdir(f_path)

    for file in files:
        try:
            f_tmp = open(file, 'r', encoding='latin-1')
            ll = f_tmp.readlines()
            for j in range(len(ll)):
                if 'Four Character ID        :' in ll[j]:
                    site_tmp = ll[j].split(':')[1].strip()
                if 'Country                  :' in ll[j]:
                    country = ll[j].split(':')[1].strip()  # Country                  : United States

                if 'X coordinate' in ll[j]:
                    x = float(ll[j].split(':')[-1])
                if 'Y coordinate' in ll[j]:
                    y = float(ll[j].split(':')[-1])
                if 'Z coordinate' in ll[j]:
                    z = float(ll[j].split(':')[-1])
                    break
            lat, lon, ele = cartesian2geodetic(x, y, z)
            w_str = site_tmp.lower() + ',' + country + ',' + str(lat) + ',' + str(lon) + ',' + str(ele) + '\n'
            fo.write(w_str)
        except ValueError as e:
            print('ValueError for site', site_tmp, file)
            e_str = site_tmp + ',' + country + ',' + 'ValueError' + '\n'
            fo.write(e_str)
    fo.close()
    os.chdir(cwd)
    print('DONE')


def select_sites_in_area(lat1, lon1, lat2, lon2, site_coord_file, selected_sites_path, out_name):
    """
    EXPERIMENTAL
    :param lat1: float
    :param lon1: float
    :param lat2: float
    :param lon2: float
    :param site_coord_file: string
    :param selected_sites_path: string   output_file_path
    :param out_name: string out_file name
    :return:
    """

    fi = open(site_coord_file, 'r', encoding='latin-1')
    lines = fi.readlines()
    fi.close()

    fo = open(selected_sites_path + out_name, 'w')
    for i in range(len(lines)):
        try:
            sl = lines[i].split(',')
            site = sl[0]
            lat = float(sl[2])
            lon = float(sl[3])
            if (lat1 < lat < lat2) and (lon1 < lon < lon2):
                fo.write(lines[i])
        except ValueError as e:
            print('ValueError for site ', site)
    fo.close()
    print('DONE')


def find_extension_sites(primary_set, ext1, ext2, out_fpath):
    """
    EXPERIMENTAL
    Find additional sites not belonging to the primary set
    :param out_fpath: string path and file to where to write the output
    :param primary_set: string path and filename for primary set of sites
    :param ext1: string path and filename for the 1st extension set
    :param ext2: string path and filename for the 2nd extension set
    :return:
    """
    fi = open(primary_set, 'r', encoding='latin-1')
    pr_lines = fi.readlines()
    fi.close()
    fi = open(ext1, 'r', encoding='latin-1')
    ex1_lines = fi.readlines()
    fi.close()
    fi = open(ext2, 'r', encoding='latin-1')
    ex2_lines = fi.readlines()
    fi.close()

    fo = open(out_fpath, 'w')

    pr_sites, ext1_sites, ext2_sites = [], [], []
    for i in range(len(pr_lines)):
        pr_sites.append(pr_lines[i].split(',')[0])
    for i in range(len(ex1_lines)):
        ext1_sites.append(ex1_lines[i].split(',')[0])
    for i in range(len(ex2_lines)):
        ext2_sites.append(ex2_lines[i].split(',')[0])

    fo.write('========= From ext1 ============' + '\n')
    ext_1, ext_2 = [], []
    for i in range(len(ext1_sites)):
        if ext1_sites[i] not in pr_sites:
            ext_1.append(ext1_sites[i])
            fo.write(ex1_lines[i])

    # merge primary with ext1
    merged = pr_sites + ext_1
    fo.write('========= From ext2 ============' + '\n')
    for i in range(len(ext2_sites)):
        if ext2_sites[i] not in merged:
            ext_2.append(ext2_sites[i])
            fo.write(ex2_lines[i])

    fo.close()
    from_primary = len(pr_sites)
    ext_from_set1 = len(ext_1)
    ext_from_set2 = len(ext_2)
    total_number_sites = from_primary + ext_from_set1 + ext_from_set2
    print('DONE! total_number_of_sites, from_primary, ext_from_set1, ext_from_set2', total_number_sites, from_primary,
          ext_from_set1, ext_from_set2)


def plot_sites(fpath):
    """
    EXPERIMENTAL Output plot into fpath
    :param fpath: string filepath to site coordinate file
    :return:
    """
    fi = open(fpath, 'r', encoding='latin-1')
    lines = fi.readlines()
    fi.close()

    site_names, lats, lons = [], [], []
    for i in range(len(lines)):
        sl = lines[i].split(',')
        site_names.append(sl[0])
        lats.append(float(sl[2]))
        lons.append(float(sl[3]))

    # fig = plt.figure(figsize=(10, 5))
    ax = plt.axes(projection=ccrs.PlateCarree())

    # Add map features
    ax.add_feature(cfeature.LAND)
    ax.add_feature(cfeature.OCEAN)
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.BORDERS, linestyle=':')
    ax.add_feature(cfeature.LAKES, alpha=0.5)
    ax.add_feature(cfeature.RIVERS)

    # Plot the sites
    ax.scatter(lons, lats, color='red', s=3, transform=ccrs.PlateCarree(), label='Sites')

    # Set title and show the map
    ax.set_title('Site Locations from fpath %s' % fpath, fontsize=16)

    out_path = '/Data/C3S2/abi/'
    out_name = fpath.split('/')[-1]
    name = out_name.split('.')[0]
    output_file = out_path + name + '.png'
    plt.savefig(output_file, bbox_inches='tight', dpi=600)


def get_gps_week(year, month, day):
    """
    Calculate a number of gps-week from given date
    The GPS week started at midnight January 6, 1980
    :return: nr_of_gps_week, from where to find the data for a given date
    """
    epoch = date(1980, 1, 6)
    given_day = date(year, month, day)
    return int((given_day - epoch).days / 7)


def doy_to_date2(year, doy):
    """
    :param doy: integer
    :param year: integer
    :return: YYYY/MM/DD
    """
    sdoy = str(doy)
    syear = str(year)
    sdoy.rjust(3 + len(sdoy), '0')
    return datetime.strptime(syear + "-" + sdoy, "%Y-%j").strftime("%Y/%m/%d")


def get_gps_week_and_weekday(year, doy):
    """

    :param year: int
    :param doy: int
    :return: gps_week, day_of_week
    """
    md = doy_to_date2(str(year), str(doy))
    mds = md.split('/')
    yyyy = int(mds[0])
    mm = int(mds[1])
    dd = int(mds[2])
    # day of the week
    gd = datetime.strptime(md, '%Y/%m/%d')
    wd = (gd.weekday() + 1) % 7
    wk = get_gps_week(yyyy, mm, dd)
    return wk, wd


def scan_for_non_rinex(r_path, year, scan_non_rinex, scan_err_logs):
    """
    Find all files with an extension recursively
    for detecting non-RINEX files (i.e., files not endfing with .crx or .rnx and excluding .log and .txt)
    in GREP /RINEX directory
    Writing output to a file 'non_rinex_' + year + '.txt'
    :return:
    """
    out_fp_name = '/Data/C3S2/abi/' + 'non_rinex_in_RINEX_' + str(year) + '.txt'
    fo = open(out_fp_name, 'w')

    collected_errors_file = '/Data/C3S2/abi/' + 'collected_errors_' + str(year) + '.txt'
    fo_err = open(collected_errors_file, 'w')

    d_name = r_path + str(year) + '/'

    err_lines = []
    for (root, dirs, files) in os.walk(d_name):
        for file in files:
            if scan_non_rinex:
                if not (file.endswith('.crx') or file.endswith('.rnx') or file.endswith('.txt') or file.endswith(
                        '.log')):
                    print(file)
                    fo.write(f'{file}\n')

            if scan_err_logs:
                if file == 'daily_errors.log':
                    with open(root + '/' + file) as f_err:
                        tmp_err_lines = f_err.readlines()
                    for i in range(len(tmp_err_lines)):
                        if 'ERROR:' in tmp_err_lines[i]:
                            err_lines.append(tmp_err_lines[i])

    err_lines = sorted(err_lines)
    for i in range(len(err_lines)):
        fo_err.write(f'{err_lines[i]}')
    fo.close()
    fo_err.close()


def scan_for_non_rinex_mod(r_path, year, scan_non_rinex, scan_err_logs):
    """
    TODO: MODIFICATION for searcing sites with short site names in GREP /RINEX directory
      For example, for years 2001...2015 (already compressed to *.gz). Avoiding existing of non RINEX3 standard
      compressed RINEXes in daily /RINEX
    Find all files with an extension recursively
    for detecting non-RINEX files (i.e., files not endfing with .crx or .rnx and excluding .log and .txt)
    in GREP /RINEX directory
    Writing output to a file 'non_rinex_' + year + '.txt' TODO: rename non_rinex --> rubbish_*.txt
    :return:
    """
    out_fp_name = '/Data/C3S2/abi/' + 'non_rinex_in_RINEX_' + str(year) + '.txt'
    # fo = open(out_fp_name, 'w')

    collected_errors_file = '/Data/C3S2/abi/' + 'collected_errors_' + str(year) + '.txt'
    fo_err = open(collected_errors_file, 'w')

    d_name = r_path + str(year) + '/'

    def func(elem):
        return elem[4:7]

    err_lines = []
    rubbish_lines = []
    for (root, dirs, files) in os.walk(d_name):
        for file in files:
            if scan_non_rinex:
                # TODO: if file.gz and '_' not in file[:11] (in the first 11 positions of the filename, as known for
                #  long RINEX3 filenames' standard, then add the file into non_rinex_in_RINEX*.txt
                # =====
                if file.endswith('.gz'):
                    fh = file[:11]
                    if '_' in fh:
                        pass
                    else:
                        print(file + ' not RINEX3 name standard')
                        rubbish_lines.append(file)
                        # fo.write(f'{file}\n')
                # =====
                elif not (file.endswith('.crx') or file.endswith('.rnx') or file.endswith('.txt') or file.endswith(
                        '.log')):
                    print(file)
                    rubbish_lines.append(file)
                    # fo.write(f'{file}\n')

            if scan_err_logs:
                if file == 'daily_errors.log':
                    with open(root + '/' + file) as f_err:
                        tmp_err_lines = f_err.readlines()
                    for i in range(len(tmp_err_lines)):
                        if 'ERROR:' in tmp_err_lines[i]:
                            err_lines.append(tmp_err_lines[i])

    err_lines = sorted(err_lines)
    for i in range(len(err_lines)):
        fo_err.write(f'{err_lines[i]}')
    # ===
    sorted_rubbish_lines = sorted(rubbish_lines, key=func)
    # write rubbish into ao file
    with open(out_fp_name, 'w') as f:
        for line in sorted_rubbish_lines:
            f.write(f'{line}\n')
    # ===
    # fo.close()
    fo_err.close()


def rinex_version(f_path_name):
    """
    For checking if RINEX version before Anubis QC (Anubis doesn't accept RINEX v1 !!!)
    :param f_path_name:
    :return: str version number
    """
    f_in = open(f_path_name, 'r')
    lines = f_in.readlines()
    if ('RINEX VERS' in lines[0]) and ('OBSERVATION' in lines[0]):
        return lines[0][:10].lstrip().strip()
    else:
        return None


def rinex_version_from_lines(f_lines):
    """
    For checking if RINEX version before Anubis QC (Anubis doesn't accept RINEX v1 !!!)
    :param f_lines: [] of RINEX lines
    :return: str version number
    """
    if len(f_lines) == 0:
        err_log.warning(f'No RINEX version available.')
        return None
    else:
        if ('RINEX VERS' in f_lines[0]) and ('OBSERVATION' in f_lines[0]):
            return f_lines[0][:10].lstrip().strip()
        else:
            return None


def rinex_converted(f_path_name):
    """
    Checking if GFZ format converter used
    :param f_path_name:
    :return:
    """
    with open(f_path_name, 'r') as f:
        lines = f.readlines()
        if lines[2].startswith('gfzrnx-2.2.0') and lines[3].startswith('INITIAL_RINEX_VERSION'):
            return True


def read_log_file(path):
    """
    Open and read a log file.
    :param path: The path of the log file to be read.
    :return: A list of lines read from the log file.
    """
    try:
        with open(path, 'r') as l_file:
            return l_file.readlines()
    except UnicodeDecodeError:
        # err_log.warning(f' utf-8 decoding error, now trying with encoding=latin-1: {path}')
        try:
            with open(path, 'r', encoding='latin-1') as l_file:
                lines = l_file.readlines()
            return lines
        except UnicodeEncodeError:
            err_log.error(f' Could not read {path} using utf-8 nor latin-1')
            return None


def parse_logfile(f_path):
    """
    Parse an IGS site log file (.txt/.log) for C3S2_311_bis T.14 GREP inventory table.

    Returns {site_code: [identifier, site_name, startOfOperation, country,
                         pointOfContact_Organisation, pointOfContact_ContactName,
                         pointOfContact_MailAddress, dataCentre]}
    where site_code is the 4-char identifier (uppercase).

    TODO: take lat, lon from stn_table and calculate amsl for stationDescription,
          maybe long filename for identifier also?? !!! Do it independently!
    :param f_path:
    :return:
    """
    log_lines = read_log_file(f_path)

    # Locate section header line indices
    sec = {'site_id': 0, 'location': 0, 'contact': 0, 'responsible': 0, 'more_info': 0}
    for i, line in enumerate(log_lines):
        if 'Site Identification' in line:
            sec['site_id'] = i
        elif 'Site Location' in line:
            sec['location'] = i
        elif 'Point of Contact Agency' in line:
            sec['contact'] = i
        elif 'Responsible Agency' in line:
            sec['responsible'] = i
        elif 'More Information' in line:
            sec['more_info'] = i
            break

    def get_value(start, end, label, multiline=False):
        """Return the value of the first labeled field matching `label` in log_lines[start:end].
        Continuation lines (stripped lines starting with ':') are appended when multiline=True.
        """
        value = ''
        collecting = False
        for line in log_lines[start:end]:
            if not collecting:
                if label in line and ':' in line:
                    value = line.split(':', 1)[1].strip()
                    if not multiline:
                        break
                    collecting = True
            else:
                if line.strip().startswith(':'):
                    value += ' ' + line.split(':', 1)[1].strip()
                else:
                    break
        return value

    site_name   = get_value(sec['site_id'],   sec['location'],    'Site Name')
    identifier  = get_value(sec['site_id'],   sec['location'],    'Character ID').upper()
    start_year  = get_value(sec['site_id'],   sec['location'],    'Date Installed')[:4]
    country     = get_value(sec['location'],  sec['contact'],     'Country')
    org         = get_value(sec['contact'],   sec['responsible'], 'Agency',        multiline=True)
    contact     = get_value(sec['contact'],   sec['responsible'], 'Contact Name')
    email       = get_value(sec['contact'],   sec['responsible'], 'E-mail')
    data_centre = get_value(sec['more_info'], len(log_lines),     'Primary Data')

    site = identifier[:4]
    return {site: [identifier, site_name, start_year, country, org, contact, email, data_centre]}


def parse_logfile_xml(xml_file_name):
    """
    on example of process_geoscience_australia.params_fom_xml_log()
    Must extract
    # return {} with 4char site name and [identifier, startOfOperation, country, pointOfContact_Organisation,
    # pointOfContact_ContactName, pointOfContact_MailAddress, dataCentre]
    :param xml_file_name: path_and_filename
    :return:
    """
    # initiate the output parameters
    identifier, startOfOperation, country, pointOfContact_Organisation, pointOfContact_ContactName, \
        pointOfContact_MailAddress, dataCentre = '', '', '', '', '', '', ''

    try:
        if os.path.getsize(xml_file_name) == 0:
            err_log.error(' Logfile is empty: %s' % xml_file_name)
            return None
        # if file does not start with '<?xml version=' in first line, it is not an XML-file, reason whatever
        with open(xml_file_name) as x_file:
            first_line = x_file.readline()
            if '<?xml version=' not in first_line:
                err_log.error(' Not XML file: %s' % xml_file_name)
                return None
    except FileNotFoundError as e:
        err_log.error(' File %s not found in params_from_xml_log(), error: %s' % (xml_file_name, e))
        return None

    js = xml_to_json(xml_file_name)  # string-json
    dict_x = json.loads(js)  # string-json --> json

    s_log = dict_x.get('geo:GeodesyML').get('geo:siteLog')
    sid = s_log.get('geo:siteIdentification')
    stationDescription_site_name = sid.get('geo:SiteIdentification').get('geo:siteName')
    identifier = sid.get('geo:SiteIdentification').get('geo:fourCharacterID').upper()
    # site_name_long = sid.get('geo:SiteIdentification').get('geo:siteName')
    startOfOperation = (sid.get('geo:SiteIdentification').get('geo:dateInstalled') or '')[:4]

    own = s_log.get('geo:siteLocation')
    country = own.get('geo:SiteLocation').get('geo:countryCodeISO').get('@codeListValue')

    try:
        sown = s_log.get('geo:siteOwner')
        pointOfContact_Organisation = sown.get('gmd:CI_ResponsibleParty').get('gmd:organisationName'). \
            get('gco:CharacterString')
    except AttributeError as e:
        pointOfContact_Organisation = ''

    scont = s_log.get('geo:siteContact')  # can be either list or {}
    if isinstance(scont, list):
        pointOfContact_ContactName = scont[0].get('gmd:CI_ResponsibleParty').get('gmd:individualName'). \
            get('gco:CharacterString')
        pointOfContact_MailAddress = scont[0].get('gmd:CI_ResponsibleParty').get('gmd:contactInfo').get(
            'gmd:CI_Contact'). \
            get('gmd:address').get('gmd:CI_Address').get('gmd:electronicMailAddress').get('gco:CharacterString')
    else:
        try:
            pointOfContact_ContactName = scont.get('gmd:CI_ResponsibleParty').get('gmd:individualName'). \
                get('gco:CharacterString')
            pointOfContact_MailAddress = scont.get('gmd:CI_ResponsibleParty').get('gmd:contactInfo').get('gmd:CI_Contact'). \
                get('gmd:address').get('gmd:CI_Address').get('gmd:electronicMailAddress').get('gco:CharacterString')
        except AttributeError as e:
            pointOfContact_ContactName = ''
            pointOfContact_MailAddress = ''

    # TODO: from where to get "agency" fronm GeodesyML???
    from_log_xml = {identifier: [identifier, stationDescription_site_name, startOfOperation, country,
                                 pointOfContact_Organisation, pointOfContact_ContactName, pointOfContact_MailAddress,
                                 dataCentre]}
    return from_log_xml


def xml_to_json(xml_file_name):
    """
    :param xml_file_name:
    :return: json_doc
    """
    with open(xml_file_name) as fd:
        doc = xmltodict.parse(fd.read())
    # print()
    # return json.dumps(doc, indent=4)  # readable result (string)
    return json.dumps(doc)


def extract_lat_lon_elev_network(f_path_stn_table, f_path_output):
    """
    Extract lat, lon, elev, 9char_s_name, 3char_country
    If 9char sitename is '', then use 4char site-name (for sites where long filename conversion failed
    00NA,AUS,-12.46664178,130.84398483,106.284,-4073663.0128,4712066.0117,-1367875.0164,00NA00AUS,00NA_2024-09-07_log.xml,2024-09-07 00:00:00,auspos
    :param f_path_output:
    :param f_path_stn_table:
    :param stn_table:
    :return:
    """
    f_out = open(f_path_output, 'w')
    with open(f_path_stn_table, 'r') as f_in:
        in_lines = f_in.readlines()
    for i in range(1, len(in_lines)):
        sl = in_lines[i].split(',')
        s_name = ''
        # if lon >180 deg, then lon = lon -360 for EGM2008
        if float(sl[3]) > 180.0:
            sl[3] = str(float(sl[3]) - 360)
        if sl[8] == '':
            s_name = sl[0]
        else:
            s_name = sl[8]
        tmp_line = sl[2] + ' ' + sl[3] + ' ' + sl[4] + ' ' + s_name + ' ' + sl[1] + ' ' + sl[11]
        f_out.write(tmp_line)
    f_out.close()
    print(f'extracted data in {f_path_output}')


def swap_elev_to_amsl(in_file_extracted, in_file_with_amsl, out_fpath):
    """
    swaps elev in extracted stn_table file with amsl calculated with EGM2008
    :param in_file_with_amsl:
    :param in_file_extracted:
    :param out_fpath:
    :param in_file:
    :return:
    """
    f_out = open(out_fpath, 'w')
    with open(in_file_extracted, 'r') as f_in1:
        in_lines_extracted = f_in1.readlines()
    with open(in_file_with_amsl, 'r') as f_in2:
        lines_with_amsl = f_in2.readlines()
    #  -22.817870  316.693736     -5.574
    #   -12.466642  130.843985     51.044

    # -22.817870056 316.693736382 8.922 0001 BRA
    # -12.46664178 130.84398483 106.284 00NA00AUS AUS auspos
    for i in range(len(in_lines_extracted)):
        sl1 = in_lines_extracted[i].split()
        sl2 = lines_with_amsl[i].split()
        if len(sl1) < 6:  # missing original data network
            empty_network = ','
            # amsl = ellips - geoid
            amsl = str(float(sl1[2]) - float(sl2[2]))
            tmp_line = sl1[0] + ',' + sl1[1] + ',' + amsl + ',' + sl1[3] + ',' + sl1[4] + empty_network
        else:
            # amsl = ellips - geoid
            amsl = str(float(sl1[2]) - float(sl2[2]))
            tmp_line = sl1[0] + ',' + sl1[1] + ',' + amsl + ',' + sl1[3] + ',' + sl1[4] + ',' + sl1[5]
        f_out.write(tmp_line + '\n')
    f_out.close()
    print(f'extracted info with amsl in {out_fpath}')


def calculate_amsl(f_input):
    """
    Calculate amsl for sites in GREP stn_table:
    INPUT file must be converted to format (lat, lon, elev, sitename)
    38.33892  359.51877   61.20320 ALAC
    39.47887  353.65822  436.70810 CACE
    from
    site_name,country_code,lat,lon,elev,x,y,z,site_name_9char,latest_log_name,latest_log_download_dt,latest_log_source
    0001,BRA,-22.817870056,316.693736382,8.922,4280295.1878,-4034429.6843,-2458144.1097,,,,
    00NA,AUS,-12.46664178,130.84398483,106.284,-4073663.0128,4712066.0117,-1367875.0164,00NA00AUS,00NA_2024-09-07_log.xml,2024-09-07 00:00:00,auspos
    01NA,AUS,-12.478222495,130.982047895,105.1472,-4084823.3937,4702026.4373,-1369125.6706,01NA00AUS,01NA_2024-09-07_log.xml,2024-09-07 00:00:00,auspos
    OUTPUT file
    38.338920  359.518770     50.460
    39.478870  353.658220     54.716
    :param f_input:
    :return: {} of (s_name: [lat, lon, amsl, from_network])
    """
    pass
    current_dir = os.getcwd()  # get current working directory

    # print('current dir: ', os.getcwd())
    #    os.rename(config.main_path + 'sites_to_merge.txt', config.egm_path + 'INPUT.DAT')
    shutil.copy(f_input, config.egm_path + 'INPUT.DAT')

    os.chdir(config.egm_path)  # geoid model is installed to here
    cmd = './interp_1min INPUT.DAT'  # it stays hard-coded, this must be executed in egm-directory with its grid-file
    os.system(cmd)

    # copy result back
    shutil.copy('OUTPUT.DAT',
                '/media/hannes/suurketas/BARON/VM_inventory_table/' + 'OUTPUT.DAT')

    os.chdir(current_dir)  # back to working directory


def extract_metadata_from_logfiles(path_to_logfiles):
    """
    Columns (parameter names to extract) to fill:
    identifier, description, Dataset, pointOfContact_Organisation, pointOfContact_ContactName,
    pointOfContact_Position, pointOfContact_MailAddress, principalInvestigator_Name, principalInvestigator_MailAddress,
    principalInvestigator_OnlineResource, revisionDate, creationDate, metadataStandard,
    alternativeMetadataReference_Title, alternativeMetadataReference_OnlineResource, referenceSystem,
    dataIdentification, abstract, purpose, originator_Organisation, originator_Name, originator_Position,
    originator_MailAddress, topicCategory, stationDescription, longitude, latitude, startOfOperation,
    extent_MinimumValue, extent_MaximumValue, maintenanceAndUpdateFrequency, dataCentre, discipline, instrument,
    product, platform, temporal, featureType, accessConstraints, useConstraints, otherConstraints, LanguageCode,
    characterEncoding

    Combined value for stationDescription -- Onsala COUNTRY:Sweden LAT:xx.xx LONG:yy.yy HEIGHT:zzz amsl

    :param path_to_logfiles:
    :return:
    """
    # CONFIGURABLE parameters ####################################
    fpath_to_stn_table = '/media/hannes/suurketas/BARON/grep_merged/stns/stn_table_VM_20260504.csv'
    work_dir = '/media/hannes/suurketas/BARON/VM_inventory_table/'
    # END CONFIGURABLE parameters ################################

    # DEFAULT VALUES according to the example table:
    defaults = {
        'descriptionDataset': 'GREP',
        'pointOfContact_Position': 0,
        'principalInvestigator_Name': 0,
        'principalInvestigator_MailAddress': 0,
        'principalInvestigator_OnlineResource': 0,
        'revisionDate': 0, 'creationDate': 0, 'metadataStandard': 'ISO 19115-3',
        'alternativeMetadataReference_Title': 0,
        'alternativeMetadataReference_OnlineResource': 0, 'referenceSystem': 'wgs1984', 'dataIdentification': 0,
        'abstract': 0, 'purpose': 'For Copernicus GREP', 'originator_Organisation': 0, 'originator_Name': 0,
        'originator_Position': 0, 'originator_MailAddress': 0, 'topicCategory': 'climatology',
        # stationDescription NOT DEFAULT
        # longitude NOT DEFAULT
        # latitude NOT DEFAULT
        'extent_MinimumValue': 'point', 'extent_MaximumValue': 'point', 'maintenanceAndUpdateFrequency': 'asNeeded',
        # dataCentre NOT DEFAULT
        'discipline': 'Surface based climatology and meteorology', 'instrument': 0,
        'product': 'GNSS observational data',
        'platform': 'land station', 'temporal': 'sub_daily', 'featureType': 0, 'accessConstraints': 'Open',
        'useConstraints': 'Open', 'otherConstraints': 'Open', 'LanguageCode': 'EN', 'characterEncoding': 'UTF-16'
    }

    columns = ['identifier', 'descriptionDataset', 'pointOfContact_Organisation', 'pointOfContact_ContactName',
               'pointOfContact_Position', 'pointOfContact_MailAddress', 'principalInvestigator_Name',
               'principalInvestigator_MailAddress', 'principalInvestigator_OnlineResource',
               'revisionDate', 'creationDate', 'metadataStandard',
               'alternativeMetadataReference_Title', 'alternativeMetadataReference_OnlineResource',
               'referenceSystem', 'dataIdentification', 'abstract', 'purpose',
               'originator_Organisation', 'originator_Name', 'originator_Position', 'originator_MailAddress',
               'topicCategory', 'stationDescription', 'longitude', 'latitude', 'startOfOperation',
               'extent_MinimumValue', 'extent_MaximumValue', 'maintenanceAndUpdateFrequency', 'dataCentre',
               'discipline', 'instrument', 'product', 'platform', 'temporal', 'featureType',
               'accessConstraints', 'useConstraints', 'otherConstraints', 'LanguageCode', 'characterEncoding']

    # for debugging --> True
    debug = False
    if not debug:
        # extract data from stn_table for calculating amsl
        extract_lat_lon_elev_network(fpath_to_stn_table, work_dir + 'INPUT')
        calculate_amsl(work_dir + 'INPUT')
        swap_elev_to_amsl(work_dir + 'INPUT', work_dir + 'OUTPUT.DAT', work_dir + 'stn_table_extracted_parameters.csv')

    # get lines from stn_table and all existing site names
    # In case of multiple logfiles for the same site, take the "first" as for T1.4 we need startOfOperation only
    with open(work_dir + 'stn_table_extracted_parameters.csv', 'r') as fs:
        stn_lines = fs.readlines()
    sites = sorted([line.split(',')[3][:4] for line in stn_lines])

    rows = []
    for i, site in enumerate(sites):
        ssl = stn_lines[i].split(',')

        # Find logfile — try uppercase then lowercase; logfile names can be either case
        log_files = glob.glob(path_to_logfiles + site.upper() + '*')
        if not log_files:
            log_files = glob.glob(path_to_logfiles + site.lower() + '*')

        from_log = {}
        log_data = None
        if log_files:
            site_fpath = log_files[0]
            log_site_name = os.path.basename(site_fpath)[:4].upper()
            if site_fpath.endswith('.xml'):
                from_log = parse_logfile_xml(site_fpath)
            elif site_fpath.endswith('.txt') or site_fpath.endswith('.log'):
                from_log = parse_logfile(site_fpath)
            # from_log = {identifier: [identifier, stationDescription_site_name, startOfOperation, country,
            #                          pointOfContact_Organisation, pointOfContact_ContactName,
            #                          pointOfContact_MailAddress, dataCentre]}
            if from_log:
                log_data = from_log.get(log_site_name)
            # else: parse failed (empty/invalid file) — log_data stays None, row uses ssl values

        stationDescription_name = log_data[1] if log_data else ssl[3].upper()
        stationDescription_comb = (
            f"{stationDescription_name} COUNTRY:{ssl[4].strip()} "
            f"LAT:{float(ssl[0]):.2f} LON:{float(ssl[1]):.2f} HEIGHT:{float(ssl[2]):.2f} amsl"
        )

        row = {**defaults,
               'identifier': ssl[3],
               'pointOfContact_Organisation': log_data[4] if log_data else 0,
               'pointOfContact_ContactName': log_data[5] if log_data else 0,
               'pointOfContact_MailAddress': log_data[6] if log_data else 0,
               'stationDescription': stationDescription_comb,
               'longitude': ssl[1],
               'latitude': ssl[0],
               'startOfOperation': log_data[2] if log_data else 0,
               'dataCentre': log_data[7] if log_data else ssl[5],
               }
        rows.append(row)

    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(work_dir + 't14.xlsx', index=False)
