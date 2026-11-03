import os.path
import shutil
import unlzw3
import gzip
import re
import subprocess
from zipfile import ZipFile, BadZipfile
from datetime import datetime
import config
from dbio import shared_funcs
from t_box import tools
from process import process_geoscience_australia
import logging.handlers

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def get_rinex_dir(year, doy, rinex_archive_path):
    """
    Function to construct a RINEX file path based on the year, day of year, and a base RINEX archive path.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :param rinex_archive_path: The base path of the RINEX archive.
    :return: The constructed RINEX file path.
    """
    return os.path.join(rinex_archive_path, str(year), str(doy).zfill(3))


def decode_data(data):
    """
    Function to decode a list of byte lines into strings, using UTF-8 and falling back to latin-1 on decode errors.
    :param data: List of byte lines to be decoded.
    :return: List of decoded strings.
    """
    decoded_data = []
    for line in data:
        try:
            decoded_data.append(line.decode('utf-8'))
        except UnicodeDecodeError:
            decoded_data.append(line.decode('latin-1'))
    return decoded_data


def check_string_for_dt(log_line, log_filename, proc_year):
    """
    Function to extract and validate a datetime string in the format '%Y-%m-%dT%H:%MZ' from a logfile line
    (e.g. 'Date Installed'). Date-only values get 'T00:00Z' appended; for years before the split year, month
    abbreviations like '01-JAN-1991' are also converted.
    :param log_line: The logfile line to be checked for a datetime string.
    :param log_filename: The filename of the logfile (used for warning messages).
    :param proc_year: The processing year, compared with config.proc_split_year to select the parsing logic.
    :return: The datetime string if found and valid, otherwise False. For years >= split year, the unchanged
        log_line is returned if it contains a placeholder ('CCYY' or 'unknown').
    """

    if proc_year >= config.proc_split_year:
        if 'CCYY' not in log_line and 'unknown' not in log_line:
            try:
                dt_string = log_line.split(':')[1].strip() + ':' + log_line.split(':')[2].strip()
                try:
                    datetime.strptime(dt_string, '%Y-%m-%dT%H:%MZ')
                except ValueError:
                    err_log.warning(f' Could not parse datetime string {dt_string} from {log_filename} '
                                    f'using point for splitting datetime string. Trying to use both point and colon...')
                    dt_string = re.split(':|\.', log_line)[1].strip() + ':' + re.split(':|\.', log_line)[2].strip()
                    try:
                        datetime.strptime(dt_string, '%Y-%m-%dT%H:%MZ')
                    except ValueError:
                        err_log.warning(f' Could not parse datetime string {dt_string} from {log_filename} '
                                        f'using both point and colon for splitting datetime string')
                        return False

            except IndexError as e:
                dt_string = log_line.split(':')[1].strip() + 'T00:00Z'  # date time T00:00Z
                try:
                    datetime.strptime(dt_string, '%Y-%m-%dT%H:%MZ')
                except ValueError:
                    err_log.warning(f' Could not parse datetime string {dt_string} from {log_filename} '
                                    f'using point for splitting datetime string. Trying to use both point and colon...')
                    dt_string = re.split(':|\.', log_line)[1].strip() + 'T00:00Z'
                    try:
                        datetime.strptime(dt_string, '%Y-%m-%dT%H:%MZ')
                    except ValueError:
                        err_log.warning(f' Could not parse datetime string {dt_string} from {log_filename} '
                                        f'using both point and colon for splitting datetime string')
                        return False
            return dt_string
        else:
            return log_line
    else:
        if 'CCYY' not in log_line and 'dd-MMM' not in log_line and 'unknown' not in log_line:
            try:
                sl = log_line.split('-')
                if not sl[1].isdigit():  # if not a number
                    month_abbr = {
                        "JAN": "01",
                        "FEB": "02",
                        "MAR": "03",
                        "APR": "04",
                        "MAY": "05",
                        "JUN": "06",
                        "JUL": "07",
                        "AUG": "08",
                        "SEP": "09",
                        "OCT": "10",
                        "NOV": "11",
                        "DEC": "12"
                    }
                    month_str = sl[1].upper().strip()
                    mon_nr_str = month_abbr.get(month_str)
                    sld = log_line.split()
                    y_str = sld[3].split('-')[2]
                    dt_string = y_str + '-' + mon_nr_str + '-' + sl[0][-2:] + 'T00:00Z'
                    return dt_string

                else:
                    dt_string = log_line.split(':')[1].strip() + ':' + log_line.split(':')[2].strip()
                    try:
                        datetime.strptime(dt_string, '%Y-%m-%dT%H:%MZ')
                    except ValueError:
                        err_log.warning(f' Could not parse datetime string {dt_string} from {log_filename} '
                                        f'using point for splitting datetime string. Trying to use both point and colon...')
                        dt_string = re.split(':|\.', log_line)[1].strip() + ':' + re.split(':|\.', log_line)[2].strip()
                        try:
                            datetime.strptime(dt_string, '%Y-%m-%dT%H:%MZ')
                        except ValueError:
                            err_log.warning(f' Could not parse datetime string {dt_string} from {log_filename} '
                                            f'using both point and colon for splitting datetime string')
                            return False

            except IndexError as e:
                dt_string = log_line.split(':')[1].strip() + 'T00:00Z'  # date time T00:00Z
                try:
                    datetime.strptime(dt_string, '%Y-%m-%dT%H:%MZ')
                except ValueError:
                    err_log.warning(f' Could not parse datetime string {dt_string} from {log_filename} '
                                    f'using point for splitting datetime string. Trying to use both point and colon...')
                    dt_string = re.split(':|\.', log_line)[1].strip() + 'T00:00Z'
                    try:
                        datetime.strptime(dt_string, '%Y-%m-%dT%H:%MZ')
                    except ValueError:
                        err_log.warning(f' Could not parse datetime string {dt_string} from {log_filename} '
                                        f'using both point and colon for splitting datetime string')
                        return False
            return dt_string
        else:
            # return log_line
            return False


def read_log_file(path):
    """
    Function to read a logfile, using the default encoding and falling back to latin-1 on decode errors.
    :param path: The path of the logfile to be read.
    :return: A list of lines read from the logfile, or None if it could not be read.
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


def readlines_zipped(full_rinex_path, get_only_path=False):
    """
    Function to unpack a RINEX file (*.gz, *.Z or *.zip) in place and read its lines; already unpacked files are
    read directly. The unpacked file is needed for long filename generation and the Anubis (free version) check.
    Note: gunzip replaces the compressed file; for *.zip the observation file is extracted and the zip deleted.
    :param full_rinex_path: The full path of the (compressed) RINEX file.
    :param get_only_path: If True, suppresses error logging for decoding and corrupted file errors.
    :return: A tuple (list of RINEX lines, unpacked RINEX filename), or (None, None) on failure.
    """
    f_rinex = os.path.basename(full_rinex_path)
    r_path = os.path.dirname(full_rinex_path) + '/'

    ends_with = f_rinex.split('.')[-1]

    rinex_lines = None
    unzipped_fn = None

    try:
        if ends_with == 'gz':
            result = subprocess.run(['gunzip', '-f', full_rinex_path], check=True)
            unzipped_fp = r_path + f_rinex[:-3]
            with open(unzipped_fp) as rfi:  # file ends with 'gz'
                rinex_lines = rfi.readlines()
            unzipped_fn = os.path.basename(unzipped_fp)
        elif ends_with == 'Z':
            result = subprocess.run(['gunzip', '-f', full_rinex_path], check=True)
            unzipped_fp = r_path + f_rinex[:-2]
            with open(unzipped_fp) as rfi:  # file ends with 'Z'
                rinex_lines = rfi.readlines()
            unzipped_fn = os.path.basename(unzipped_fp)
        elif ends_with == 'zip':
            with ZipFile(full_rinex_path, 'r') as zipf:
                file_inside_zip = None
                # Loop through the filenames in the zip looking for one ending in 'o'
                for filename in zipf.namelist():
                    if filename.endswith('d') or filename.endswith('D') or filename.endswith('O') or \
                            filename.endswith('o'):
                        # if filename.endswith('o'):  # PREVIOUS APPROACH
                        file_inside_zip = filename
                        break
                # If we found a file ending in 'o'
                if file_inside_zip is not None:
                    # Determine the directory of the unzipped file
                    unzip_dir = os.path.dirname(full_rinex_path)
                    # Extract the 'o' file into the unzipped directory
                    unzipped_fp = zipf.extract(file_inside_zip, path=unzip_dir)
                    # Read the file as string lines
                    with open(unzipped_fp, 'r', encoding='utf-8', errors='replace') as rfi:
                        rinex_lines = rfi.readlines()
                else:
                    err_log.warning(f' Did not find file with suitable file ending in {f_rinex}')
                    return None, None
            # Once done with the extracted file, remove it
            os.remove(full_rinex_path)
            unzipped_fn = os.path.basename(unzipped_fp)

        else:  # file is already unzipped
            unzipped_fp = r_path + f_rinex
            with open(unzipped_fp) as rfi:
                rinex_lines = rfi.readlines()
            unzipped_fn = f_rinex
            pass  # it is already unzipped, do nothing

    except UnicodeDecodeError:
        # try with latin1
        try:
            if ends_with == 'gz':
                unzipped_fp = r_path + f_rinex[:-3]
                err_log.info(' UnicodeDecodeError while reading RINEX %s' % f_rinex[:-3])
                with open(unzipped_fp, encoding='latin1', errors='replace') as rfi:
                    rinex_lines = rfi.readlines()
            elif ends_with == 'Z':
                unzipped_fp = r_path + f_rinex[:-2]
                err_log.info(' UnicodeDecodeError while reading RINEX %s' % f_rinex[:-2])
                with open(unzipped_fp, encoding='latin1', errors='replace') as rfi:
                    rinex_lines = rfi.readlines()
            else:
                unzipped_fp = r_path + f_rinex
                err_log.info(' UnicodeDecodeError while reading RINEX %s' % f_rinex)
                with open(unzipped_fp, encoding='latin1', errors='replace') as rfi:
                    rinex_lines = rfi.readlines()
            unzipped_fn = os.path.basename(unzipped_fp)

        except UnicodeDecodeError:
            if not get_only_path:
                err_log.error(' UnicodeDecodeError appeared for both latin1 and utf-8 while reading RINEX %s' % f_rinex)
            return None, None

    except (OSError, ValueError) as e:
        if not get_only_path:
            err_log.error(' Corrupted file %s, cannot unzip: %s' % (f_rinex, e))
        return None, None

    except BadZipfile as e:
        err_log.error(' Corrupted file %s, cannot unzip, BadZipfile error: %s' % (f_rinex, e))

    except subprocess.CalledProcessError as e:
        err_log.error(' Corrupted file %s, cannot unzip, subprocess.CalledProcessError: %s' % (f_rinex, e))

    # cmd = 'gzip ' + f_rinex[:-3]
    # os.system(cmd)
    # os.chdir(cur_dir)

    return rinex_lines, unzipped_fn


def move_rinex_to_err_dir(year, doy, unzipped_rinex_fn):
    """
    Function to move an unpacked RINEX file from the daily RINEX archive to the YYYY/DOY folder of the erroneous
    files archive (config.rinex_xyz_err_archive_path), creating it if needed. If the file is already present
    there, the source file is deleted instead.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :param unzipped_rinex_fn: The filename of the unpacked RINEX file.
    :return: None.
    """
    r_path = get_rinex_dir(year, doy, config.rinex_archive_path)
    unzipped_rinex_path = os.path.join(r_path, unzipped_rinex_fn)

    r_xyz_err_dir = get_rinex_dir(year, doy, config.rinex_xyz_err_archive_path)

    if not os.path.exists(r_xyz_err_dir):  # create a YYYY/DOY folder for erroneous files, if needed
        os.makedirs(r_xyz_err_dir)

    if unzipped_rinex_path:  # move unzipped file
        dest_rinex_path = os.path.join(r_xyz_err_dir, os.path.basename(unzipped_rinex_path))
        if not os.path.exists(dest_rinex_path):  # move unzipped RINEX to r_xyz_err_dir, if not present already
            shutil.move(unzipped_rinex_path, r_xyz_err_dir)
            err_log.info(f' {unzipped_rinex_path} moved to {r_xyz_err_dir}')
        # delete unzipped_rinex_path if it exists
        if os.path.exists(unzipped_rinex_path):
            os.remove(unzipped_rinex_path)
            err_log.info(f' {unzipped_rinex_path} deleted, the unzipped file already present in {r_xyz_err_dir}')


def prepare_log_inf(f_rinex, stn_df, year, doy, network):
    """
    Function to find the existing logfile for a RINEX file or download a new one.
    :param f_rinex: The long RINEX filename (starting with the 9-character site identification).
    :param stn_df: The station DataFrame used for looking up the logfile.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :param network: The network name.
    :return: A tuple (logfile name, logfile download datetime, 9-character site name, logfile source).
    """
    # site_name_9char = f_rinex.upper().split("_")[0]  # does not work for 4char site name 'RVO_'
    site_name_9char = f_rinex.upper()[:9]
    site_name_4char = f_rinex.upper()[:4]
    log_file, log_download_dt, log_source = shared_funcs.load_or_download_log_file(site_name_4char, site_name_9char,
                                                                                   stn_df, year, doy,
                                                                                   network)
    return log_file, log_download_dt, site_name_9char, log_source


def extract_header_inf_after_splityear(year, doy, f_rinex):
    """
    Function to unpack a RINEX file and extract GNSS metadata (receiver, antenna, approx. XYZ, antenna deltas,
    first epoch, lat/lon/ele) from its header, for years >= config.proc_split_year.
    Note: invalid files are deleted or moved to the erroneous files archive.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :param f_rinex: The RINEX filename (like abpo0010.22o).
    :return: A tuple (header_inf dict, list of error codes, list of reprocessing campaigns using the file,
        unpacked RINEX path), or (None, [], None, None) on failure.
    """

    try:
        header_inf = {}

        used_by = tools.if_rinex_used_in_igs_repro3(year, doy, f_rinex)
        if tools.if_rinex_used_in_epn_repro2(year, doy, f_rinex):
            used_by.append('EPN_repro2')

        r_path = get_rinex_dir(year, doy, config.rinex_archive_path)
        full_rinex_path = os.path.join(r_path, f_rinex)

        rinex_lines, unzipped_rinex_fn = readlines_zipped(full_rinex_path)  # get the RINEX lines

        if not rinex_lines:
            move_rinex_to_err_dir(year, doy, f_rinex)
            return None, [], None, None
        else:
            unzipped_rinex_path = os.path.join(r_path, unzipped_rinex_fn)

        if 'RINEX' not in rinex_lines[0] or 'TYPE' not in rinex_lines[0]:
            os.remove(unzipped_rinex_path)  # delete the file
            err_log.warning(f' {unzipped_rinex_path} deleted - the first line does not contain "RINEX" and "TYPE"')
            return None, [], None, None

        if shared_funcs.dos_line_endings(unzipped_rinex_path):
            shared_funcs.dos2unix(unzipped_rinex_path)

        h_lines = []
        for line in rinex_lines:
            h_lines.append(line)
            if 'END OF HEADER' in line:
                break

        # define header_inf keys
        keys = [
            "h_receiver", "h_serial", "h_receiver_firmware",
            "h_antenna", "h_antenna_serial", "h_radome",
            "h_x", "h_y", "h_z", "h_h", "h_e", "h_n"
        ]
        # assign keys to the dictionary with empty string values
        for key in keys:
            header_inf[key] = ''

        try:
            # it must be checked, whether the "key" is in the last 20-25 positions (i.e., at the end of the line)
            for line in h_lines:
                if ('REC #' in line[-25:]) and ('TYPE' in line[-25:]):
                    header_inf['h_serial'] = line[:20].strip()
                    header_inf['h_receiver'] = line[20:40].strip()
                    header_inf['h_receiver_firmware'] = line[40:60].strip()
                elif ('ANT #' in line[-25:]) and ('TYPE' in line[-25:]):
                    sl = line.split()
                    header_inf['h_antenna_serial'] = sl[0].strip()
                    header_inf['h_antenna'] = sl[1].split()[0].strip()
                    try:
                        if not sl[2] == 'ANT':
                            header_inf['h_radome'] = sl[2].strip()
                    except IndexError as e:
                        # print('Antenna Radome info missing in %s RINEX header, %s' % (f_rinex, e))
                        pass
                elif 'APPROX POSITION' in line[-25:]:  # format 3F14.4
                    header_inf['h_x'] = line[0:14].strip()
                    header_inf['h_y'] = line[14:28].strip()
                    header_inf['h_z'] = line[28:42].strip()
                elif 'ANTENNA: DELTA' in line[-25:]:
                    sl = line.split()
                    header_inf['h_h'] = sl[0].strip()
                    header_inf['h_e'] = sl[1].strip()
                    header_inf['h_n'] = sl[2].strip()
                elif 'TIME OF FIRST' in line[-25:]:
                    s_first_dt = line.split()
                    f_year = int(s_first_dt[0])
                    f_month = int(s_first_dt[1])
                    f_day = int(s_first_dt[2])
                    f_hour = int(s_first_dt[3])
                    f_min = int(s_first_dt[4])
                    f_sec = int(float(s_first_dt[5]))
                    header_inf['first_dt'] = datetime(f_year, f_month, f_day, f_hour, f_min, f_sec)
                elif 'END OF HEADER' in line[-25:]:
                    break
        except IndexError:
            err_log.error(' Problem in parsing RINEX header for %s' % f_rinex)

        error_codes = []

        lle = shared_funcs.cartesian2geodetic(float(header_inf['h_x']), float(header_inf['h_y']),
                                              float(header_inf['h_z']))
        if lle is None:  # in case approx XYZ in RINEX header were 0.0, 0,0, 0.0
            move_rinex_to_err_dir(year, doy, f_rinex)  # no chance to make long filename
            return None, [], None, None

        if lle is not None:
            header_inf['lat'] = float(lle[0])
            header_inf['lon'] = float(lle[1])
            header_inf['ele'] = float(lle[2])
        else:
            # leaving out from DF those files with zero values of XYZ in header, these are placed to
            # config.rinex_xyz_err_archive_path
            err_log.warning(f' Zero values of XYZ in header : {f_rinex}')
            error_codes.append(201)  # messy XYZ values in RINEX header

        return header_inf, error_codes, used_by, unzipped_rinex_path

    except Exception as e:
        err_log.warning(' Unknown exception in extract_header_inf for %s: %s' % (f_rinex, e))
        move_rinex_to_err_dir(year, doy, f_rinex)
        return None, [], None, None


def extract_header_inf_before_splityear(year, doy, f_rinex):
    """
    Function to unpack a RINEX file and extract GNSS metadata (receiver, antenna, approx. XYZ, antenna deltas,
    first epoch, interval, constellation, lat/lon/ele) from its header, for years < config.proc_split_year.
    Note: RINEX v1 files are copied to the RINEX v1 archive and converted to v2.11 in place; invalid files are
    deleted or moved to the erroneous files archive.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :param f_rinex: The RINEX filename (like abpo0010.22o).
    :return: A tuple (header_inf dict, list of error codes, list of reprocessing campaigns using the file,
        unpacked RINEX path), or (None, [], None, None) on failure.
    """

    try:
        header_inf = {}

        used_by = tools.if_rinex_used_in_igs_repro3(year, doy, f_rinex)
        if tools.if_rinex_used_in_epn_repro2(year, doy, f_rinex):
            used_by.append('EPN_repro2')

        r_path = get_rinex_dir(year, doy, config.rinex_archive_path)
        full_rinex_path = os.path.join(r_path, f_rinex)

        rinex_lines, unzipped_rinex_fn = readlines_zipped(full_rinex_path)  # get the RINEX lines

        #  Modifications 10Feb2026 for RINEX "old" v1 version and no "END OF HEADER" in RINEX header
        #  Check the version number, if "1":
        #  a) Convert RINEXv1 --> v2.11 b) copy the unzipped file into rinex_v1_archive_path = BASE_PATH + 'RINEX_v1/'
        #  c) continue processing the converted (RINEXv2.11 file) in a traditional way for long filename generation with
        #  Anubis QC, and if no *.xtr generated, etc., then move the file to RINEX_err (no need for using RINEX_v1_err)
        #
        if not tools.rinex_version_from_lines(rinex_lines) is None:
            if tools.rinex_version_from_lines(rinex_lines) == '1':
                # copy RINEX_v1 file to its archive, if the archive does not exist, create it
                if not os.path.exists(config.rinex_v1_archive_path + str(year) + '/' + str(doy).zfill(3) + '/'):
                    os.makedirs(config.rinex_v1_archive_path + str(year) + '/' + str(doy).zfill(3) + '/')
                shutil.copy(full_rinex_path,
                            config.rinex_v1_archive_path + str(year) + '/' + str(doy).zfill(3) + '/' + f_rinex)
                # convert from v1 --> v2.11 and replace
                cmd = config.rin1to2_executable + ' -finp ' + full_rinex_path + ' -fout ' + full_rinex_path + \
                    ' -vo 2 -f'
                os.system(cmd)
                # If it was initially RINEX_v1 file, than we start to process converted file v 2.11!!! Must
                #   refresh rinex_lines from the new converted to 2.11 version file
                with open(full_rinex_path, 'r', encoding='utf-8') as f:
                    rinex_lines = f.readlines()
        # ============================================================================
        # IF it was not NOT RINEX_V1, then from here on everything continues as before
        # ============================================================================

        if not rinex_lines:
            move_rinex_to_err_dir(year, doy, f_rinex)
            return None, [], None, None
        else:
            unzipped_rinex_path = os.path.join(r_path, unzipped_rinex_fn)

        if 'RINEX' not in rinex_lines[0] or 'TYPE' not in rinex_lines[0]:
            os.remove(unzipped_rinex_path)  # delete the file
            err_log.warning(f' {unzipped_rinex_path} deleted - the first line does not contain "RINEX" and "TYPE"')
            return None, [], None, None

        # if DOS file, i.e. b'\r\n' in line, and convert to UNIX (if DOS)
        if shared_funcs.dos_line_endings(unzipped_rinex_path):
            shared_funcs.dos2unix(unzipped_rinex_path)

        h_lines = []
        for line in rinex_lines:
            h_lines.append(line)
            if 'END OF HEADER' in line:
                break

        # define header_inf keys
        keys = [
            "h_receiver", "h_serial", "h_receiver_firmware",
            "h_antenna", "h_antenna_serial", "h_radome",
            "h_x", "h_y", "h_z", "h_h", "h_e", "h_n", "h_interval", "h_constellation", "lat", "lon", "ele"
        ]
        # assign keys to the dictionary with empty string values
        for key in keys:
            header_inf[key] = ''

        constellation = h_lines[0][40:41]
        if constellation == ' ':
            constellation = 'G'
        header_inf['h_constellation'] = constellation

        try:
            # it must be checked, whether the "key" is in the last 20-25 positions (i.e., at the end of the line)
            for line in h_lines:
                if ('REC #' in line[-25:]) and ('TYPE' in line[-25:]):
                    header_inf['h_serial'] = line[:20].strip()
                    header_inf['h_receiver'] = line[20:40].strip()
                    header_inf['h_receiver_firmware'] = line[40:60].strip()
                elif ('ANT #' in line[-25:]) and ('TYPE' in line[-25:]):
                    sl = line.split()
                    header_inf['h_antenna_serial'] = sl[0].strip()
                    header_inf['h_antenna'] = sl[1].split()[0].strip()
                    try:
                        if not sl[2] == 'ANT':
                            header_inf['h_radome'] = sl[2].strip()
                    except IndexError as e:
                        # print('Antenna Radome info missing in %s RINEX header, %s' % (f_rinex, e))
                        pass
                elif 'APPROX POSITION' in line[-25:]:  # format 3F14.4
                    # use "from", "to" to guarantee correct reading F14.4
                    header_inf['h_x'] = line[0:14].strip()
                    header_inf['h_y'] = line[14:28].strip()
                    header_inf['h_z'] = line[28:42].strip()
                elif 'ANTENNA: DELTA' in line[-25:]:
                    sl = line.split()
                    header_inf['h_h'] = sl[0].strip()
                    header_inf['h_e'] = sl[1].strip()
                    header_inf['h_n'] = sl[2].strip()
                elif 'TIME OF FIRST' in line[-25:]:
                    s_first_dt = line.split()
                    f_year = int(s_first_dt[0])
                    f_month = int(s_first_dt[1])
                    f_day = int(s_first_dt[2])
                    f_hour = int(s_first_dt[3])
                    f_min = int(s_first_dt[4])
                    f_sec = int(float(s_first_dt[5]))
                    # avoid error if f_sec >= 60 for old 1992 data in some obs files' headers
                    if f_sec >= 60:
                        f_sec = 59
                        err_log.warning(f'Seconds >= 60 in {f_rinex} header, set to 59')
                    header_inf['first_dt'] = datetime(f_year, f_month, f_day, f_hour, f_min, f_sec)
                elif 'INTERVAL' in line[-25:]:
                    sl = line.split()
                    header_inf['h_interval'] = sl[0].strip().lstrip()
                elif 'END OF HEADER' in line[-25:]:
                    break
        except IndexError:
            err_log.error(' Problem in parsing RINEX header for %s' % f_rinex)

        error_codes = []

        if header_inf['h_x'] == '' or header_inf['h_y'] == '' or header_inf['h_z'] == '':
            err_log.warning(f'Missing APPROX POSITION in RINEX %s header!' % f_rinex)
            return header_inf, error_codes, used_by, unzipped_rinex_path
        else:
            lle = shared_funcs.cartesian2geodetic(float(header_inf['h_x']), float(header_inf['h_y']),
                                                      float(header_inf['h_z']))
            if lle is None: # in case approx XYZ in RINEX header were 0.0, 0,0, 0.0
                move_rinex_to_err_dir(year, doy, f_rinex) # no chance to make long filename
                return None, [], None, None

        if lle is not None:
            header_inf['lat'] = float(lle[0])
            header_inf['lon'] = float(lle[1])
            header_inf['ele'] = float(lle[2])
        else:
            # leaving out from DF those files with zero values of XYZ in header, these are placed to
            # config.rinex_xyz_err_archive_path
            err_log.warning(f' Zero values of XYZ in header : {f_rinex}')
            error_codes.append(201)  # messy XYZ values in RINEX header
            # move_rinex_to_err_dir(year, doy, f_rinex)
        if header_inf['h_interval'] == '':
            header_inf['h_interval'] = '__'

        return header_inf, error_codes, used_by, unzipped_rinex_path

    except Exception as e:
        err_log.warning(' Unknown exception in extract_header_inf for %s: %s' % (f_rinex, e))
        move_rinex_to_err_dir(year, doy, f_rinex)
        return None, [], None, None


def get_long_filename(f_rinex, rinex_names_set_w_ext, unzipped_rnx_path, qc_inf, year, doy, network):
    """
    Function to get the long RINEX filename for a RINEX file. Already long filenames are kept (only the
    compression extension removed); short filenames get a generated long filename.
    Note: if no long filename can be generated, the RINEX file is moved to the erroneous files archive.
    :param f_rinex: The input RINEX filename.
    :param rinex_names_set_w_ext: A set of existing RINEX filenames (with extension).
    :param unzipped_rnx_path: The path of the unpacked RINEX file.
    :param qc_inf: The site information (incl. lat, lon, sample interval) from Anubis or a header-based replica.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :param network: The network name (currently unused).
    :return: A tuple (long RINEX filename, filename without extension, country code, matching existing filename
        with different resolution or None), or (None, None, None, None) on failure.
    """
    f_rinex_long = ''
    # if "long", do nothing, just give unzipped filenames (a must for Anubis free)
    if '_' in f_rinex and len(f_rinex) > 30:
        if f_rinex.endswith('.crx') or f_rinex.endswith('.rnx'):
            f_rinex_long = f_rinex
        if f_rinex.endswith('.gz'):
            f_rinex_long = f_rinex[:-3]
        if f_rinex.endswith('.Z'):
            f_rinex_long = f_rinex[:-2]
        country_code = f_rinex_long[6:9]
        diff_res_f_present = find_other_res_rinex_matching_new_file(f_rinex_long[:-4], rinex_names_set_w_ext)
    else:
        if year >= config.proc_split_year:
            sample_interval = str(int(qc_inf['sample_interval']))
            if f_rinex.endswith('.gz'):
                f_rinex_long, country_code, diff_res_f_present = (
                    shared_funcs.generate_long_filename_after_splityear(qc_inf['lat'], qc_inf['lon'], sample_interval, f_rinex[:-3],
                                                        rinex_names_set_w_ext))
            if f_rinex.endswith('.Z'):
                f_rinex_long, country_code, diff_res_f_present = (
                    shared_funcs.generate_long_filename_after_splityear(qc_inf['lat'], qc_inf['lon'], sample_interval, f_rinex[:-2],
                                                        rinex_names_set_w_ext))
            if f_rinex.endswith('.zip'):
                f_rinex = unzipped_rnx_path.split('/')[-1]
                f_rinex_long, country_code, diff_res_f_present = (
                    shared_funcs.generate_long_filename_after_splityear(qc_inf['lat'], qc_inf['lon'], sample_interval, f_rinex,
                                                        rinex_names_set_w_ext))
            if f_rinex.endswith('O') or f_rinex.endswith('o') or f_rinex.endswith('D') or f_rinex.endswith('d'):
                f_rinex_long, country_code, diff_res_f_present = (
                    shared_funcs.generate_long_filename_after_splityear(qc_inf['lat'], qc_inf['lon'], sample_interval, f_rinex,
                                                        rinex_names_set_w_ext))
            if not f_rinex_long:
                move_rinex_to_err_dir(year, doy, f_rinex)
                return None, None, None, None
        else:
            sample_interval = qc_inf['sample_interval']

            if f_rinex.endswith('.gz'):
                f_rinex_long, country_code, diff_res_f_present = (
                    shared_funcs.generate_long_filename_before_splityear(qc_inf['lat'], qc_inf['lon'], sample_interval,
                                                        qc_inf['first_epoch'], qc_inf['constellation_indicator'],
                                                        f_rinex[:-3], rinex_names_set_w_ext, unzipped_rnx_path))
            if f_rinex.endswith('.Z'):
                f_rinex_long, country_code, diff_res_f_present = (
                    shared_funcs.generate_long_filename_before_splityear(qc_inf['lat'], qc_inf['lon'], sample_interval,
                                                        qc_inf['first_epoch'], qc_inf['constellation_indicator'],
                                                        f_rinex[:-2], rinex_names_set_w_ext, unzipped_rnx_path))
            if f_rinex.endswith('.zip'):
                f_rinex = unzipped_rnx_path.split('/')[-1]
                f_rinex_long, country_code, diff_res_f_present = (
                    shared_funcs.generate_long_filename_before_splityear(qc_inf['lat'], qc_inf['lon'], sample_interval,
                                                        qc_inf['first_epoch'], qc_inf['constellation_indicator'],
                                                        f_rinex,
                                                        rinex_names_set_w_ext, unzipped_rnx_path))

            if f_rinex.endswith('O') or f_rinex.endswith('o') or f_rinex.endswith('D') or f_rinex.endswith('d'):
                f_rinex_long, country_code, diff_res_f_present = (
                    shared_funcs.generate_long_filename_before_splityear(qc_inf['lat'], qc_inf['lon'], sample_interval,
                                                        qc_inf['first_epoch'], qc_inf['constellation_indicator'],
                                                        f_rinex,
                                                        rinex_names_set_w_ext, unzipped_rnx_path))
            if not f_rinex_long:
                move_rinex_to_err_dir(year, doy, f_rinex)
                return None, None, None, None

    if not f_rinex.endswith('.zip'):
        f_rinex_without_extension = f_rinex_long.lower().split('.', 1)[0]
    else:
        f_rinex_without_extension = f_rinex
    return f_rinex_long, f_rinex_without_extension, country_code, diff_res_f_present


def find_other_res_rinex_matching_new_file(f_rinex_long_wo_ext, rinex_names_set_w_ext):
    """
    Function to find an existing RINEX file that matches the given long filename except for the sample interval.
    :param f_rinex_long_wo_ext: The long RINEX filename without extension.
    :param rinex_names_set_w_ext: A set of existing RINEX filenames (with extension).
    :return: The first matching filename, or None if there is no match.
    """
    split_string = f_rinex_long_wo_ext.split('_')

    # Use wildcard character and join the string back together
    split_string[4] = '.*'
    fuzzy_string = '_'.join(split_string).lower()  # e.g. 'ahid00usa_r_20162880000_01d_.*_mo'

    # Get the first entry in rinex_names_set_w_ext that matches the fuzzy_string, or None if there's no match
    # gives e.g. 'ahid00usa_r_20162880000_01d_30s_mo.crx'
    diff_res_matching_file_present = next((s for s in rinex_names_set_w_ext if re.match(fuzzy_string, s)), None)
    return diff_res_matching_file_present


def fallback_stn_tab_row(qc_inf, replica, used_by, country_code):
    """
    Function to build a fallback log line and station table row when no logfile comparison result is available.
    :param qc_inf: The site information from Anubis, or None.
    :param replica: The header-based replica of the site information, used if qc_inf is None.
    :param used_by: A list of reprocessing campaigns using the RINEX file.
    :param country_code: The country code of the site.
    :return: A tuple (log line [used_by agencies, None], station table row with country code, lat/lon/ellips,
        XYZ and None placeholders).
    """
    if not used_by:
        used_by_agencies = None
    else:
        used_by_agencies = ', '.join(str(item) for item in used_by)

    if qc_inf is None:
        qc_inf = replica

    line_to_log = [used_by_agencies, None]

    row_to_stn_tab = [country_code, qc_inf['lat'], qc_inf['lon'], qc_inf['ellips'], qc_inf['x'], qc_inf['y'],
                      qc_inf['z'], None, None, None, None]

    return line_to_log, row_to_stn_tab


def process_header_and_logfile(year, doy, f_rinex, rinex_names_set, rinex_names_set_w_ext, stn_df, network):
    """
    Function to extract the RINEX header, run the Anubis QC, get the long RINEX filename, find the logfile and
    compare the header with the logfile.
    :param year: The year of the RINEX file.
    :param doy: The day of year of the RINEX file.
    :param f_rinex: The RINEX filename.
    :param rinex_names_set: A set of existing RINEX filenames (without extension).
    :param rinex_names_set_w_ext: A set of existing RINEX filenames (with extension).
    :param stn_df: The station DataFrame used for looking up the logfile.
    :param network: The network name.
    :return: A tuple (line_to_log, row_to_stn_tab, RINEX filename (long if available), already-present flag,
        logfile name, logfile download datetime, 9-character site name, logfile source, abort flag,
        matching existing filename with different resolution or False).
    """

    if year >= config.proc_split_year:
        header_inf, error_codes, used_by, unzipped_rnx_path = extract_header_inf_after_splityear(year, doy, f_rinex)
    else:
        header_inf, error_codes, used_by, unzipped_rnx_path = extract_header_inf_before_splityear(year, doy, f_rinex)  # rnx_v1 --> v2 also

    if header_inf is None:  # if RINEX header missing altogether
        return None, None, f_rinex, False, None, None, None, None, False, False

    # Run Anubis QC for a downloaded () and, for year < config.proc_split_year possibly converted from RINEXv1 --> v2)
    # file in daily /RINEX
    qc_inf = shared_funcs.get_approx_position(year, doy, os.path.basename(unzipped_rnx_path))
    replica = {}

    if year >= config.proc_split_year:
        if qc_inf is None:
            return None, None, f_rinex, False, None, None, None, None, False, False

        f_rinex_long, f_rinex_long_wo_ext, country_code, diff_res_f_present = (
            get_long_filename(f_rinex, rinex_names_set_w_ext, unzipped_rnx_path, qc_inf, year, doy, network))
    else:
        if qc_inf is None:
            err_log.warning(f'No QC_inf from Anubis for {f_rinex}, using REPLICA based on RINEX header ')
            try:
                if header_inf['h_x'] == '':
                    header_inf['h_x'] = 0
                if header_inf['h_y'] == '':
                    header_inf['h_y'] = 0
                if header_inf['h_z'] == '':
                    header_inf['h_z'] = 0

                replica = {'lat': header_inf['lat'], 'lon': header_inf['lon'], 'ellips': header_inf['ele'],
                           'first_epoch': header_inf['first_dt'], 'constellation_indicator': header_inf['h_constellation'],
                           'sample_interval': header_inf['h_interval'], 'x': float(header_inf['h_x']),
                           'y': float(header_inf['h_y']), 'z': float(header_inf['h_z'])
                           }

            except ValueError as e:
                err_log.error(f'Missing or invalid XYZ in replica by RINEX header in {f_rinex}: {e}')

            qc_not_passed_fp_name = config.rinex_xyz_err_archive_path + str(year) + '/' + str(doy).zfill(
                3) + '/' + f_rinex
            unzipped_rnx_path = qc_not_passed_fp_name
            f_rinex_long, f_rinex_long_wo_ext, country_code, diff_res_f_present = (
                get_long_filename(f_rinex, rinex_names_set_w_ext, unzipped_rnx_path, replica, year, doy, network))  # unzipped_rnx_path should be RINEX_err + ...

        # if Anubis QC passed (no replica):
        if len(replica) == 0:
            f_rinex_long, f_rinex_long_wo_ext, country_code, diff_res_f_present = (
                get_long_filename(f_rinex, rinex_names_set_w_ext, unzipped_rnx_path, qc_inf, year, doy, network))
    if not f_rinex_long:  # if long RINEX name was not retrieved
        return None, None, f_rinex, False, None, None, None, None, False, False

    log_file, log_download_dt, site_name_9char, log_source = prepare_log_inf(f_rinex_long, stn_df, year, doy, network)
    if log_file == 'abort':
        return None, None, f_rinex, False, None, None, None, None, True, False

    if not config.correct_df_for_doy_logfile_info:
        if f_rinex_long_wo_ext in rinex_names_set:
            # RINEX already present (neglecting the extension crx or rnx at this stage)
            return None, None, f_rinex_long, True, log_file, log_download_dt, site_name_9char, log_source, False, False
        else:
            # such RINEX not present (neglecting the extension crx or rnx at this stage)
            if diff_res_f_present:
                # file with different resolution present - use that instead
                return (None, None, f_rinex_long, True, log_file, log_download_dt, site_name_9char, log_source, False,
                        diff_res_f_present)
    if log_file:
        if qc_inf is None:
            qc_inf = replica

        if log_file[-3:] == 'xml':  # logfile is in XML format
            line_to_log, row_to_stn_tab = (compare_with_logfile_xml(year, doy, f_rinex_long, log_file, header_inf,
                                                                    qc_inf, country_code, used_by, error_codes))

        else:  # logfile is in ASCII format
            line_to_log, row_to_stn_tab = (compare_with_logfile(year, doy, f_rinex_long, log_file, header_inf, qc_inf,
                                                                country_code, used_by, error_codes))
        if row_to_stn_tab:
            row_to_stn_tab.extend([site_name_9char, log_file, log_download_dt, log_source])
            return (line_to_log, row_to_stn_tab, f_rinex_long, False, log_file, log_download_dt, site_name_9char,
                    log_source, False, False)
        else:
            line_to_log, row_to_stn_tab = fallback_stn_tab_row(qc_inf, replica, used_by, country_code)
            return line_to_log, row_to_stn_tab, f_rinex_long, False, None, None, site_name_9char, None, False, False
    else:
        # No log file found. Include RINEX in dataframe, but skip the comparison with log.
        line_to_log, row_to_stn_tab = fallback_stn_tab_row(qc_inf, replica, used_by, country_code)
        return line_to_log, row_to_stn_tab, f_rinex_long, False, None, None, site_name_9char, None, False, False


def compare_with_logfile(year, doy, f_rinex, log_file, header_inf, qc_inf, country_code, used_by, error_codes):
    """
    Function to compare the RINEX header with an ASCII logfile (receiver type/serial/firmware, antenna
    type/serial/radome, antenna U/N/E, approximate XYZ) and collect error codes.
    Note: for years before the split year, logfiles without receiver subsections are copied to config.logfile_err_path.
    :param year: The year of the observation data.
    :param doy: The day of year of the observation data.
    :param f_rinex: The (long) filename of the RINEX file.
    :param log_file: The filename of the logfile.
    :param header_inf: A dictionary containing information from the RINEX file header.
    :param qc_inf: The site information (lat, lon, ellips, XYZ) from Anubis or a header-based replica.
    :param country_code: The country code of the site.
    :param used_by: A list of agencies using the RINEX in reprocessed datasets.
    :param error_codes: A list of error codes, extended in place.
    :return: A tuple ([used_by agencies, comma-separated error codes], [country code, lat, lon, ellips, x, y, z]),
        or (None, None) on failure.
    """

    try:
        l_path = config.logfile_archive_path
        if log_file:
            log_lines = read_log_file(l_path + log_file)
        else:
            log_lines = None

        res_log.info('      comparing %s header with %s' % (f_rinex, log_file))

        if not log_file:
            err_log.warning(f' NO LOGFILE for {f_rinex}')
            if (header_inf['h_receiver'] == '') or (header_inf['h_serial'] == '') or (
                    header_inf['h_receiver_firmware'] == ''):
                error_codes.append(301)  # incomplete receiver specification in RINEX header
            if (header_inf['h_antenna'] == '') or (header_inf['h_antenna_serial'] == '') or (
                    header_inf['h_radome'] == ''):
                error_codes.append(401)  # incomplete antenna specification in RINEX header

            if not used_by:
                used_by_agencies = None
            else:
                used_by_agencies = ', '.join(str(item) for item in used_by)

            lat_lon_ele = [country_code, qc_inf['lat'], qc_inf['lon'], qc_inf['ellips'], qc_inf['x'], qc_inf['y'],
                           qc_inf['z']]
            if len(error_codes) == 0:  # adding '0' as we cannot check and compare with logfile
                error_codes.append(0)
            comma_separated_errors = ', '.join(str(item) for item in error_codes)
            new_line = [used_by_agencies, comma_separated_errors]
            return new_line, lat_lon_ele

        # =============  END RINEX HEADER DATA, START WITH LOGFILE ===============================

        rec_install_remove, ant_install_remove, receiver_firmware, ant_type_radome, ant_une, rec_serial, ant_serial = \
            [], [], [], [], [], [], []

        # find the section start lines
        loc_inf_beg, rec_inf_beg, ant_inf_beg = 0, 0, 0
        if year >= config.proc_split_year:
            for i in range(len(log_lines)):
                if '2.' and 'Site Location Information' in log_lines[i]:
                    loc_inf_beg = i
                elif '3.' and 'GNSS Receiver Information' in log_lines[i]:
                    rec_inf_beg = i
                elif '4.' and 'GNSS Antenna Information' in log_lines[i]:
                    ant_inf_beg = i
                    break
        else:
            for i in range(len(log_lines)):
                if ('2.' and 'Site Location Information' in log_lines[i]) or \
                        ('2.' and 'Site Location' in log_lines[i]):
                    loc_inf_beg = i
                elif ('3.' and 'GNSS Receiver Information' in log_lines[i]) or \
                        ('3.' and 'GPS Receiver Information' in log_lines[i]) or \
                        ('3.' and 'GPS Receiver' in log_lines[i]):
                    rec_inf_beg = i
                elif ('4.' and 'GNSS Antenna Information' in log_lines[i]) or \
                        ('4.' and 'GPS Antenna Information' in log_lines[i]) or \
                        ('4.' and 'GPS Antenna' in log_lines[i]):
                    ant_inf_beg = i
                    break

        # ====== section 3 ============
        # we have a number of receiver data sections, ending with empty '3.x'
        # must iterate over all of them until '3.x' reached. At the end of each section append installed, removed to
        # rec_install_remove
        installed, removed = '', ''
        i = rec_inf_beg
        inst_date_found, remove_date_found, rec_type_found, rec_firm_found = False, False, False, False
        tmp_rec_type, tmp_rec_firm, tmp_rec_serial = '', '', ''
        # To avoid situation like this (Date Installed at unexpected place):
        #      Date Installed           : 2011-06-16T16:35Z
        #      Date Removed             : 2011-07-12T13:30Z
        #      Temperature Stabiliz.    : 20 +/-3
        #      Additional Information   : Change Date Installed from 2011-06-16 to 2011-06-16T16:35Z
        # splitting the line with ':' and checking only the 1st part for 'key'

        if year < config.proc_split_year:
            # Check, if 1st section 3.1 present. If not, then move logfile to logfiles_err and quit comparing with
            # RINEX header
            for i in range(rec_inf_beg, rec_inf_beg + 3):
                if ('Type' in log_lines[i]) and ('3.1' not in log_lines[i]):
                    print(f'===========================================')
                    print(f'Logfile %s receiver section has no subsections' % log_file)
                    print(f'===========================================')
                    if not os.path.exists(config.logfile_err_path):
                        os.makedirs(config.logfile_err_path)

                    if not used_by:
                        used_by_agencies = None
                    else:
                        used_by_agencies = ', '.join(str(item) for item in used_by)

                    lat_lon_ele = [country_code, qc_inf['lat'], qc_inf['lon'], qc_inf['ellips'], qc_inf['x'],
                                   qc_inf['y'],
                                   qc_inf['z']]
                    if not os.path.exists(config.logfile_err_path + log_file):
                        shutil.copyfile(config.logfile_archive_path + log_file, config.logfile_err_path + log_file)
                        err_log.warning(f'In logfile %s the receiver section has no subsections' % log_file)
                        if len(error_codes) == 0:  # adding '0' as we cannot check and compare with logfile
                            error_codes.append(501)  # 0 --> 501
                        comma_separated_errors = ', '.join(str(item) for item in error_codes)
                        new_line = [used_by_agencies, comma_separated_errors]

                        return new_line, lat_lon_ele
                    else:  # do the same, without copying the logfile that was already present
                        err_log.warning(f'In logfile %s the receiver section has no subsections' % log_file)
                        if len(error_codes) == 0:  # adding '0' as we cannot check and compare with logfile
                            error_codes.append(501)  # 0 --> 501
                        comma_separated_errors = ', '.join(str(item) for item in error_codes)
                        new_line = [used_by_agencies, comma_separated_errors]
                        return new_line, lat_lon_ele

            i = rec_inf_beg
        while '3.x' not in log_lines[i]:
            if 'GNSS Antenna Information' in log_lines[i]:  # if already starting next section
                break  # in case '3.x' section missing in logfile
            if ':' in log_lines[i]:
                sl = log_lines[i].split(':')
                if 'Receiver Type' in sl[0]:
                    tmp_rec_type = log_lines[i].split(':')[1].strip()
                    rec_type_found = True
                if 'Firmware Version' in sl[0]:
                    tmp_rec_firm = log_lines[i].split(':')[1].strip()
                    rec_firm_found = True
                if 'Serial Number' in sl[0]:
                    rec_serial.append(log_lines[i].split(':')[1].strip())
                if 'Date Installed' in sl[0]:
                    installed = check_string_for_dt(log_lines[i], log_file, year)
                    if installed:
                        inst_date_found = True
                if 'Date Removed' in sl[0]:
                    removed = check_string_for_dt(log_lines[i], log_file, year)
                    if removed:
                        remove_date_found = True

            i += 1
            if rec_type_found is True and rec_firm_found is True:
                receiver_firmware.append((tmp_rec_type, tmp_rec_firm))
                rec_type_found, rec_firm_found = False, False
            if inst_date_found is True and remove_date_found is True:
                rec_install_remove.append((installed, removed))
                inst_date_found, remove_date_found = False, False

        # ====== section 4 ============
        installed, removed = '', ''
        i = ant_inf_beg
        inst_date_found, remove_date_found = False, False
        tmp_ant_type, tmp_ant_radome, tmp_ant_serial, tmp_up, tmp_north, tmp_east = '', '', '', '', '', ''
        ant_type_found, ant_radome_found, up_found, north_found, east_found = False, False, False, False, False
        while '4.x' not in log_lines[i]:
            if 'Surveyed Local' in log_lines[i]:  # if already starting next section
                break  # in case '4.x' section missing in logfile
            if ':' in log_lines[i]:
                sl = log_lines[i].split(':')
                if 'Antenna Type' in sl[0]:
                    tmp_ant_type = log_lines[i].split(':')[1].strip().split()[0]
                    ant_type_found = True
                if ('Serial Number' in sl[0]) and not ('Radome' in sl[0]):
                    ant_serial.append(log_lines[i].split(':')[1].strip())
                if 'Marker' and 'Up' in sl[0]:
                    tmp_up = log_lines[i].split(':')[1].strip()
                    up_found = True
                if 'Marker' and 'North' in sl[0]:
                    tmp_north = log_lines[i].split(':')[1].strip()
                    north_found = True
                if 'Marker' and 'East' in sl[0]:
                    tmp_east = log_lines[i].split(':')[1].strip()
                    east_found = True
                if 'Radome Type' in sl[0]:
                    tmp_ant_radome = log_lines[i].split(':')[1].strip()
                    ant_radome_found = True
                if 'Date Installed' in sl[0]:
                    installed = check_string_for_dt(log_lines[i], log_file, year)
                    if installed:
                        inst_date_found = True
                if 'Date Removed' in sl[0]:
                    removed = check_string_for_dt(log_lines[i], log_file, year)
                    if removed:
                        remove_date_found = True

            i += 1
            if up_found is True and north_found is True and east_found is True:
                ant_une.append((tmp_up, tmp_north, tmp_east))
                up_found, north_found, east_found = False, False, False
            if ant_type_found is True and ant_radome_found is True:
                ant_type_radome.append((tmp_ant_type, tmp_ant_radome))
                ant_type_found, ant_radome_found = False, False
            if inst_date_found is True and remove_date_found is True:
                ant_install_remove.append((installed, removed))
                inst_date_found, remove_date_found = False, False

        # =============  END PARSING LOGFILE ======================================================
        # search by first_dt: a) with receiver data and b) antenna
        receiver_from_section, antenna_from_section = 0, 0
        section_3_format_error, section_4_format_error = False, False
        for i in range(len(receiver_firmware)):
            try:
                rec_install_remove1_temp = rec_install_remove[i].__getitem__(0)
                rec_install_remove2_temp = rec_install_remove[i].__getitem__(1)
                if not isinstance(rec_install_remove1_temp, str) or not isinstance(rec_install_remove2_temp, str):
                    section_3_format_error = True
                else:
                    tmp_install = datetime.strptime(rec_install_remove[i].__getitem__(0), '%Y-%m-%dT%H:%MZ')
                    tmp_remove = datetime.strptime(rec_install_remove[i].__getitem__(1), '%Y-%m-%dT%H:%MZ')
                    # convert datetime to UNIX timestamp before aa <= bb <= cc
                    if tools.datetime_to_timestamp(tmp_install) <= tools.datetime_to_timestamp(
                            header_inf['first_dt']) <= tools.datetime_to_timestamp(tmp_remove):
                        receiver_from_section = i
                        break
            except ValueError as e:
                if i < len(rec_install_remove) - 1:
                    section_3_format_error = True
                else:
                    receiver_from_section = i  # receiver from the "last" with removed alphabetic 'CCYY-MM-DDThhmmZ'
                    break
            except IndexError as e:
                if i < len(rec_install_remove) - 1:
                    section_3_format_error = True
                else:
                    receiver_from_section = i  # receiver from the "last" with removed alphabetic 'CCYY-MM-DDThhmmZ'
                    break

        rec_type = receiver_firmware[receiver_from_section].__getitem__(0)
        rec_firm_vers = receiver_firmware[receiver_from_section].__getitem__(1)
        rec_serial_number = rec_serial[receiver_from_section]

        for i in range(len(ant_type_radome)):
            try:
                ant_install_remove1_temp = ant_install_remove[i].__getitem__(0)
                ant_install_remove2_temp = ant_install_remove[i].__getitem__(1)
                if not isinstance(ant_install_remove1_temp, str) or not isinstance(ant_install_remove2_temp, str):
                    section_4_format_error = True
                else:
                    tmp_install = datetime.strptime(ant_install_remove[i].__getitem__(0), '%Y-%m-%dT%H:%MZ')
                    tmp_remove = datetime.strptime(ant_install_remove[i].__getitem__(1), '%Y-%m-%dT%H:%MZ')
                    if tools.datetime_to_timestamp(tmp_install) <= tools.datetime_to_timestamp(
                            header_inf['first_dt']) <= tools.datetime_to_timestamp(tmp_remove):
                        antenna_from_section = i
                        break
            except ValueError as e:
                if i < len(ant_install_remove) - 1:
                    section_4_format_error = True
                else:
                    antenna_from_section = i
                    break
            except IndexError as e:
                if i < len(ant_install_remove) - 1:
                    section_4_format_error = True
                else:
                    antenna_from_section = i
                    break

        ant_type = ant_type_radome[antenna_from_section].__getitem__(0)
        ant_radome = ant_type_radome[antenna_from_section].__getitem__(1)
        ant_serial_number = ant_serial[antenna_from_section]
        arp_une_present = True
        try:
            ant_u = ant_une[antenna_from_section].__getitem__(0)
            ant_n = ant_une[antenna_from_section].__getitem__(1)
            ant_e = ant_une[antenna_from_section].__getitem__(2)
        except (IndexError, ValueError) as e:
            arp_une_present = False
            error_codes.append(402)  # incomplete antenna specification in logfile, une missing

        # ===== COMPARING HEADER vers. LOGFILE ======
        # XYZ values comparison -- +/- 50m used as an acceptable tolerance by GFZ

        if (year < config.proc_split_year and (
                header_inf['h_x'] == '' or header_inf['h_y'] == '' or header_inf['h_z'] == '')):
                pass
        else:
            # header XYZ compared with qc_inf from Anubis
            xyz_tolerance = 50
            if not qc_inf.get('x') - xyz_tolerance <= float(header_inf['h_x']) <= qc_inf.get('x') + xyz_tolerance:
                pos_error_code = 21
                error_codes.append(pos_error_code)
            if not qc_inf.get('y') - xyz_tolerance <= float(header_inf['h_y']) <= qc_inf.get('y') + xyz_tolerance:
                pos_error_code = 22
                error_codes.append(pos_error_code)
            if not qc_inf.get('z') - xyz_tolerance <= float(header_inf['h_z']) <= qc_inf.get('z') + xyz_tolerance:
                pos_error_code = 23
                error_codes.append(pos_error_code)

        # In section 3, 4 comparisons: if any of the parameters is missing ('' or None) from Header or logfile,
        # then AttributeError due to NoneType object has no attribute lower()
        # If h_receiver == '' or h_serial == '' or h_receiver_firmware == '', then error_codes.append(301),
        # denoting incomplete receiver specification in RINEX header
        # If h_antenna == '' or h_antenna_serial == '' or h_radome == '', then error_codes.append(401), denoting
        # incomplete antenna specification in RINEX header

        if (header_inf['h_receiver'] == '') or (header_inf['h_serial'] == '') or (
                header_inf['h_receiver_firmware'] == ''):
            error_codes.append(301)  # incomplete receiver specification in RINEX header
        if (rec_type is None) or (rec_serial_number is None) or (rec_firm_vers is None):
            error_codes.append(302)  # incomplete receiver specification in logfile
        if (header_inf['h_antenna'] == '') or (header_inf['h_antenna_serial'] == '') or (header_inf['h_radome'] == ''):
            error_codes.append(401)  # incomplete antenna specification in RINEX header
        if (ant_type is None) or (ant_serial_number is None) or (ant_radome is None):
            error_codes.append(402)  # incomplete antenna specification in logfile

        if section_3_format_error:
            error_codes.append(30)
        if not header_inf['h_receiver'].lower() == rec_type.lower():
            rec_error_code = 31
            error_codes.append(rec_error_code)
        if not header_inf['h_serial'].lower() == rec_serial_number.lower():
            rec_error_code = 32
            error_codes.append(rec_error_code)
        if not header_inf['h_receiver_firmware'].lower() == rec_firm_vers.lower():
            rec_error_code = 33
            error_codes.append(rec_error_code)

        if section_4_format_error:
            error_codes.append(40)
        if not header_inf['h_antenna'].lower() == ant_type.lower():
            ant_error_code = 41
            error_codes.append(ant_error_code)
        if not header_inf['h_antenna_serial'].lower() == ant_serial_number.lower():
            ant_error_code = 42
            error_codes.append(ant_error_code)
        if not header_inf['h_radome'].lower() == ant_radome.lower():
            ant_error_code = 43
            error_codes.append(ant_error_code)

        # antenna eccentricity data comparison
        ant_tol = 0.0005  # antenna eccentricity check tolerance 0.0005 m = 0.5 mm (the same at GFZ)
        # if any of h_h, h_n, h_e, ant_u, ant_n, ant_e is not a number -- it is a fault
        #  for RINEX header error 47, for logfile error 48
        if not tools.is_number(header_inf['h_h']) or not tools.is_number(header_inf['h_n']) or not tools.is_number(
                header_inf['h_e']):
            ant_error_code = 47
            error_codes.append(ant_error_code)

        if arp_une_present:
            if not tools.is_number(ant_u) or not tools.is_number(ant_n) or not tools.is_number(ant_e):
                ant_error_code = 48
                error_codes.append(ant_error_code)

            if (47 in error_codes) or (48 in error_codes):
                pass
            else:  # compare the values
                if not float(ant_u) - ant_tol <= float(header_inf['h_h']) <= float(ant_u) + ant_tol:
                    ant_error_code = 44  # TODO: no need to set tolerance for UP-component
                    error_codes.append(ant_error_code)
                if not float(ant_n) - ant_tol <= float(header_inf['h_n']) <= float(ant_n) + ant_tol:
                    ant_error_code = 45
                    error_codes.append(ant_error_code)
                if not float(ant_e) - ant_tol <= float(header_inf['h_e']) <= float(ant_e) + ant_tol:
                    ant_error_code = 46
                    error_codes.append(ant_error_code)

        if not used_by:
            used_by_agencies = None
        else:
            used_by_agencies = ', '.join(str(item) for item in used_by)

        lat_lon_ele = [country_code, qc_inf['lat'], qc_inf['lon'], qc_inf['ellips'], qc_inf['x'], qc_inf['y'],
                       qc_inf['z']]

        if len(error_codes) == 0:  # if no errors, write error code 0
            null_error = ' 0'
            error_codes.append(null_error)
            new_line = [used_by_agencies, null_error]
            return new_line, lat_lon_ele
        else:
            comma_separated_errors = ', '.join(str(item) for item in error_codes)
            new_line = [used_by_agencies, comma_separated_errors]
            return new_line, lat_lon_ele

    except (ValueError, FileNotFoundError) as ex:
        err_log.warning(' %s for %s' % (ex, f_rinex))
        return None, None
    except IndexError as ie:
        err_log.warning(' Index Error from compare_with_logfile for %s: %s' % (f_rinex, ie))
        # print('Last processed: ', f_log, f_rinex)
        return None, None
    except Exception as e:
        # print(' Unknown exception in compare_with_logfile for %s: %s' % (f_rinex, e))
        err_log.error(' Unknown exception in compare_with_logfile for %s: %s' % (f_rinex, e))
        return None, None


def compare_with_logfile_xml(year, doy, f_rinex, log_file, header_inf, qc_inf, country_code, used_by, error_codes):
    """
    Function to compare the RINEX header with an XML logfile (currently only Geoscience Australia) for receiver
    type/serial/firmware, antenna type/serial/radome, antenna U/N/E and approximate XYZ, and collect error codes.
    :param year: The year of the observation data.
    :param doy: The day of year of the observation data.
    :param f_rinex: The (long) filename of the RINEX file.
    :param log_file: The filename of the XML logfile.
    :param header_inf: A dictionary containing information from the RINEX file header.
    :param qc_inf: The site information (lat, lon, ellips, XYZ) from Anubis or a header-based replica.
    :param country_code: The country code of the site.
    :param used_by: A list of agencies using the RINEX in reprocessed datasets.
    :param error_codes: A list of error codes, extended in place.
    :return: A tuple ([used_by agencies, comma-separated error codes], [country code, lat, lon, ellips, x, y, z]),
        or (None, None) on failure.
    """

    try:
        l_path = config.logfile_archive_path

        res_log.info('      comparing %s header with %s' % (f_rinex, log_file))

        # =============  END RINEX HEADER DATA, START WITH LOGFILE ===============================
        rec_type, rec_firm, ant_type, ant_u, ant_n, ant_e, ant_radome = '', '', '', '', '', '', ''
        # TODO 01052024: rec_serial_number, ... referred before assignment, gives run-time error
        rec_firm_vers, rec_serial_number, ant_serial_number = '', '', ''

        # check if XML-file is valid or empty
        if process_geoscience_australia.params_from_xml_log(l_path + log_file) == -1:
            err_log.warning('Invalid or missing logfile %s ' % log_file)
            return None, None

        site_inf, receiver_inf, antenna_inf = process_geoscience_australia.params_from_xml_log(l_path + log_file)
        rec_data, ant_data, format_errors = \
            process_geoscience_australia.get_site_par_by_date_from_log(site_inf, receiver_inf, antenna_inf,
                                                                       year, doy)

        # frinex_list_x = sorted(os.listdir(tmp_rinex_path))  # unzipped rinex-files list (incl non-rinex files)
        # =============  END PARSING LOGFILE ======================================================
        section_3_format_error, section_4_format_error = False, False
        if not format_errors[0] == '':
            section_3_format_error = True
        if not format_errors[1] == '':
            section_4_format_error = True

        if not section_3_format_error:
            rec_type = rec_data[3]
            rec_firm_vers = rec_data[4]
            rec_serial_number = rec_data[2]

        if not section_4_format_error:
            ant_type = ant_data[3]
            ant_radome = ant_data[4]
            ant_serial_number = ant_data[2]
            ant_u = ant_data[5]
            ant_n = ant_data[6]
            ant_e = ant_data[7]

        # ===== COMPARING HEADER vers. LOGFILE ======
        # XYZ values comparison -- +/- 50m used as an acceptable tolerance (GFZ)
        xyz_tolerance = 50  # used by GFZ
        # header XYZ compared with qc_inf from Anubis
        if not qc_inf.get('x') - xyz_tolerance <= float(header_inf['h_x']) <= qc_inf.get('x') + xyz_tolerance:
            pos_error_code = 21
            error_codes.append(pos_error_code)
        if not qc_inf.get('y') - xyz_tolerance <= float(header_inf['h_y']) <= qc_inf.get('y') + xyz_tolerance:
            pos_error_code = 22
            error_codes.append(pos_error_code)
        if not qc_inf.get('z') - xyz_tolerance <= float(header_inf['h_z']) <= qc_inf.get('z') + xyz_tolerance:
            pos_error_code = 23
            error_codes.append(pos_error_code)

        # In section 3, 4 comparisons: if any of the parameters is missing ('' or None) from Header or logfile,
        # then AttributeError due to NoneType object has no attribute lower()
        # If h_receiver == '' or h_serial == '' or h_receiver_firmware == '', then error_codes.append(301),
        # denoting incomplete receiver specification in RINEX header
        # If h_antenna == '' or h_antenna_serial == '' or h_radome == '', then error_codes.append(401), denoting
        # incomplete antenna specification in RINEX header

        if (header_inf['h_receiver'] == '') or (header_inf['h_serial'] == '') or (
                header_inf['h_receiver_firmware'] == ''):
            error_codes.append(301)  # incomplete receiver specification in RINEX header
        if (rec_type is None) or (rec_serial_number is None) or (rec_firm_vers is None):
            error_codes.append(302)  # incomplete receiver specification in logfile
        if (header_inf['h_antenna'] == '') or (header_inf['h_antenna_serial'] == '') or (header_inf['h_radome'] == ''):
            error_codes.append(401)  # incomplete antenna specification in RINEX header
        if (ant_type is None) or (ant_serial_number is None) or (ant_radome is None):
            error_codes.append(402)  # incomplete antenna specification in logfile

        if section_3_format_error:  # receiver section in logfile
            error_codes.append(30)
        else:
            if rec_type is not None:
                if not (header_inf['h_receiver'] == '') and not (rec_type == ''):  # otherwise, errors 30, 301, avoiding
                    # AttributeError
                    if not header_inf['h_receiver'].lower() == rec_type.lower():
                        rec_error_code = 31
                        error_codes.append(rec_error_code)
            if rec_serial_number is not None:
                if not (header_inf['h_serial'] == '') and not (rec_serial_number == ''):  # otherwise, errors 30, 301
                    if not header_inf['h_serial'].lower() == rec_serial_number.lower():
                        rec_error_code = 32
                        error_codes.append(rec_error_code)
            if rec_firm_vers is not None:
                if not (header_inf['h_receiver_firmware'] == '') and not (
                        rec_firm_vers == ''):  # otherwise, errors 30, 301
                    if not header_inf['h_receiver_firmware'].lower() == rec_firm_vers.lower():
                        rec_error_code = 33
                        error_codes.append(rec_error_code)

        if section_4_format_error:
            error_codes.append(40)
        else:
            if ant_type is not None:
                if not (header_inf['h_antenna'] == '') and not (
                        ant_type == ''):  # otherwise, errors 40, 401, avoiding AttributeError
                    if not header_inf['h_antenna'].lower() == ant_type.lower():
                        ant_error_code = 41
                        error_codes.append(ant_error_code)
            if ant_serial_number is not None:
                if not (header_inf['h_antenna_serial'] == '') and not (
                        ant_serial_number == ''):  # otherwise, errors 40, 401
                    if not header_inf['h_antenna_serial'].lower() == ant_serial_number.lower():
                        ant_error_code = 42
                        error_codes.append(ant_error_code)
            if ant_radome is not None:
                if not (header_inf['h_radome'] == '') and not (ant_radome == ''):  # otherwise, errors 40, 401
                    if not header_inf['h_radome'].lower() == ant_radome.lower():
                        ant_error_code = 43
                        error_codes.append(ant_error_code)

        # antenna eccentricity data comparison
        ant_tol = 0.0005  # antenna eccentricity check tolerance 0.0005 m = 0.5 mm (the same at GFZ, Markus 10-02-2023)
        # if any of h_h, h_n, h_e, ant_u, ant_n, ant_e is not a number -- it is a fault
        #  for RINEX header error 47, for logfile error 48
        if not tools.is_number(header_inf['h_h']) or not tools.is_number(header_inf['h_n']) or not tools.is_number(
                header_inf['h_e']):
            ant_error_code = 47
            error_codes.append(ant_error_code)
        if not tools.is_number(ant_u) or not tools.is_number(ant_n) or not tools.is_number(ant_e):
            ant_error_code = 48
            error_codes.append(ant_error_code)

        if 47 or 48 in error_codes:
            pass
        else:
            if not float(ant_u) - ant_tol <= float(header_inf['h_h']) <= float(ant_u) + ant_tol:
                ant_error_code = 44
                error_codes.append(ant_error_code)
            if not float(ant_n) - ant_tol <= float(header_inf['h_n']) <= float(ant_n) + ant_tol:
                ant_error_code = 45
                error_codes.append(ant_error_code)
            if not float(ant_e) - ant_tol <= float(header_inf['h_e']) <= float(ant_e) + ant_tol:
                ant_error_code = 46
                error_codes.append(ant_error_code)

        if not used_by:
            used_by_agencies = None
        else:
            used_by_agencies = ', '.join(str(item) for item in used_by)

        lat_lon_ele = [country_code, qc_inf['lat'], qc_inf['lon'], qc_inf['ellips'], qc_inf['x'], qc_inf['y'],
                       qc_inf['z']]

        if len(error_codes) == 0:
            null_error = ' 0'
            error_codes.append(null_error)
            new_line = [used_by_agencies, null_error]
            return new_line, lat_lon_ele
        else:
            comma_separated_errors = ', '.join(str(item) for item in error_codes)
            new_line = [used_by_agencies, comma_separated_errors]
            return new_line, lat_lon_ele
    except FileNotFoundError:
        err_log.warning(' File not found in compare_with_logfile_xml for %s' % f_rinex)
        return None, None
    except IndexError:
        err_log.warning(' IndexError from compare_with_logfile_xml for %s' % f_rinex)
        return None, None
    except ValueError:
        err_log.warning(' ValueError from compare_with_logfile_xml for %s' % f_rinex)
        return None, None
    except Exception as e:
        err_log.error(' Unknown exception in compare_with_logfile_xml for %s: %s' % (f_rinex, e))
        return None, None