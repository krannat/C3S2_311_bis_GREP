import paramiko
import stat
import posixpath
import logging
import ftplib
import time
from urllib.parse import urlparse
from datetime import datetime, timedelta
import config

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def day_of_year_to_mm_dd(year, day_of_year):
    """
    Function to convert a year and day of year into month and day strings.
    :param year: The year (int).
    :param day_of_year: The day of year (int).
    :return: Tuple (month, day) as zero-padded strings ('MM', 'DD').
    """
    date = datetime(year, 1, 1) + timedelta(day_of_year - 1)
    return date.strftime('%m'), date.strftime('%d')


def merge_lists(list1, list2):
    """
    Function to concatenate two lists, handling the case where one of them is None.
    :param list1: The first list (or None).
    :param list2: The second list (or None).
    :return: The concatenated list if both are not None, otherwise the one that is truthy (or list2).
    """
    if list1 is not None and list2 is not None:
        return list1 + list2
    else:
        return list1 or list2


def get_rinex_list(year, doy):
    """
    Function to get the daily Uruguay RINEX list and remote paths by combining the historical (SFTP) and latest
    year (FTP) archives; sites in the latest archive take precedence over the historical ones.
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: Tuple (rinex_names, rinex_paths); ([], []) if the DOY should be skipped, (None, None) if processing should abort.
    """
    rinex_names_hist, rinex_paths_hist, flag = get_rinex_list_historical(year, doy, "0.rnx.zip")
    rinex_names_latest, rinex_paths_latest = get_rinex_list_latest_year(year, doy, ".gz")

    if rinex_names_hist and rinex_paths_hist and rinex_names_latest and rinex_paths_latest:
        # lowercase first 4 characters of rinex_names_latest
        rinex_names_latest_4_chr = [name[:4].lower() for name in rinex_names_latest]

        # filter rinex_names_hist and rinex_paths_hist
        filtered_rinex_names_hist, filtered_rinex_paths_hist = [], []
        for name, path in zip(rinex_names_hist, rinex_paths_hist):
            if name[:4].lower() not in rinex_names_latest_4_chr:
                filtered_rinex_names_hist.append(name)
                filtered_rinex_paths_hist.append(path)

        rinex_names = merge_lists(filtered_rinex_names_hist, rinex_names_latest)
        rinex_paths = merge_lists(filtered_rinex_paths_hist, rinex_paths_latest)
    elif not rinex_names_hist and not rinex_names_latest:
        if flag == 'skip_doy':
            # will skip uruguay processing for the current DOY (connection OK but RINEX list empty)
            return [], []
        else:
            if year < 2017:  # RINEX files are available since 2017 (accessed 7th Feb 2025) - just skip this DOY
                return [], []
            else:
                # RINEX files should be available, will abort the processing, the next DOY will not be processed
                return None, None

    else:
        if rinex_names_hist and rinex_paths_hist:
            rinex_names = rinex_names_hist
            rinex_paths = rinex_paths_hist
        else:
            rinex_names = rinex_names_latest
            rinex_paths = rinex_paths_latest
    return rinex_names, rinex_paths


def get_rinex_list_latest_year(year, doy, ext):
    """
    Function to list the files ending with the given extension in the /YYYY/DOY directory of the Uruguay latest
    year FTP server.
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :param ext: The file extension to filter by.
    :return: Tuple (matching_files, matching_files_fullpath) of file names and their remote directory URLs, or (None, None).
    """
    url = urlparse(config.uruguay_rinex_latest_url)
    hostname = url.netloc  # This gives 'pp.igm.gub.uy'
    directory = url.path.lstrip('/') + str(year) + '/' + str(doy).zfill(3)

    # create an FTP client
    ftp = ftplib.FTP(hostname)
    ftp.login("Anonymous")

    server_url = f'ftp://{hostname}/'
    dir_url = server_url + directory

    try:
        ftp.cwd(directory)
        files = ftp.nlst()
        matching_files = [filename for filename in files if filename.endswith(ext)]
        if matching_files:
            matching_files_fullpath = [dir_url] * len(matching_files)
        else:
            matching_files = matching_files_fullpath = None
    except ftplib.error_perm as e:
        err_message = str(e)
        if "Failed to change directory" in err_message:
            err_log.warning(f' No such directory as {directory} at {server_url}')
            matching_files = matching_files_fullpath = None
        else:
            # Handle other permissions errors as before
            err_log.error(' Could not handle the exception from process_uruguay.get_rinex_list_latest_year(): %s' % e)
            matching_files = matching_files_fullpath = None
    except ftplib.all_errors as e:
        err_log.error(' Could not handle the exception from process_uruguay.get_rinex_list_latest_year(): %s' % e)
        matching_files = matching_files_fullpath = None
    finally:
        # close the FTP session
        ftp.quit()

    return matching_files, matching_files_fullpath


def get_rinex_list_historical(year, doy, ext):
    """
    Function to recursively list the files ending with the given extension in the /YYYY/MM/DD/ directory of the
    Uruguay historical SFTP server (SSH connection retried up to 5 times).
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :param ext: The file extension to filter by.
    :return: Tuple (matching_files, matching_files_fullpath, flag) where flag is 'ok', 'skip_doy' (no files) or 'abort_doy' (error; lists are None).
    """
    url_base = config.uruguay_rinex_hist_url
    month, day = day_of_year_to_mm_dd(year, doy)
    url = url_base + str(year) + '/' + month + '/' + day + '/'
    # extract server domain and directory path from url
    # url should be in the form 'sftp://sftp.domain.com/path/to/directory'
    scheme, rest = url.split("://")
    rest_parts = rest.split("/", 1)

    # domain is first part of `rest`, path is remainder or an empty string
    server, path = rest_parts if len(rest_parts) > 1 else (rest_parts[0], "")

    max_retries = 5
    wait_time = 60
    ssh_conn = False
    sftp_conn = False
    for n in range(max_retries):
        try:
            if not ssh_conn:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server, 2222, username="regna", password="historico")
                ssh_conn = True

            if not sftp_conn and ssh_conn:
                sftp = ssh.open_sftp()
                sftp_conn = True

            # Exit the loop if both the SSH and SFTP connections were successful
            if ssh_conn and sftp_conn:
                break

        except Exception as e:
            err_log.warning(f" SSH connection failed in process_uruguay.get_rinex_list_historical() with error {e}. "
                            f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

    if not ssh_conn or not sftp_conn:
        err_log.warning(f" SSH connection failed in process_uruguay.get_rinex_list_historical(). Max retries reached. "
                        f"Aborting...")
        return None, None, 'abort_doy'

    server_url = "://".join(url.split("://")[:2])  # Exact server part of the URL
    dir_url = "/".join(url.split("/")[3:])  # Get the directory part of the url
    try:
        # list all files in the directory recursively
        file_records = recursive_file_list(sftp, path, ext)
        # all folders were empty
        if not file_records:
            return [], [], 'skip_doy'
        matching_files, matching_files_fullpath = map(list, zip(*file_records))
        # Remove the redundant directory part and prepend the server URL
        matching_files_fullpath = [server_url + posixpath.relpath(path, dir_url) for path in matching_files_fullpath]
    except Exception as e:
        err_log.error(' Could not handle the exception from process_uruguay.get_rinex_list_historical: %s' % e)
        return None, None, 'abort_doy'
    finally:
        # close the SFTP session
        sftp.close()
        ssh.close()

    return matching_files, matching_files_fullpath, 'ok'


def recursive_file_list(sftp, path, ext):
    """
    Function to recursively list the files ending with the given extension in an SFTP directory tree
    (only subdirectories whose names contain no digits are entered).
    :param sftp: The open paramiko SFTP client.
    :param path: The directory path to start from.
    :param ext: The file extension to filter by.
    :return: List of tuples (file_name, directory_path) of matching files.
    """
    matching_files = []

    for item in sftp.listdir_attr(path):
        # use posixpath.join to ensure the use of forward-slashes
        item_path = posixpath.join(path, item.filename)

        if stat.S_ISDIR(item.st_mode):
            # item is a directory; recurse into this directory
            # only if the directory name contains no digits
            if not any(character.isdigit() for character in item.filename):
                matching_files.extend(recursive_file_list(sftp, item_path, ext))
        elif item_path.endswith(ext):
            # item is a file that ends with the specified extension
            matching_files.append((item.filename, posixpath.dirname(item_path)))  # Keep filename and directory path

    return matching_files
