import time
import subprocess
import shutil
import requests
from tqdm import tqdm
import multiprocessing
import datetime
import re
import pandas as pd
import logging
import os
import numpy as np
import sys
from geopy.geocoders import Nominatim
import pycountry
from math import pi, sqrt, cos, fabs, atan, atan2
import config, t_box
from compare import compare_rinex_log
from log import setup_log
from t_box import tools
from download import (download_cacs, download_igs, download_us_cors, download_epn, download_geoscience_australia,
                           download_unavco, download_uruguay, download_brazil_ibge, download_greenland)
from process import (process_cacs, process_igs, process_us_cors, process_geoscience_australia, process_epn,
                          process_unavco, process_uruguay, process_brazil_ibge, process_greenland, process_chile)

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def create_empty_df(pkl_year_dir):
    """
    Function to create an empty monthly DataFrame with the base columns and one boolean 'in_<network>' column per
    configured network. Creates the pickle directory if it does not exist.
    :param pkl_year_dir: The directory for the yearly pickle files (created if missing).
    :return: The empty DataFrame.
    """
    if not os.path.exists(pkl_year_dir):
        os.makedirs(pkl_year_dir)

    # prepare the column names for the networks
    network_columns = ['in_' + network for network in config.networks]

    # establish the rest of the columns
    base_columns = ['site_name', 'rinex_name', 'rinex_orig_name', 'rinex_download_dt', 'rinex_source', 'log_name',
                    'log_download_dt', 'log_source', 'in_repros', 'error_codes']

    # create the data frame with dynamic columns
    df_month = pd.DataFrame(columns=base_columns + network_columns)

    # set the type of the network columns to bool
    df_month[network_columns] = df_month[network_columns].astype(bool)

    return df_month


def chunks(lst, n):
    """
    Function to yield successive n-sized chunks from a list.
    :param lst: The list (or sequence) to split into chunks.
    :param n: The size of each chunk.
    :return: A generator yielding chunks of lst with up to n elements each.
    """
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def apply_stn_filter(stns_to_include, rnx_list):
    """
    Function to filter a RINEX list to only include files whose lowercase names contain any of the given station names.
    :param stns_to_include: List of (lowercase) station names to keep.
    :param rnx_list: The list of RINEX file names to filter.
    :return: The filtered list of RINEX file names.
    """
    res_log.warning(f' Filtering RINEX list to include {stns_to_include}')
    temp_r_list = []
    for rinex in rnx_list:
        if any(name in rinex.lower() for name in stns_to_include):
            temp_r_list.append(rinex)
    obs_rinex = temp_r_list
    return obs_rinex


def filter_obs_rinex(rnx_list, remote_dir_list, proc_year, proc_doy, ntwk):
    """
    Function to filter a RINEX list (and the matching remote directory list) to keep only files matching the
    processing year and day of year. Brazil IBGE *.zip files are kept without checking.
    :param rnx_list: The list of RINEX file names to filter.
    :param remote_dir_list: A list of remote directories (one per RINEX file) or a single remote directory string.
    :param proc_year: The processing year.
    :param proc_doy: The processing day of year.
    :param ntwk: The network name.
    :return: Tuple of the filtered RINEX list and the filtered remote directory list (or the remote directory string).
    """
    filter_remote_dir_flag = False  # initialize
    filtered_rnx_list = []
    if isinstance(remote_dir_list, list):
        filter_remote_dir_flag = True
        filtered_remote_dir_list = []
    else:
        remote_dir = remote_dir_list  # remote_dir_list is actually a string (one dir used for all RINEX files)

    for idx in range(len(rnx_list)):
        f_rinex = rnx_list[idx]
        if filter_remote_dir_flag:
            remote_dir = remote_dir_list[idx]
        try:
            if ntwk == 'brazil_ibge':
                # RINEX3 long filenames
                if '_' in f_rinex:
                    sf = f_rinex.split('_')
                    year = int(sf[2][:4])
                    doy = int(sf[2][4:7])
                    if year == proc_year and doy == proc_doy:
                        filtered_rnx_list.append(f_rinex)
                        if filter_remote_dir_flag:
                            filtered_remote_dir_list.append(remote_dir)
                    else:
                        err_log.warning(
                            f' RINEX {f_rinex} excluded from the {ntwk} download - RINEX DOY and year are not equal to '
                            f'{proc_doy} and {proc_year}')
                else:  # must be *.zip, DON't check for year and doy
                    filtered_rnx_list.append(f_rinex)
                    if filter_remote_dir_flag:
                        filtered_remote_dir_list.append(remote_dir)
            else:
                if len(f_rinex) > 30:
                    sf = f_rinex.split('_')
                    year = int(sf[2][:4])
                    doy = int(sf[2][4:7])
                    if year == proc_year and doy == proc_doy:
                        filtered_rnx_list.append(f_rinex)
                        if filter_remote_dir_flag:
                            filtered_remote_dir_list.append(remote_dir)
                    else:
                        err_log.warning(
                            f' RINEX {f_rinex} excluded from the {ntwk} download - RINEX DOY and year are not equal to '
                            f'{proc_doy} and {proc_year}')
                else:
                    if ntwk == 'uruguay':
                        sf = f_rinex.split('.')
                        doy = int(sf[0][4:7])
                        if doy == proc_doy:
                            filtered_rnx_list.append(f_rinex)
                            if filter_remote_dir_flag:
                                filtered_remote_dir_list.append(remote_dir)
                        else:
                            err_log.warning(
                                f' RINEX {f_rinex} excluded from the {ntwk} download - RINEX DOY are not equal to '
                                f'{proc_doy}')
                    else:
                        sf = f_rinex.split('.')
                        year = sf[1][:2]
                        if 80 < int(year) <= 99:
                            year = int('19' + year)
                        else:
                            year = int('20' + year)
                        doy = int(sf[0][4:7])
                        if year == proc_year and doy == proc_doy:
                            filtered_rnx_list.append(f_rinex)
                            if filter_remote_dir_flag:
                                filtered_remote_dir_list.append(remote_dir)
                        else:
                            err_log.warning(
                                f' RINEX {f_rinex} excluded from the {ntwk} download - RINEX DOY and year are not equal to '
                                f'{proc_doy} and {proc_year}')
        except ValueError:  # Raised when int conversion fails
            err_log.warning(
                f' RINEX {f_rinex} excluded from the download - DOY and year could not be converted to integers')
    if filter_remote_dir_flag:
        return filtered_rnx_list, filtered_remote_dir_list
    else:
        return filtered_rnx_list, remote_dir


def rinex_list_without_log_comp(df_mon, year, doy, network):
    """
    Function to get the sorted list of RINEX names from the DataFrame for a network, year and day of year that have
    no log file assigned.
    :param df_mon: The DataFrame containing the information for one month.
    :param year: The year.
    :param doy: The day of year.
    :param network: The network name.
    :return: The sorted list of RINEX names without a log file.
    """
    obs_rinex_from_df = df_mon[(df_mon[f'in_{network}']) &
                               df_mon['log_name'].isnull()]['rinex_name'].tolist()
    year_doy = str(year) + str(doy).zfill(3)
    obs_rinex_from_df_filtered = list(filter(lambda x: x.split("_")[2][:7] == year_doy, obs_rinex_from_df))
    obs_rinex_from_df_filtered_sorted = sorted(obs_rinex_from_df_filtered)

    return obs_rinex_from_df_filtered_sorted


def process_network(year, doy, df_mon, res_logger, err_logger, clear_log_handlers, network):
    """
    Function to process all RINEX files and log files of a network for a given year and day of year: gets and filters
    the RINEX list, downloads and compares RINEX headers with log files in parallel, and merges the results.
    Note: writes to the station CSV file and writes a comparison text file into the RINEX DOY directory.
    :param year: The year for which the RINEX files should be processed.
    :param doy: The day of year (DOY) for which the RINEX files should be processed.
    :param df_mon: The DataFrame containing the information for one month.
    :param res_logger: The result logger.
    :param err_logger: The error logger.
    :param clear_log_handlers: If True, clear the logger handlers and set up new daily loggers.
    :param network: The network name.
    :return: The final DataFrame with the results for the DOY, the unchanged df_mon if no RINEX files are found,
             or 'abort' if the RINEX list could not be retrieved.
    """
    redo_comp = config.correct_df_for_doy_logfile_info

    # Read stn table
    csv_file = config.stn_csv_path
    stn_df_init = pd.read_csv(csv_file, parse_dates=['latest_log_download_dt'])
    stn_df_init['latest_log_download_dt'] = pd.to_datetime(stn_df_init['latest_log_download_dt'])

    if clear_log_handlers:
        res_logger.handlers.clear()
        err_logger.handlers.clear()
        res_logger, err_logger = setup_log.write_dailylog()

    # Log the starting time
    current_time = datetime.datetime.now()
    res_logger.info(f' ==========================')
    res_logger.info(f' Processing {network} started {current_time:%Y-%m-%d %H:%M:%S}')

    # Get the list of files and remove duplicates and set paths
    if network == 'auspos':
        mixed_list = process_geoscience_australia.get_rinex_list_geoscience_australia(year, doy)
        obs_rinex = process_geoscience_australia.remove_duplicated_sites_from_sites_list(mixed_list)
        tmp_remote_dir = os.path.join(config.auspos_rinex_url_amazon, str(year) + '/' + str(doy).zfill(3) + '/')
        max_no_queries = multiprocessing.cpu_count()
        # max_no_queries = 1
    elif network == 'cacs':
        obs_rinex = process_cacs.get_rinex_list_cacsa(year, doy)
        tmp_remote_dir = os.path.join(config.cacs_rinex_url, str(year)[2:] + str(doy).zfill(3), str(year)[2:] + 'd/')
        max_no_queries = multiprocessing.cpu_count()
    # =====================================================
    elif network == 'igs':
        if redo_comp:
            obs_rinex = rinex_list_without_log_comp(df_mon, year, doy, network)
        else:
            obs_rinex = process_igs.get_rinex_list_igs(year, doy)
        tmp_remote_dir = os.path.join(config.igs_rinex_url, str(year) + '/' + str(doy).zfill(3), str(year)[2:] + 'o/')
        max_no_queries = multiprocessing.cpu_count()
        # max_no_queries = 1
    elif network == 'us_cors':
        obs_rinex = process_us_cors.get_rinex_list_aws(year, doy)  # with amazon
        tmp_remote_dir = os.path.join(config.us_cors_rinex_url_amazon,
                                      str(year) + '/' + str(doy).zfill(3) + '/')
        max_no_queries = multiprocessing.cpu_count()
        # max_no_queries = 8  # 32 cores can be used up to 2022?
    elif network == 'epn':
        if redo_comp:
            obs_rinex = rinex_list_without_log_comp(df_mon, year, doy, network)
        else:
            obs_rinex = process_epn.get_rinex_list_epn(year, doy)
        tmp_remote_dir = os.path.join(config.epn_rinex_url,
                                      str(year) + '/' + str(doy).zfill(3) + '/')
        max_no_queries = multiprocessing.cpu_count()
        # max_no_queries = 1
    elif network == 'unavco':
        obs_rinex = process_unavco.f_list_unavco(config.unavco_rinex_url + str(year) + '/'
                                                 + str(doy).zfill(3) + '/', 'd.Z')
        tmp_remote_dir = os.path.join(config.unavco_rinex_url,
                                      str(year) + '/' + str(doy).zfill(3) + '/')
        max_no_queries = multiprocessing.cpu_count()
        # max_no_queries = 8
    elif network == 'uruguay':
        obs_rinex, tmp_remote_dir = process_uruguay.get_rinex_list(year, doy)
        # max_no_queries = multiprocessing.cpu_count()
        max_no_queries = 4
    elif network == 'brazil_ibge':  #
        f_gz, f_zip = process_brazil_ibge.get_rinex_list_brazil_ibge(year, doy)
        s_list = process_brazil_ibge.get_brazil_ibge_site_name_list(year, doy)
        if f_gz is None or f_zip is None or s_list is None:
            obs_rinex = None
        else:
            obs_rinex = process_brazil_ibge.merge_gz_zip_lists(f_gz, f_zip, s_list)
        tmp_remote_dir = ''  # due to IBGE specifics, the dir name will be assigned in download_brazil_ibge_rinex_file()
        max_no_queries = 8
        # max_no_queries = 1
    elif network == 'greenland':
        obs_rinex, tmp_remote_dir = process_greenland.get_rinex_list_and_remote_dir_list(year, doy)
        # max_no_queries = multiprocessing.cpu_count()
        max_no_queries = 4
    elif network == 'chile':
        tmp_remote_dir = os.path.join(config.chile_rinex_url, str(year), str(doy).zfill(3))
        if config.download_chile:
            obs_rinex = process_chile.get_chile_file_list(tmp_remote_dir)
            max_no_queries = 1
        else:
            tmp_local_dir = os.path.join(config.chile_rinex_temp_down_path, str(year), str(doy).zfill(3))
            obs_rinex = process_chile.file_list_from_local_dir(tmp_local_dir)
            #max_no_queries = multiprocessing.cpu_count()
            max_no_queries = 1
    else:
        err_log.error(f' Network {network} not recognized.')
        exit()

    if obs_rinex is None:
        # Previously used (not aborting):
        # err_log.error(f' Could not retrieve RINEX list for {network}. Skipping this day for {network}...')
        # return df_year

        # Aborting
        err_log.error(f' Could not retrieve RINEX list for {network}. Aborting...')
        return 'abort'

    if not obs_rinex:
        err_log.warning(f' RINEX list empty for {network}. Skipping this day for {network}...')
        return df_mon

    if network != 'chile':
        obs_rinex, tmp_remote_dir = filter_obs_rinex(obs_rinex, tmp_remote_dir, year, doy, network)
    # Optional: Apply filter based on a list containing 4-char station name(s)
    # obs_rinex = apply_stn_filter(['ankr', 'joze'], obs_rinex)

    if not obs_rinex:
        err_log.warning(f' There were no RINEX files for {network} after filtering based on year and DOY value')
        return df_mon

    # Setup paths
    tmp_down_path = os.path.join(config.rinex_archive_path, str(year), str(doy).zfill(3))
    if not os.path.exists(tmp_down_path):
        os.makedirs(tmp_down_path)

    # Convert DataFrame column to set for quick lookups and make all entries lowercase,
    # include only entries for this DOY
    target_sub_string = str(year) + str(doy).zfill(3)
    # split the string x into parts by underscore and take the third part (index starts from 0).
    # target_sub_string in x.split('_')[2] checks if this part contains target year and day of year.
    # If it does - the element is included in the list, otherwise - it's not.
    rinex_names_set = set(
        [x for x in df_mon['rinex_name'].str.lower().apply(lambda x: re.search('(.*)\.', x).group(1)) if
         target_sub_string in x.split('_')[2]])

    rinex_names_set_w_ext = set([x for x in df_mon['rinex_name'].str.lower() if target_sub_string in x.split('_')[2]])

    sites_to_download = [file[:4].upper() for file in obs_rinex]  # for logfiles 4char sitenames must be uppercase

    files_for_multi_download = list(chunks(range(len(obs_rinex)), max_no_queries))

    df_results = []
    df_stn_results = []
    total_new_cnt = 0
    total_upd_cnt = 0
    total_excl_cnt = 0

    try:
        for batch in files_for_multi_download:
            with multiprocessing.Pool(max_no_queries) as p:
                desc = (f' Processing RINEXes and logfiles from {sites_to_download[batch[0]]} to '
                        f'{sites_to_download[batch[-1]]}')

                async_results = [p.apply_async(part_process,
                                               args=(sites_to_download, rinex_names_set, rinex_names_set_w_ext, df_mon,
                                                     stn_df_init, obs_rinex, tmp_remote_dir, year, doy, idx, network))
                                 for idx in range(batch[0], batch[-1] + 1)]
                pbar = tqdm(total=len(async_results), desc=desc)

                # process the results and write log strings
                for result in async_results:
                    df, stn_df, update_flag, new_cnt, upd_cnt, excl_cnt, abort = result.get()
                    # None, None, False, 0, 0, 1, False
                    if abort:
                        sys.exit()
                    total_new_cnt += new_cnt
                    total_upd_cnt += upd_cnt
                    total_excl_cnt += excl_cnt
                    # res_logger.info(f' %s' % log_strings)
                    if df is not None:
                        if not update_flag:  # New DataFrame should be appended
                            df_results.append(df)
                            if stn_df is not None:
                                df_stn_results.append(stn_df)

                        else:  # DataFrame contains upgrades for df_year
                            for idx, row in df.iterrows():
                                df_mon.loc[idx] = row
                            if config.correct_df_for_doy_logfile_info:
                                if stn_df is not None:
                                    df_stn_results.append(stn_df)

                    # update progress bar
                    pbar.update(1)
                pbar.close()

    except Exception as e:
        err_logger.error(f' Error in batch processing loop: {str(e)}')

    if df_results:  # Not an empty list
        df_day = pd.concat(df_results, ignore_index=True)
        final_df = pd.concat([df_mon, df_day], ignore_index=True)
        stn_df_day = pd.concat(df_stn_results, ignore_index=True)
        write_to_stn_csv(stn_df_day)

    else:
        if config.correct_df_for_doy_logfile_info:
            stn_df_day = pd.concat(df_stn_results, ignore_index=True)
            write_to_stn_csv(stn_df_day)
        res_logger.info(f' No new RINEX files were found.')
        final_df = df_mon
        stn_df_day = stn_df_init

    df_doy_filt = final_df[final_df['rinex_name'].str.contains(str(year) + str(doy).zfill(3))]
    comp_log_path = os.path.join(config.rinex_archive_path, str(year), str(doy).zfill(3),
                                 f'comparing_log_rinex_{str(year)}_{str(doy).zfill(3)}.txt')
    df_doy_filt_sorted = df_doy_filt.sort_values(by='rinex_name')

    header = tools.get_header_txt(config.rinex_logfile_header_file)
    with open(comp_log_path, 'w') as fo:
        fo.write(''.join(header))

    with open(comp_log_path, 'a') as fo:
        df_doy_filt_sorted[['rinex_name', 'log_name', 'in_repros', 'error_codes']].to_csv(fo, sep='|', index=False,
                                                                                          header=False)

    # Calculate elapsed time
    e_time = datetime.datetime.now()
    elapsed_minutes = (e_time - current_time).total_seconds() / 60

    res_logger.info(f' {network} RINEX for Year {year} and DOY {doy} completed and lasted '
                    f'{elapsed_minutes:.1f} minutes')
    res_logger.info(
        f'    # New RINEXes downloaded and processed: {total_new_cnt}')  # swapping rnx for crx does not count
    res_logger.info(
        f'    # Duplicate RINEXes found: {total_upd_cnt}')  # such files were already present before (incl. swapping rnx for crx)
    res_logger.info(f'    # RINEXes downloaded but not processed: {total_excl_cnt}')  # XYZ error in header

    return final_df


def prepare_row_to_update(df_mon, rinex_filename, rinex_origname, rinex_lc_wo_gz_z, network, update_code,
                          diff_res_fn_present):
    """
    Function to copy the DataFrame row of an already present RINEX file and prepare it for update: sets the current
    network flag to True and, depending on the update code, logs the reason and swaps .rnx for .crx.
    :param df_mon: The DataFrame containing the information for one month.
    :param rinex_filename: The RINEX file name.
    :param rinex_origname: The original RINEX file name.
    :param rinex_lc_wo_gz_z: The lowercase RINEX file name without .gz or .Z extension.
    :param network: The network name.
    :param update_code: The update code (1: duplicate not downloaded, 2: comparison already made, 3: swap .rnx for
                        .crx, 4: comparison made using a RINEX with different resolution).
    :param diff_res_fn_present: The name of the already present RINEX with different resolution (used for code 4).
    :return: The DataFrame row(s) to update, or None if an error occurs.
    """
    try:
        r_wo_ext = rinex_lc_wo_gz_z.split('.', 1)[0]
        if update_code != 4:
            # Make a copy of the row for this RINEX from DataFrame.
            row_to_update = df_mon.loc[df_mon['rinex_name'].str.lower().str.contains(r_wo_ext, regex=False)].copy()
        else:
            # Make a copy of the row for this RINEX from DataFrame using RINEX already present for this DOY and station
            # but with different resolution.
            row_to_update = df_mon.loc[
                df_mon['rinex_name'].str.lower().str.contains(diff_res_fn_present, regex=False)].copy()

        if config.correct_df_for_doy_logfile_info:
            return row_to_update

        current_ntwk_presence_flag = row_to_update[f'in_{network}'].iloc[0]

        if update_code == 1:
            if not current_ntwk_presence_flag:
                string_to_res_log = (f' RINEX {rinex_filename} will not be downloaded to avoid duplicates. '
                                     f'Setting {network}=True instead.')
            else:
                string_to_res_log = (f' RINEX {rinex_filename} will not be downloaded to avoid duplicates. '
                                     f'Already {network}=True.')
        elif update_code == 2:
            if not current_ntwk_presence_flag:
                string_to_res_log = (f' Comparison of {rinex_filename} and logfile already made. Skipping comparison. '
                                     f'Setting {network}=True instead.')
            else:
                string_to_res_log = (f' Comparison of {rinex_filename} and logfile already made. Skipping comparison. '
                                     f'Already {network}=True.')
        elif update_code == 3:
            if not current_ntwk_presence_flag:
                string_to_res_log = (f' Comparison of {rinex_filename} and logfile already made. Skipping comparison. '
                                     f'Setting {network}=True instead. Swapping .rnx file for .crx')
            else:
                string_to_res_log = (f' Comparison of {rinex_filename} and logfile already made. Skipping comparison. '
                                     f'Already {network}=True. Swapping .rnx file for .crx')
            file_without_ext = os.path.splitext(rinex_lc_wo_gz_z)[0].upper()
            row_to_update['rinex_name'] = file_without_ext + '.crx'
            row_to_update['rinex_source'] = network
            row_to_update['rinex_orig_name'] = rinex_origname
            row_to_update['rinex_download_dt'] = datetime.datetime.now()

        elif update_code == 4:
            if not current_ntwk_presence_flag:
                string_to_res_log = (f' Comparison of {rinex_filename} and logfile not made. '
                                     f'However, comparison using {diff_res_fn_present} made. Skipping comparison. '
                                     f'Setting {network}=True instead.')
            else:
                string_to_res_log = (f' Comparison of {rinex_filename} and logfile not made. '
                                     f'However, comparison using {diff_res_fn_present} made. Skipping comparison. '
                                     f'Already {network}=True.')

        res_log.info(f'{string_to_res_log}')

        # Set current network True for this RINEX in the copied row.
        row_to_update[f'in_{network}'] = True

        return row_to_update
    except Exception as e:
        err_log.error(f' prepare_row_to_update gives {e}')


def get_lc_rnx_name_without_ext(rinex_filename):
    """
    Function to get the lowercase RINEX file name with any .Z or .gz extension removed.
    :param rinex_filename: The RINEX file name.
    :return: The lowercase RINEX file name without .Z or .gz, or None if an error occurs.
    """
    try:
        if rinex_filename.endswith('.Z') or rinex_filename.endswith('.gz'):
            # os.path.splitext() method splits the path into root and extension
            base_name = os.path.splitext(rinex_filename)[0]
            return base_name.lower()
        return rinex_filename.lower()  # return the original name without .Z or .gz
    except Exception as e:
        err_log.error(f' get_lc_rnx_name_without_ext gives {e}')


def part_process(site_list, rinex_names_set, rinex_names_set_w_ext, df_year, stn_df, file_list,
                 remote_path, current_year, current_doy, file_index, network):
    """
    Function to process one RINEX file of a network: downloads it (unless already present), compares its header with
    the site log file, and builds the result rows. May delete duplicate RINEX/log files.
    :param site_list: List of 4-character site names.
    :param rinex_names_set: Set of lowercase RINEX names (without extension) already in the DataFrame for this DOY.
    :param rinex_names_set_w_ext: Set of lowercase RINEX names (with extension) already in the DataFrame for this DOY.
    :param df_year: The DataFrame containing the already processed RINEX information.
    :param stn_df: The station table DataFrame.
    :param file_list: List of RINEX file names.
    :param remote_path: The remote path (string or list of paths per file).
    :param current_year: The processing year.
    :param current_doy: The processing day of year.
    :param file_index: Index of the file to process.
    :param network: The network name.
    :return: Tuple (RINEX DataFrame/row, station DataFrame, update flag, new count, update count, excluded count,
             abort flag).
    """

    site_name = site_list[file_index]
    log_names_set = set(stn_df['latest_log_name'].dropna())
    rinex_fn = file_list[file_index]
    rinex_orig_name = rinex_fn
    rinex_local_directory = os.path.join(config.rinex_archive_path, str(current_year),
                                         str(current_doy).zfill(3))

    rinex_without_extension = rinex_fn.lower().split('.', 1)[0]  # gives e.g. aut000usa_r_20132380000_01d_00u_mo

    if config.correct_df_for_doy_logfile_info:
        rnx_lc_fn_wo_gz_or_z = get_lc_rnx_name_without_ext(rinex_fn)
        row_to_update = prepare_row_to_update(df_year, rinex_fn, rinex_orig_name, rnx_lc_fn_wo_gz_or_z,
                                              network, 1, '')
        r_path = compare_rinex_log.get_rinex_dir(current_year, current_doy, config.rinex_archive_path)
        full_rinex_path = os.path.join(r_path, rinex_fn)
        rinex_lines, unzipped_rinex_fn = compare_rinex_log.readlines_zipped(full_rinex_path)

    else:
        # check if such RINEX is already in the dataframe
        # use the original filename, but neglect file extensions (.Z, .gz, .crx and .rnx)
        if rinex_without_extension in rinex_names_set:
            rnx_lc_fn_wo_gz_or_z = get_lc_rnx_name_without_ext(rinex_fn)
            if rnx_lc_fn_wo_gz_or_z not in rinex_names_set_w_ext and '.crx' in rnx_lc_fn_wo_gz_or_z:
                # there is .rnx file with the same name in GREP - has to be replaced with current .crx file,
                # continue with the download
                pass
            else:
                # Neglecting extension, such file is already present in GREP and the current file is not Compact RINEX,
                # nothing needs to be done, except setting True for the current network (if not True already)
                row_to_update = prepare_row_to_update(df_year, rinex_fn, rinex_orig_name, rnx_lc_fn_wo_gz_or_z,
                                                      network, 1, '')
                return row_to_update, None, True, 0, 1, 0, False  # Return the row to be updated

        if network == 'auspos':
            # rinex_downloaded = download_geoscience_australia.download_rinex_files_web_api(rinex_fn, remote_path,
            #                                                                              rinex_local_directory)
            unzipped_rinex_fn = download_geoscience_australia.download_rinex_files_amazon(rinex_fn, remote_path,
                                                                                         rinex_local_directory)
        elif network == 'cacs':
            unzipped_rinex_fn = download_cacs.download_rinex_files(rinex_fn, remote_path, rinex_local_directory)
        elif network == 'igs':
            unzipped_rinex_fn = download_igs.download_rinex_files(rinex_fn, remote_path, rinex_local_directory)
        elif network == 'us_cors':
            unzipped_rinex_fn = download_us_cors.download_rinex_files_us_cors(rinex_fn, remote_path,
                                                                             rinex_local_directory)
        elif network == 'epn':
            unzipped_rinex_fn = download_epn.download_rinex_files_epn(rinex_fn, remote_path, rinex_local_directory)
        elif network == 'unavco':
            unzipped_rinex_fn = download_unavco.download_rinex_file_unavco(rinex_fn, remote_path,
                                                                          rinex_local_directory)
        elif network == 'uruguay':
            if 'sftp://' in remote_path[file_index]:
                unzipped_rinex_fn = download_uruguay.download_rinex_files_sftp(rinex_fn, remote_path[file_index],
                                                                              rinex_local_directory)
            else:
                unzipped_rinex_fn = download_uruguay.download_rinex_files_ftp(rinex_fn, remote_path[file_index],
                                                                             rinex_local_directory)
        elif network == 'brazil_ibge':
            unzipped_rinex_fn = download_brazil_ibge.download_brazil_ibge_rinex_file(rinex_fn,
                                                                                     remote_path,
                                                                                     rinex_local_directory,
                                                                                     current_year,
                                                                                     current_doy)
        elif network == 'greenland':
            unzipped_rinex_fn = download_greenland.download_rinex_file_greenland(rinex_fn, remote_path[file_index],
                                                                                rinex_local_directory)
        elif network == 'chile':
            if config.download_chile:
                process_chile.download_rinex_csn(current_year, current_doy, current_doy)
            local_file_path = (
                os.path.join(config.chile_rinex_temp_down_path, str(current_year), str(current_doy).zfill(3)))
            rinex_lines, unzipped_rinex_fn = (
                compare_rinex_log.readlines_zipped(os.path.join(local_file_path, rinex_fn), get_only_path=True))
            shutil.copy2(os.path.join(local_file_path, unzipped_rinex_fn), rinex_local_directory)
            res_log.info(f'Chile RINEX file {unzipped_rinex_fn} copied to {rinex_local_directory}')
        else:
            err_log.error(f' The scripts are not implemented for network {network}')
            exit()

    if unzipped_rinex_fn:
        # to avoid *.zip file names from IBGE, use RINEX file names returned from download_brazil_ibge_rinex_file()
        # if network == 'brazil_ibge':
        #     rinex_fn = brazilian_file
        # line_to_log, row_to_stn_tab, f_rinex_long, False, log_file, log_download_dt, site_name_9char
        (line_to_log, row_to_stn_tab, rinex_fn, rnx_not_new, log_file, log_download_dt, site_name_9char,
         log_source, abort_bool, rinexname_with_diff_res_present) = \
            (compare_rinex_log.process_header_and_logfile(current_year, current_doy, unzipped_rinex_fn, rinex_names_set,
                                                          rinex_names_set_w_ext, stn_df, network))
        if abort_bool:
            return None, None, False, 0, 0, 1, True
        if rnx_not_new:
            # we do not need the logfile that was just downloaded if it is not listed in log_name column
            if log_file and log_file not in log_names_set:
                os.remove(config.logfile_archive_path + log_file)
                res_log.info(f" Logfile {log_file} deleted - another logfile for {site_name_9char} already present")

            rnx_lc_fn_wo_gz_or_z = get_lc_rnx_name_without_ext(rinex_fn)
            if rinexname_with_diff_res_present:
                row_to_update = prepare_row_to_update(df_year, rinex_fn, rinex_orig_name, rnx_lc_fn_wo_gz_or_z,
                                                      network, 4, rinexname_with_diff_res_present)
                delete_rnx(rnx_lc_fn_wo_gz_or_z, current_year, current_doy, False)
                return row_to_update, None, True, 0, 1, 0, False  # Return the row to be updated
            elif rnx_lc_fn_wo_gz_or_z not in rinex_names_set_w_ext and '.crx' in rnx_lc_fn_wo_gz_or_z:
                # there is .rnx file with the same name in GREP - has to be replaced with current .crx file,
                row_to_update = prepare_row_to_update(df_year, rinex_fn, rinex_orig_name, rnx_lc_fn_wo_gz_or_z,
                                                      network, 3, '')
                delete_rnx(rnx_lc_fn_wo_gz_or_z, current_year, current_doy, 'rnx')  # delete rnx (keep crx)
                return row_to_update, None, True, 0, 1, 0, False  # Return the row to be updated
            else:
                # Neglecting crx/rnx, such file is already present in GREP - setting True for the current network
                # (if not True already). If the current file is rnx, and the crx file exists in rinex_name column,
                # then delete the current rnx. If the current file is crx then it is a repeating crx at this point and
                # the respective rnx is already deleted by the previous cycle for another network
                # (if the rnx existed at all)
                row_to_update = prepare_row_to_update(df_year, rinex_fn, rinex_orig_name, rnx_lc_fn_wo_gz_or_z,
                                                      network, 2, '')
                w_test = rnx_lc_fn_wo_gz_or_z.replace('.rnx', '.crx')
                if rnx_lc_fn_wo_gz_or_z.replace('.rnx', '.crx') in rinex_names_set_w_ext:
                    delete_rnx(rnx_lc_fn_wo_gz_or_z, current_year, current_doy, 'rnx')  # delete rnx (keep crx)
                return row_to_update, None, True, 0, 1, 0, False  # Return the row to be updated

        if line_to_log is None or site_name_9char is None:
            return None, None, False, 0, 0, 1, False

        # Set True only for the respective network
        network_dict = {f'in_{n}': n == network for n in config.networks}

        df_rinex = pd.DataFrame({
            'site_name': [site_name_9char],
            'rinex_name': [rinex_fn],
            'rinex_orig_name': [rinex_orig_name],
            'rinex_download_dt': [datetime.datetime.now()],
            'rinex_source': [network],
            'log_name': [log_file],
            'log_download_dt': [log_download_dt],
            'log_source': [log_source],
            'in_repros': [line_to_log[0]],
            'error_codes': [line_to_log[1]],
            **network_dict
        })
        df_stn_tab = pd.DataFrame({
            'site_name': [site_name],
            'country_code': [row_to_stn_tab[0]],
            'lat': [row_to_stn_tab[1]],
            'lon': [row_to_stn_tab[2]],
            'elev': [row_to_stn_tab[3]],
            'x': [row_to_stn_tab[4]],
            'y': [row_to_stn_tab[5]],
            'z': [row_to_stn_tab[6]],
            'site_name_9char': [row_to_stn_tab[7]],
            'latest_log_name': [row_to_stn_tab[8]],
            'latest_log_download_dt': [row_to_stn_tab[9]],
            'latest_log_source': [row_to_stn_tab[10]],
        })

        # prepare the column names
        column_names = ['in_' + network for network in config.networks]

        # dynamically adjust columns in dataframe based on networks list
        df_rinex[column_names] = df_rinex[column_names].astype(bool)

        if config.correct_df_for_doy_logfile_info:
            row_to_update['log_name'] = log_file
            row_to_update['log_download_dt'] = log_download_dt
            row_to_update['log_source'] = log_source
            row_to_update['error_codes'] = line_to_log[1]

            return row_to_update, df_stn_tab, True, 0, 1, 0, False
        else:
            return df_rinex, df_stn_tab, False, 1, 0, 0, False
    else:
        # err_log.error(' Max retries reached for %s from %s - skipping this RINEX...' % (file_list[file_index], network))
        return None, None, False, 0, 0, 1, False


def delete_rnx(rnx_lc_fn_wo_gz_or_z, year, doy, del_by_ext):
    """
    Function to delete a RINEX file (and its .gz version), if present, in the RINEX archive folder of the given DOY.
    :param rnx_lc_fn_wo_gz_or_z: The lowercase RINEX file name without .gz or .Z extension.
    :param year: The year.
    :param doy: The day of year.
    :param del_by_ext: If truthy, delete the .rnx version of the file; otherwise delete the file with its own extension.
    :return: None.
    """
    rinex_local_directory = os.path.join(config.rinex_archive_path, str(year),
                                         str(doy).zfill(3))
    if del_by_ext:
        # Getting filename without extension and converting it to uppercase.
        file_without_ext = os.path.splitext(rnx_lc_fn_wo_gz_or_z)[0].upper()
        delete_rnx_name = file_without_ext + '.rnx'
    else:
        file_ext = os.path.splitext(rnx_lc_fn_wo_gz_or_z)[1]
        file_without_ext = os.path.splitext(rnx_lc_fn_wo_gz_or_z)[0].upper()
        delete_rnx_name = file_without_ext + file_ext

    if os.path.isfile(os.path.join(rinex_local_directory, delete_rnx_name)):
        os.remove(os.path.join(rinex_local_directory, delete_rnx_name))
        res_log.info(f" {delete_rnx_name} deleted")

    delete_rnx_name_gz = delete_rnx_name + '.gz'
    if os.path.isfile(os.path.join(rinex_local_directory, delete_rnx_name_gz)):
        os.remove(os.path.join(rinex_local_directory, delete_rnx_name_gz))
        res_log.info(f" {delete_rnx_name_gz} deleted")
    # else:
    #     err_log.error(f" Could not remove {delete_rnx_name_gz}: file does not exist")


def write_to_stn_csv(new_stn_df):
    """
    Function to write station data to the station CSV file. If the file exists, the new data is merged, duplicates
    (by site_name and country_code) are dropped keeping the latest, and the result is sorted and saved.
    :param new_stn_df: The DataFrame with new station data.
    :return: None.
    """
    csv_file = config.stn_csv_path

    # Check if the directory exists, and if not, create the directory
    if not os.path.exists(os.path.dirname(csv_file)):
        os.makedirs(os.path.dirname(csv_file))

    if not os.path.isfile(csv_file):
        # if file doesn't exist, save the DataFrame to CSV
        new_stn_df.to_csv(csv_file, index=False)
    else:
        # if file exists, read the CSV file into a DataFrame
        df = pd.read_csv(csv_file)

        # Concatenate the two dataframes
        combined_df = pd.concat([df, new_stn_df])

        # Keep only the unique rows, based on 'site_name' and 'country_code'
        final_df = combined_df.drop_duplicates(subset=['site_name', 'country_code'], keep='last')

        # sort df by the first column
        final_df = final_df.sort_values(by=final_df.columns[0])

        # Convert the 'log_download_dt' column to datetime
        final_df['latest_log_download_dt'] = pd.to_datetime(final_df['latest_log_download_dt'])

        # Format the 'log_download_dt' column and convert it back to string
        final_df['latest_log_download_dt'] = final_df['latest_log_download_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')

        # save df to CSV
        final_df.to_csv(csv_file, index=False)


def read_stn_csv_as_df():
    """
    Function to read the station CSV file into a DataFrame.
    :return: The station DataFrame.
    """
    csv_file = config.stn_csv_path
    df = pd.read_csv(csv_file)
    return df


def load_or_download_log_file(site_name_4char, site_name_9char, stn_df, current_year, current_doy, network):
    """
    Function to get the log file for a site: downloads a new log file if the site is not yet in the station table
    (or has no log file when correcting), otherwise loads the existing one.
    :param site_name_4char: The 4-character site name.
    :param site_name_9char: The 9-character site name.
    :param stn_df: The station table DataFrame.
    :param current_year: The processing year.
    :param current_doy: The processing day of year.
    :param network: The network name.
    :return: Tuple of log file name, log download datetime and log source.
    """
    current_date_string = datetime.datetime.now().strftime('%Y-%m-%d')
    proc_date = datetime.datetime(current_year, 1, 1) + datetime.timedelta(current_doy - 1)
    sites_downloaded = set(stn_df['site_name_9char'])

    if site_name_9char not in sites_downloaded:
        return download_new_log_file(site_name_4char, current_date_string, proc_date, network)
    else:
        # force to download logfile (in stn_table.csv latest_log_name == None),
        if config.correct_df_for_doy_logfile_info:
            filtered_stn_df = stn_df[stn_df['latest_log_name'].isnull()]
            sites_without_log = set(filtered_stn_df['site_name_9char'])
            if site_name_9char in sites_without_log:
                return download_new_log_file(site_name_4char, current_date_string, proc_date, network)
            else:
                return load_existing_log_file(site_name_4char, site_name_9char, stn_df, current_year, current_doy,
                                              current_date_string, network)
        else:
            return load_existing_log_file(site_name_4char, site_name_9char, stn_df, current_year, current_doy,
                                          current_date_string, network)


def load_existing_log_file(site_name_4char, site_name_9char, stn_df, current_year, current_doy, current_date_string,
                           network):
    """
    Function to get the latest log file for a site from the station table, or download a newer one if the existing
    log is older than the processing date.
    :param site_name_4char: The 4-character site name.
    :param site_name_9char: The 9-character site name.
    :param stn_df: The station table DataFrame.
    :param current_year: The processing year.
    :param current_doy: The processing day of year.
    :param current_date_string: The current date string (YYYY-MM-DD).
    :param network: The network name.
    :return: Tuple of log file name, log download datetime and log source, or (None, None, None) if not available.
    """
    if current_year < config.proc_split_year:
        if site_name_4char.upper() == 'PAMA':
            return None, None, None

    stn_df_filtered = stn_df[(stn_df['site_name_9char'] == site_name_9char) &
                             (stn_df['latest_log_name'].notnull())]
    if stn_df_filtered.shape[0] > 0:
        max_date = stn_df_filtered['latest_log_download_dt'].iat[0]
        if isinstance(max_date, str):
            max_date = datetime.datetime.strptime(max_date, '%Y-%m-%d %H:%M:%S.%f')
        proc_date = datetime.datetime.strptime(f'{current_year}-{str(current_doy).zfill(3)}',
                                               '%Y-%j')
        if proc_date > max_date:  # check if log is considered as too old
            res_log.info(f' Log file for {site_name_9char} too old. Downloading a newer log.')
            proc_date = datetime.datetime(current_year, 1, 1) + datetime.timedelta(current_doy - 1)
            log_file, log_download_dt, log_source = download_new_log_file(site_name_4char, current_date_string,
                                                                          proc_date, network)

        else:
            # Find rows where 'log_download_dt' equals max_date for the station defined
            rows_with_max_date = stn_df_filtered[stn_df_filtered['latest_log_download_dt'] == max_date]
            # Get 'log_name' and 'log_source' from the first row of the filtered DataFrame
            log_file = rows_with_max_date['latest_log_name'].iloc[0]
            log_source = rows_with_max_date['latest_log_source'].iloc[0]
            log_download_dt = max_date
        return log_file, log_download_dt, log_source
    else:  # all the sites' RINEXes are without log file
        return None, None, None


def download_new_log_file(site_4char, current_date, proc_date, network):
    """
    Function to download a new log file for a site using the network-specific download function.
    :param site_4char: The 4-character site name.
    :param current_date: The current date string.
    :param proc_date: The processing date (datetime).
    :param network: The network name.
    :return: Tuple of log file name, log download datetime and log source (None values for chile), or None for an
             unknown network.
    """
    if network == 'auspos':
        return download_geoscience_australia.get_site_logfiles_auspos(site_4char, current_date, proc_date)
    elif network == 'cacs':
        return download_cacs.get_site_logfiles_cacs(site_4char)
    elif network == 'igs':
        return download_igs.get_site_logfiles_igs(site_4char)
    elif network == 'us_cors':
        return download_us_cors.get_site_logfile_us_cors_aws(site_4char)
    elif network == 'epn':
        return download_epn.get_site_logfile_epn(site_4char)
    elif network == 'unavco':
        return download_unavco.get_site_logfile_unavco(site_4char)
    elif network == 'uruguay':
        return download_uruguay.get_site_logfile_uruguay(site_4char)
    elif network == 'brazil_ibge':
        return download_brazil_ibge.get_site_logfile_brazil_ibge(site_4char)
    elif network == 'greenland':
        return download_greenland.get_site_logfile_greenland(site_4char)
    elif network == 'chile':
        return None, None, None
    else:
        err_log.error(f'Unknown network used in download_new_log_file: {network}')


def check_first_logfile_name(fname, fname_end_str_list, fname_max_len, ntwk):
    """
    Function to check that the first log file name in a list ends with one of the expected strings and is not too long.
    :param fname: The file name to check.
    :param fname_end_str_list: List of allowed file name endings.
    :param fname_max_len: The maximum allowed length of the file name.
    :param ntwk: The network name.
    :return: None if the check passes, otherwise the string 'logfile list error'.
    """
    fname_len = len(fname)
    if any(fname.endswith(end_str) for end_str in fname_end_str_list) and fname_len <= fname_max_len:
        return None
    else:
        end_str_printable = ", ".join(
            f'"{str_}"' for str_ in fname_end_str_list)  # Join list items into a printable string
        err_log.error(f' The first element in {ntwk} logfile list does not end with any of '
                      f'[{end_str_printable}] or the length of the text string > {fname_max_len}. Exiting...')
        return 'logfile list error'


def cartesian2geodetic(x, y, z):
    """
    Function to convert ECEF cartesian coordinates to WGS84 geodetic latitude, longitude and ellipsoidal height using
    the improved Bowring method (Toms, 1995).
    :param x: The X coordinate in meters.
    :param y: The Y coordinate in meters.
    :param z: The Z coordinate in meters.
    :return: List [lat, lon, ele] with lat/lon in degrees (lon in 0-360) and ele in meters, or None on division by zero.
    """
    try:
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
        if lon < 0:
            lon += 360
        return [lat, lon, ele]
    except ZeroDivisionError as e:  # either all or one value for XYZ has been ZERO
        # err_log.error(f' Zero values for XYZ in cartesian2geodetic. Error: {e}')
        return None


def get_country(sitename, lat, lon):
    """
    Function to get the 3-character country code for a location using a Nominatim reverse geocoding query.
    :param sitename: The site name (used for logging).
    :param lat: The latitude in degrees.
    :param lon: The longitude in degrees.
    :return: The 3-character (uppercase) country code, or None if it could not be determined.
    """
    try:
        geolocator = Nominatim(user_agent="gnss_data", timeout=10)
        lat_lon_str = str(lat) + ', ' + str(lon)
        location = geolocator.reverse(lat_lon_str, exactly_one=True)
        if location is None:
            err_log.error(f'Possibly unrealistic land coordinates {lat_lon_str} for site {sitename}')
            return None
        address = location.raw['address']
        if address == {}:
            err_log.error(f" Could not get country code for {sitename} using lat={lat:.3f}, lon={lon:.3f}. "
                          f"Add country code manually in generate_long_filename()")
            return None

        country_code = address.get('country_code', '')
        country = get_alpha_3(country_code)
        return country

    except Exception as e:
        err_log.error(f" get_country for site {sitename} gave an error: {e}")
        return None


def get_alpha_3(alpha_2):
    """
    Function to convert a 2-character country code to a 3-character country code.
    :param alpha_2: The 2-character country code.
    :return: The 3-character country code, or an 'Invalid code: ...' string if not found.
    """
    try:
        country = pycountry.countries.get(alpha_2=alpha_2)
        return country.alpha_3
    except AttributeError:
        return f"Invalid code: {alpha_2}"


def check_stn_presence(stn, lat, lon):
    """
    Function to look up the country code of a station in the station CSV file, matching the site name and lat/lon
    within a tolerance of 2 degrees.
    :param stn: The site name.
    :param lat: The latitude in degrees.
    :param lon: The longitude in degrees.
    :return: The country code prefixed with '00', or None if not found or the CSV file does not exist.
    """
    if os.path.exists(config.stn_csv_path):  # not yet created (but will be created at the end of the current daily run)
        df = read_stn_csv_as_df()
        # Define the tolerance
        tolerance = 2

        # Check if `element1` is in column1 and `element2` and `element3` are within +/-2 of column3 and column4 in the respective row
        mask = (df['site_name'] == stn) & \
               (np.abs(df['lat'] - lat) <= tolerance) & \
               (np.abs(df['lon'] - lon) <= tolerance)

        # Apply the mask to get the rows that match the conditions
        result_df = df[mask]

        # If result_df has any rows, it means the conditions were met for those entries
        if result_df.empty:
            res_log.info(f" No country code found in {os.path.basename(config.stn_csv_path)} for station {stn}, "
                         f"lat {lat:.2f}, lon {lon:.2f}. Making a Nominatim query...")
            return None
        else:
            cc = result_df.iloc[0]['country_code']
            res_log.info(f" Country code {cc} found in {os.path.basename(config.stn_csv_path)} for station {stn}, "
                         f"lat {lat:.2f}, lon {lon:.2f}. Skipping Nominatim query...")
            return '00' + cc  # Get the country code value of the first matching row
    else:
        return None


def copy_shortname_rinex(f_rinex, long_rinex):
    """
    Function to copy a short-named RINEX file to a file with the long RINEX name, if the short-named file exists.
    :param f_rinex: The path of the short-named RINEX file.
    :param long_rinex: The path of the long-named RINEX file to create.
    :return: None.
    """

    if os.path.isfile(f_rinex):
        try:
            # make a copy of short-name rinex (using the long name that was just derived) into doy_dir
            shutil.copy(f_rinex, long_rinex)
        except OSError as e:
            err_log.warning(f'Could not copy file {f_rinex} to {long_rinex}. Error: {e}')


def del_shortname_rinex(f_rinex):
    """
    Function to delete a short-named RINEX file, if it exists.
    :param f_rinex: The path of the short-named RINEX file.
    :return: None.
    """
    if os.path.isfile(f_rinex):
        try:
            # remove the old short-named file
            os.remove(f_rinex)
        except OSError as e:
            err_log.warning(f"Could not remove {f_rinex}: Error: {e}")


def generate_long_filename_after_splityear(lat, lon, sample_interval, f_rinex, rinex_names_set_w_ext):
    """
    Function to generate a long IGS-standard RINEX file name (via RX3name) for a short-named RINEX file, using the
    country code derived from lat/lon, and replace the short-named file with the long-named one in the DOY directory.
    Note: changes the working directory, renames/copies/deletes RINEX files.
    :param lat: The latitude in degrees.
    :param lon: The longitude in degrees.
    :param sample_interval: The sample interval in seconds (from Anubis *.xtr).
    :param f_rinex: The uncompressed short-named RINEX file name.
    :param rinex_names_set_w_ext: Set of lowercase RINEX names (with extension) already present.
    :return: Tuple of long RINEX name, 3-character country code and the name of an already present RINEX with a
             different resolution (or matching name); None values on failure.
    """

    add_country = check_stn_presence(f_rinex[:4].upper(), lat, lon)

    # generating a name for current DOY directory (based on RINEX filename)
    try:
        sf = f_rinex.split('.')
        year = sf[1][:2]
    except IndexError as e:
        if f_rinex[-4] != '.':
            ss = list(f_rinex)
            ss[-4] = '.'
            f = ''.join(ss)
            sf = f.split('.')
            year = sf[1][:2]
        else:
            print('Problem with filename: ', f_rinex, e)
            return None, None

    if 80 < int(year) <= 99:
        year = '19' + year
    else:
        year = '20' + year
    doy = sf[0][4:7]

    doy_dir = config.rinex_archive_path + year + '/' + doy + '/'

    # At igs.org the country code is given by territorial principles. The same for French overseas
    if not add_country:
        s_name = f_rinex[:4].lower()
        # If lat < -XXX degrees, then add_country = '00ATA'
        if lat < - 62.0:
            add_country = '00ATA'  # must be in Antarctica

        elif s_name == 'kerg' or s_name == 'cftg' or s_name == 'krgg':
            add_country = '00ATF'
        elif s_name == 'ftna' or s_name == 'thtg' or s_name == 'gamb' or s_name == 'thti' or s_name == 'tah1':
            add_country = '00PYF'
        elif s_name == 'cyne' or s_name == 'koug' or s_name == 'kour':
            add_country = '00GUF'
        elif s_name == 'abmf':
            add_country = '00GLP'
        elif s_name == 'kouc' or s_name == 'nrmd':
            add_country = '00NCL'
        elif s_name == 'lmmf':
            add_country = '00MTQ'
        elif s_name == 'reun':
            add_country = '00REU'
        elif s_name == 'rvo_':
            add_country = '00PNG'
        elif s_name == 'covx' or s_name == 'dum1' or s_name == 'dev1':  # in ocean or lighthouse
            add_country = '00USA'

        else:
            country_code = get_country(s_name, lat, lon)
            if not country_code:
                return None, None, None

            add_country = '00' + country_code

    os.chdir(doy_dir)  # directory with RINEX files

    # If the filename is of type SITE*.YYD (like compact RINEX in EPN), then rename the file to SITE*.YYd
    if f_rinex.endswith('D'):
        f_rinex_new = f_rinex[:-1] + 'd'
        # rename the file in doy_dir, otherwise RX3name does not generate long-named file
        os.rename(f_rinex, f_rinex_new)
        f_rinex = f_rinex_new
    elif f_rinex.endswith('O'):
        f_rinex_new = f_rinex[:-1] + 'o'
        # rename the file in doy_dir, otherwise RX3name does not generate long-named file
        os.rename(f_rinex, f_rinex_new)
        f_rinex = f_rinex_new
    else:
        f_rinex_new = f_rinex  # don't rename for the next cmd

    # generate a long filename for return
    cmd = [config.rx3name_executable, f_rinex_new, add_country]
    pipe = subprocess.PIPE  # Pipe the output of the first command into 'sed' and 'xargs'
    long_name_res = subprocess.run(cmd, stdout=pipe)

    if long_name_res.returncode == 0:
        long_rinex = long_name_res.stdout.decode('utf-8').strip()  # e.g. 'AHID00USA_R_20162880000_01D_30S_MO.crx'
        if long_rinex.lower() in rinex_names_set_w_ext and int(sample_interval) == 30:
            # Exactly the same filename (30S file, also matching the extension) is already present -
            # derived from another network, do not overwrite the RINEX with long name,
            # only delete the RINEX with short name!
            del_shortname_rinex(f_rinex)
            return long_rinex, add_country[2:], long_rinex.lower()
        else:
            long_rinex_final_res = long_rinex[:28] + str(int(sample_interval)).zfill(2) + 'S' + long_rinex[31:]
            diff_res_file_present = (
                compare_rinex_log.find_other_res_rinex_matching_new_file(long_rinex_final_res[:-4],
                                                                         rinex_names_set_w_ext))
            if not diff_res_file_present:
                # continue with writing a new file with long filename
                process2 = subprocess.run(['sed', 's/ *$//'], input=long_name_res.stdout, stdout=pipe)
                process3 = subprocess.run(['xargs', '-i{}', 'cp', f_rinex, '{}'], input=process2.stdout, stdout=pipe)
            else:
                if (long_rinex[:-3].lower() == diff_res_file_present[:-3] and
                        long_rinex[-3:].lower() != diff_res_file_present[-3:]):  # different extension, i.e. rnx before, now crx (or vice versa)
                    process2 = subprocess.run(['sed', 's/ *$//'], input=long_name_res.stdout, stdout=pipe)
                    process3 = subprocess.run(['xargs', '-i{}', 'cp', f_rinex, '{}'], input=process2.stdout,
                                              stdout=pipe)
            if int(sample_interval) != 30:
                if not long_rinex.lower() in rinex_names_set_w_ext:
                    # removing the "old with faulty 30S" filename (includes extension) the rx3name has given.
                    # Safe to do so because such file is not used in df.
                    if os.path.isfile(long_rinex):
                        os.remove(long_rinex)
                        # err_log.info(f'     {long_rinex} deleted')
                long_rinex = long_rinex_final_res  # this we want to keep

                # Now do similar check but use the filename that is corrected for the time resolution
                # This avoids overwriting a file that is already present and downloaded from another network
                if not long_rinex.lower() in rinex_names_set_w_ext:
                    copy_shortname_rinex(f_rinex, long_rinex)
                    # err_log.info(f'       copying {f_rinex} to {long_rinex}')
                del_shortname_rinex(f_rinex)
            else:
                # copy_shortname_rinex(f_rinex, long_rinex)  # not needed, copied already within subprocess.run above
                del_shortname_rinex(f_rinex)

            return long_rinex, add_country[2:], diff_res_file_present

    else:
        # Antarctica and to check if the lat/lon values correspond to an arctic section as used in IGS-daily. Then
        # the country codes "add_country" would be added automatically with the next cmd. Or, creating manually a
        # table for all known Antarctic sites already with long site names and replacing in doy_dir while the short
        # site name is met? If the site is not arctic by lat/lon then return None (interrupting the daily loop)
        err_log.error(f" Could not get long RINEX name using command: {cmd.join(' ')}")
        return None, None, None


def generate_long_filename_before_splityear(lat, lon, sample_interval, first_epoch, constellation_indicator, f_rinex,
                           rinex_names_set_w_ext, unzipped_rinex_path):
    """
    Function to build a long IGS-standard RINEX file name for a short-named RINEX file (from country code, first
    epoch, sample interval and constellation) and replace the short-named file with the long-named one.
    Note: changes the working directory, renames/copies/deletes RINEX files.
    :param lat: The latitude in degrees.
    :param lon: The longitude in degrees.
    :param sample_interval: The sample interval in seconds (from Anubis *.xtr or header).
    :param first_epoch: The first epoch (string 'YYYY-MM-DD HH:MM:SS' or datetime).
    :param constellation_indicator: The constellation indicator (e.g. 'G', 'M').
    :param f_rinex: The uncompressed short-named RINEX file name.
    :param rinex_names_set_w_ext: Set of lowercase RINEX names (with extension) already present.
    :param unzipped_rinex_path: The path of the unzipped RINEX file (its directory is used as working directory).
    :return: Tuple of long RINEX name, 3-character country code and the name of an already present RINEX with a
             different resolution (or matching name); None values on failure.
    """
    d_type, units_freq, d_source, f_fmt = '', '', '', ''
    s_name = f_rinex[:4]

    if lat == '' or lon == '':
        err_log.warning(f'lat, lon values missing from qc_inf or replica for site {s_name}')
        return None, None, None

    add_country = check_stn_presence(f_rinex[:4].upper(), lat, lon)

    # generating a name for current DOY directory (based on RINEX filename)
    try:
        sf = f_rinex.split('.')
        year = sf[1][:2]
        fmt = sf[1][-1]
        if fmt == 'o' or fmt == 'O':
            f_fmt = 'rnx'
        if fmt == 'd' or fmt == 'D':
            f_fmt = 'crx'
    except IndexError as e:
        if f_rinex[-4] != '.':
            ss = list(f_rinex)
            ss[-4] = '.'
            f = ''.join(ss)
            sf = f.split('.')
            year = sf[1][:2]
        else:
            print('Problem with filename: ', f_rinex, e)
            return None, None

    if 80 < int(year) <= 99:
        year = '19' + year
    else:
        year = '20' + year
    doy = sf[0][4:7]

    doy_dir = os.path.dirname(unzipped_rinex_path)

    # At igs.org the country code is given by territorial principles. The same for French overseas
    if not add_country:
        s_name = f_rinex[:4].lower()
        # If lat < -XXX degrees, then add_country = '00ATA'
        if lat < - 62.0:
            add_country = '00ATA'  # must be in Antarctica

        elif s_name == 'kerg' or s_name == 'cftg' or s_name == 'krgg':
            add_country = '00ATF'
        elif s_name == 'ftna' or s_name == 'thtg' or s_name == 'gamb' or s_name == 'thti' or s_name == 'tah1':
            add_country = '00PYF'
        elif s_name == 'cyne' or s_name == 'koug' or s_name == 'kour':
            add_country = '00GUF'
        elif s_name == 'abmf':
            add_country = '00GLP'
        elif s_name == 'kouc' or s_name == 'nrmd':
            add_country = '00NCL'
        elif s_name == 'lmmf':
            add_country = '00MTQ'
        elif s_name == 'reun':
            add_country = '00REU'
        elif s_name == 'rvo_':
            add_country = '00PNG'
        elif s_name == 'covx' or s_name == 'dum1' or s_name == 'dev1':  # in ocean or lighthouse
            add_country = '00USA'

        else:
            #   US_CORS covx and dum1 are located in the ocean and get_country() responds with an error, the sites
            #   are not compared (rinex and log) and not documented in daily comparing*.txt
            #   If s_name == 'covx' or s_name == 'dev1', then add_country = '00USA', else add_country = '00' +
            #   get_country(lat, lon). If (later) will be collected many other cases like this (small islands,
            #   lighthouses, we can use a list or a directory {} with keys and values.
            country_code = get_country(s_name, lat, lon)
            if not country_code:
                return None, None, None

            add_country = '00' + country_code

    os.chdir(doy_dir)  # directory with RINEX files

    # If the filename is of type SITE*.YYD (like compact RINEX in EPN), then rename the file to SITE*.YYd
    if f_rinex.endswith('D'):
        f_rinex_new = f_rinex[:-1] + 'd'
        # rename the file in doy_dir, otherwise RX3name does not generate long-named file
        os.rename(f_rinex, f_rinex_new)
        f_rinex = f_rinex_new
    elif f_rinex.endswith('O'):
        f_rinex_new = f_rinex[:-1] + 'o'
        # rename the file in doy_dir, otherwise RX3name does not generate long-named file
        os.rename(f_rinex, f_rinex_new)
        f_rinex = f_rinex_new
    else:
        f_rinex_new = f_rinex  # don't rename for the next cmd

    # ===============================================================
    # anubis_for_grep() should give additionally constellation_indicator [4] from a line with '=RNXVER':
    # RNXHDR 2014-04-20 00:00:00 _RINEX_HEADER___________ _RINEX_HEADER___________ _RINEX_HEADER___________
    # =RNXVER     2014-04-20   00:00:00     2.11    M    2014-04-21  08: 00:00
    # from anubis_for_grep() first_epoch from line with =TOTSUM 2014-04-20 00:00:00
    # expecting (hard-coded):
    monument_number = '0'  # hard_coded
    receiver_number = '0'  # hard-coded
    units_freq = 'S'  # seconds (S), minutes (M), hours (H), days (D)
    d_source = 'R'  # receiver (R), stream (S), unknown (U)
    d_type = 'O'  # observation (O), navigation (N), meteo (M), no associated constellation (MM)

    if isinstance(first_epoch, datetime.datetime):
        first_epoch = first_epoch.strftime("%Y-%m-%d %H:%M:%S")  # datetime object to string if from header_inf

    s_hours = first_epoch.split()
    hours = s_hours[1].split(':')[0].strip()
    minutes = s_hours[1].split(':')[1].strip()
    # sample_interval in rinex name , if 60, 120, 3600 --> 01M, 02M, 01H (example, 1994DOY100 MONP interval=120)
    sample_interval_with_units_freq = ''
    sample_int = 0
    try:
        sample_int = round(float(sample_interval))  # coming a string (e.g., '30.000')
        if sample_int < 60:
            sample_interval_with_units_freq = str(sample_int).zfill(2) + 'S'
        if 60 <= sample_int <= 3600:
            sample_interval_with_units_freq = str(int(sample_int / 60)).zfill(2) + 'M'
        if sample_int > 3600:
            sample_interval_with_units_freq = str(int(sample_int / 3600)).zfill(2) + 'H'
    except ValueError as e:
        sample_interval_with_units_freq = sample_interval + 'S'
    long_name_res = s_name.upper() + monument_number + receiver_number + add_country[-3:] + '_' + d_source + '_' + \
                    year + doy + hours + minutes + '_' + '01D' + '_' + sample_interval_with_units_freq + '_' + \
                    constellation_indicator + d_type + '.' + f_fmt
    long_rinex = long_name_res

    # if long_rinex.lower() in rinex_names_set_w_ext and int(sample_interval) == 30:
    if long_rinex.lower() in rinex_names_set_w_ext and sample_int == 30:
        # Exactly the same filename (30S file, also matching the extension) is already present -
        # derived from another network, do not overwrite the RINEX with long name,
        # only delete the RINEX with short name!
        del_shortname_rinex(f_rinex)
        # err_log.info(f'   {long_rinex} already present - skipping rx3name')
        return long_rinex, add_country[2:], long_rinex.lower()
    else:
        # long_rinex_final_res = long_rinex[:28] + str(int(sample_interval)).zfill(2) + 'S' + long_rinex[31:]
        long_rinex_final_res = long_rinex[:28] + sample_interval_with_units_freq + long_rinex[31:]
        diff_res_file_present = (
            compare_rinex_log.find_other_res_rinex_matching_new_file(long_rinex_final_res[:-4],
                                                                     rinex_names_set_w_ext))
        if not diff_res_file_present:
            # continue with writing a new file with long filename
            copy_shortname_rinex(f_rinex_new, long_rinex)  #
        else:
            # different extension, i.e. rnx before, now crx (or vice versa)
            if (long_rinex[:-3].lower() == diff_res_file_present[:-3]) and \
                    (long_rinex[-3:].lower() != diff_res_file_present[-3:]):

                copy_shortname_rinex(f_rinex, long_rinex)
                del_shortname_rinex(f_rinex)
                # err_log.info(f'   found duplicate in GREP ({diff_res_file_present}), '
                #              f'but with different extension - writing {long_rinex}')

        if sample_int != 30:
            if not long_rinex.lower() in rinex_names_set_w_ext:
                # removing the "old with faulty 30S" filename (includes extension).
                # Safe to do so because such file is not used in df.
                if os.path.isfile(long_rinex):
                    os.remove(long_rinex)
                    # err_log.info(f'     {long_rinex} deleted')
            long_rinex = long_rinex_final_res  # this we want to keep

            # Now do similar check but use the filename that is corrected for the time resolution
            # This avoids overwriting a file that is already present and downloaded from another network
            if not long_rinex.lower() in rinex_names_set_w_ext:
                copy_shortname_rinex(f_rinex, long_rinex)
                # err_log.info(f'       copying {f_rinex} to {long_rinex}')
            del_shortname_rinex(f_rinex)
        else:
            del_shortname_rinex(f_rinex)

        return long_rinex, add_country[2:], diff_res_file_present


def get_approx_position(year, doy, f_rinex):
    """
    Function to get the approximate site position of a RINEX file estimated by Anubis QC for the given year and DOY.
    :param year: The year.
    :param doy: The day of year.
    :param f_rinex: The RINEX file name.
    :return: The result of anubis_for_grep() for the RINEX file.
    """
    # From ANUBIS *.xtr:
    # #====== Estimated values (v.2)
    # =PERIOD 2019-01-09 00:00:00 2019-01-09 00:00:00     2019-01-09 23:59:30
    # =SAMPLE 2019-01-09 00:00:00 30.000
    # =XYZGPS 2019-01-09 00:00:00    -1224452.7845   -2689216.1404    5633638.3237     0.7     0.7     1.7    96     0
    # =XYZGLO 2019-01-09 00:00:00    -1224453.9489   -2689216.8547    5633637.4863     2.8     3.7     9.7    96     0
    # =XYZGNS 2019-01-09 00:00:00    -1224452.9151   -2689216.2591    5633638.2091     0.7     0.8     2.5    96     0
    # =BLHGPS 2019-01-09 00:00:00     62.480893638   245.519296334        180.9660     0.9     1.2     1.6    96     0
    # =BLHGLO 2019-01-09 00:00:00     62.480881353   245.519281115        180.4544     4.7     5.5     8.9    96     1
    # =BLHGNS 2019-01-09 00:00:00     62.480891873   245.519294983        180.9394     1.3     1.4     2.3    96     0

    tmp_doy_path = config.rinex_archive_path + str(year) + '/' + str(doy).zfill(3) + '/'

    return anubis_for_grep(f_rinex, tmp_doy_path, year, doy, 2, 2)


def get_brdc_mixed_rinex3_cddis(year, doy, brdc_down_path):
    """
    Function to download the daily broadcast ephemeris (BRDC) file from CDDIS for Anubis QC and gunzip it. Retries
    every 10 seconds on request errors.
    :param year: The year.
    :param doy: The day of year.
    :param brdc_down_path: The local directory for the BRDC file (created if missing).
    :return: None.
    """
    #
    # BRDC-files in CDDIS use "old" brdc file format before 2016. Since 2016, there always present files 'BRDC00IGS_R_'
    if 1992 <= year <= 2015:
        brdc_name = 'brdc' + str(doy).zfill(3) + '0.' + str(year)[2:] + 'n.Z'
    else:
        brdc_name = 'BRDC00IGS_R_' + str(year) + str(doy).zfill(3) + '0000_01D_MN.rnx.gz'
    remote_url = 'https://cddis.nasa.gov/archive/gnss/data/daily/' + str(year) + '/brdc/' + brdc_name
    got_file = False
    brdc_path = brdc_down_path
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
            os.system('gunzip ' + brdc_path + brdc_name)
            break  # file downloaded

        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            err_log.warning(
                ' %s - get_brdc_mixed_rinex3_cddis(). Retrying in 10 seconds. Current site to download %s' % (
                    ex, brdc_name))
            time.sleep(10)  # increase the delay 10 --> 120 (for test)
            pass
        except Exception as ex:
            raise ex


def get_sp3_cddis(year, doy, sp3_down_path):
    """
    Function to download the SP3 orbit file from CDDIS for Anubis QC and gunzip it. If the file is missing (HTTP 404),
    ESA, COD and JPL alternatives are tried. Retries up to 5 times on errors.
    :param year: The year.
    :param doy: The day of year.
    :param sp3_down_path: The local directory for the SP3 file (created if missing; the same as for BRDC).
    :return: None.
    """
    #
    #
    wk, wd = t_box.tools.get_gps_week_and_weekday(year, doy)
    err_log.info(' GPS week %s, weekday %s' % (wk, wd))

    # IGS SP3 name formats in CDDIS:
    # since 1996 DOY001 igsWWWWD.sp3.Z, where D is day of the week (0...6), Sun = 0
    # up to 2022 DOY330
    # since 2022 DOY331 (week 2238) long format:
    # e.g., IGS0OPSFIN_20230040000_01D_15M_ORB.SP3.gz

    new_format_begin_date = datetime.datetime(2022, 11, 27, 0, 0)
    sio_sp3_end_date = datetime.datetime(1993, 11, 14, 0, 0)
    # new_format_begin_date = datetime.date(2022, 11, 27)  # 2022 DOY 331
    processing_date_s = t_box.tools.doy_to_date2(year, doy)
    processing_date = datetime.datetime.strptime(processing_date_s, '%Y/%m/%d')

    if processing_date < new_format_begin_date:
        if processing_date < sio_sp3_end_date:
            sp3_name = f'sio{wk:04d}{wd}.sp3.Z'

        else:
            sp3_name = f'igs{wk:04d}{wd}.sp3.Z'
    else:
        sp3_name = 'IGS0OPSFIN_' + str(year) + str(doy).zfill(3) + '0000_01D_15M_ORB.SP3.gz'

    remote_url = f'https://cddis.nasa.gov/archive/gnss/products/{wk:04d}/{sp3_name}'
    err_log.info(' Going to download %s' % remote_url)

    got_file = False
    max_retries = 5
    rep = 0

    sp3_path = sp3_down_path
    if not os.path.exists(sp3_path):
        os.makedirs(sp3_path)

    # Common headers (CDDIS behaves better with browser UA)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Connection": "keep-alive"
    }

    while got_file is False and rep < max_retries:
        try:
            import socket

            # --- REQUEST WITH SAFE TIMEOUTS + STREAM MODE ---
            r = requests.get(
                remote_url,
                timeout=(5, 5),  # (connect timeout, read timeout)
                stream=True,
                headers=headers
            )
            sp3_full_path = sp3_path + sp3_name

            def sock_read(s_path):
                """
                Function to write the streamed response content to a file using raw socket reads.
                :param s_path: The local file path to write to.
                :return: None.
                """
                # --- DOWNLOAD USING RAW SOCKET READ (never hangs) ---
                with open(s_path, "wb") as fd_s:
                    while True:
                        try:
                            chunk_s = r.raw.read(4096)
                        except socket.timeout:
                            raise TimeoutError("CDDIS stalled during download")

                        if not chunk_s:
                            break

                        fd_s.write(chunk_s)

            # ================= if first choice gives http error 404
            if r.status_code == 404:
                print(f'file at {remote_url} is missing')
                res_log.warning(f'file at {remote_url} is missing, trying alternative from ESA')
                sp3_name = f'esa{wk:04d}{wd}.eph.Z'
                remote_url = f'https://cddis.nasa.gov/archive/gnss/products/{wk:04d}/{sp3_name}'

                r = requests.get(
                    remote_url,
                    timeout=(5, 5),  # (connect timeout, read timeout)
                    stream=True,
                    headers=headers
                )

                err_log.info(' Going to download %s' % remote_url)
                sp3_full_path = sp3_path + sp3_name
                sock_read(sp3_full_path)
                result = subprocess.run(['gunzip', '-f', sp3_full_path], check=True)
                if r.status_code == 404:  # then try alternative *.eph from COD
                    print(f'file at {remote_url} is missing')
                    res_log.warning(f'file at {remote_url} is missing, trying alternative from COD')
                    sp3_name = f'cod{wk:04d}{wd}.eph.Z'
                    remote_url = f'https://cddis.nasa.gov/archive/gnss/products/{wk:04d}/{sp3_name}'

                    r = requests.get(
                        remote_url,
                        timeout=(5, 5),  # (connect timeout, read timeout)
                        stream=True,
                        headers=headers
                    )

                    err_log.info(' Going to download %s' % remote_url)
                    sp3_full_path = sp3_path + sp3_name
                    sock_read(sp3_full_path)
                    result = subprocess.run(['gunzip', '-f', sp3_full_path], check=True)
                    if r.status_code == 404:  # if still missing then try alternative *.eph from ESA
                        print(f'file at {remote_url} is missing')
                        res_log.warning(f'file at {remote_url} is missing, trying alternative from JPL')
                        sp3_name = f'jpl{wk:04d}{wd}.sp3.Z'
                        remote_url = f'https://cddis.nasa.gov/archive/gnss/products/{wk:04d}/{sp3_name}'

                        r = requests.get(
                            remote_url,
                            timeout=(5, 5),  # (connect timeout, read timeout)
                            stream=True,
                            headers=headers
                        )

                        err_log.info(' Going to download %s' % remote_url)
                        sp3_full_path = sp3_path + sp3_name
                        sock_read(sp3_full_path)
                        result = subprocess.run(['gunzip', '-f', sp3_full_path], check=True)
                        if r.status_code == 404:
                            err_log.error(
                                f'have tried to get orbital data from SIO, JPL, COD and ESA, but still failed!')

            sock_read(sp3_full_path)
            sp3_full_fn = sp3_path + sp3_name
            result = subprocess.run(['gunzip', '-f', sp3_full_fn], check=True)

            res_log.info(f' sp3 file {sp3_name} downloaded and unzipped')
            got_file = True
            break  # file downloaded

        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:

            if rep < max_retries - 1:  # if it's not the final attempt
                err_log.warning(' %s - get_sp3_cddis(). Retrying in 10 seconds. Current sp3 file to download %s' % (
                    ex, sp3_name))
                time.sleep(10)
                rep += 1
            else:
                err_log.warning(' %s - get_sp3_cddis(). Max retries reached for %s. Aborting...' % (ex, sp3_name))
                raise

        except subprocess.CalledProcessError as e:
            if rep < max_retries - 1:  # if it's not the final attempt
                err_log.warning(f" gunzip operation for {sp3_name} failed with error: {e.returncode}. "
                                f"Retrying in 10 seconds.")
                time.sleep(10)
                rep += 1
            else:
                err_log.error(
                    f" gunzip operation for {sp3_name} failed with error: {e.returncode}. Max retries reached. "
                    f"Aborting...")
                raise

        except Exception as ex:
            err_log.error(f" Unknown error from get_sp3_cddis(): {ex}. Aborting...")
            raise ex


def anubis_for_grep(rinex_file, tmp_doy_path, year, doy, qc_sec_sum, qc_sec_est):
    """
    Function to run Anubis QC on a single RINEX observation file (using SP3 orbits) and extract the sample interval,
    first epoch, constellation indicator and estimated XYZ/lat/lon/ellipsoidal height from the *.xtr output.
    Note: deletes the *.xtr file and moves the RINEX to the error directory on failure.
    :param rinex_file: The RINEX file name.
    :param tmp_doy_path: The path to the current DOY directory with the RINEX file.
    :param year: The year.
    :param doy: The day of year.
    :param qc_sec_sum: The Anubis summary statistics level (default 2).
    :param qc_sec_est: The Anubis estimated values level (default 2).
    :return: Dictionary with the QC values, or None on failure.
    """
    BRDC = False
    # BRDC-files in CDDIS use "old" brdc file format before 2016. Since 2016, there always present files 'BRDC00IGS_R_'
    brdc_path = config.daily_brdc_path

    # CDDIS SP3 new format begin 2022 DOY 331 (27. November 2022)
    new_format_begin_date = datetime.datetime(2022, 11, 27, 0, 0)
    processing_date_s = t_box.tools.doy_to_date2(year, doy)
    processing_date = datetime.datetime.strptime(processing_date_s, '%Y/%m/%d')

    # next 7 lines activated for BRDC only, i.e., if BRDC = True
    sp3_name = ''
    if BRDC:
        if 1992 <= year <= 2015:
            brdc_filename = 'brdc' + str(doy).zfill(3) + '0.' + str(year)[2:] + 'n'
            brdc_file = os.path.join(brdc_path, brdc_filename)
        else:
            brdc_name_start = 'BRDC00IGS_R_'
            brdc_filename = f"{brdc_name_start}{year}{str(doy).zfill(3)}0000_01D_MN.rnx"
            brdc_file = os.path.join(brdc_path, brdc_filename)
    else:
        if year >= config.proc_split_year:
            if processing_date < new_format_begin_date:
                wk, wd = t_box.tools.get_gps_week_and_weekday(year, doy)
                sp3_name = 'igs' + str(wk) + str(wd) + '.sp3'
            else:
                sp3_name = 'IGS0OPSFIN_' + str(year) + str(doy).zfill(3) + '0000_01D_15M_ORB.SP3'
        else:
            if processing_date < new_format_begin_date:
                wk, wd = t_box.tools.get_gps_week_and_weekday(year, doy)
                o = os.scandir(brdc_path)
                for entry in o:
                    if entry.is_file():
                        sp3_name = entry.name
            else:
                o = os.scandir(brdc_path)
                for entry in o:
                    if entry.is_file():
                        sp3_name = entry.name
        brdc_file = os.path.join(brdc_path, sp3_name)

    # compile a command with run-time parameters
    set_params = ''
    if int(qc_sec_sum):
        set_params = set_params + ' :qc:sec_sum=' + str(qc_sec_sum)
    if int(qc_sec_est):
        set_params = set_params + ' :qc:sec_est=' + str(qc_sec_est)

    anubis_executable = config.anubis_executable
    tmp_doy_file = os.path.join(tmp_doy_path, rinex_file)
    out_file = os.path.join(tmp_doy_path, rinex_file.split('.')[0] + '.xtr')
    if BRDC:
        a_cmd = f'{anubis_executable} ":inp:rinexo" "{tmp_doy_file}" ":inp:rinexn" "{brdc_file}" ":out:xtr" "{out_file}" {set_params}'
    else:
        a_cmd = f'{anubis_executable} ":inp:rinexo" "{tmp_doy_file}" ":inp:sp3" "{brdc_file}" ":out:xtr" "{out_file}" {set_params}'
    subprocess.run(a_cmd, shell=True, cwd=tmp_doy_path)

    # Having site.xtr in current working directory (tmp_doy_path)
    qc_stn_coords = {}

    xtr_file = tmp_doy_path + rinex_file.split('.')[0] + '.xtr'
    try:
        try:
            with open(xtr_file, 'r', encoding='utf-8') as f_in:  # trying with utf-8
                xtr_lines = f_in.readlines()
        except UnicodeDecodeError:
            try:
                with open(xtr_file, 'r', encoding='ISO-8859-1') as f_in:  # trying with latin1
                    xtr_lines = f_in.readlines()
            except UnicodeDecodeError as e:  # neither utf-8 and latin1 did work, skipping this RINEX, move to RINEX_err
                os.remove(xtr_file)
                err_log.warning(f" Cannot read {xtr_file}: {e}")
                compare_rinex_log.move_rinex_to_err_dir(year, doy, rinex_file)
                return None
        for i in range(len(xtr_lines)):
            # ====== Summary statistics (v.2)
            # TOTSUM First_Epoch________ Last_Epoch_________ Hours_ Sample MinEle #_Expt #_Have %Ratio o/slps woElev Exp>10 Hav>10 %Rt>10
            # =TOTSUM 2005-04-21 00:00:00 2005-04-21 23:59:30  21.23  30.00   1.81  28669  19457  67.87     49      0  22000  19455  88.43
            if '=TOTSUM' in xtr_lines[i]:
                sl = xtr_lines[i].split()
                qc_stn_coords['sample_interval'] = float(sl[6].strip())
                qc_stn_coords['first_epoch'] = (sl[1] + ' ' + sl[2]).strip()
            if '=RNXVER' in xtr_lines[i]:
                sl = xtr_lines[i].split()
                qc_stn_coords['constellation_indicator'] = sl[4].strip()
            if ('=XYZGNS' in xtr_lines[i]) or ('=XYZGPS' in xtr_lines[i]):
                sl = xtr_lines[i].split()
                # qc_xyz = [sl[3].strip(), sl[4].strip(), sl[5].strip()]
                qc_stn_coords['x'] = float(sl[3].strip())
                qc_stn_coords['y'] = float(sl[4].strip())
                qc_stn_coords['z'] = float(sl[5].strip())
            if ('=BLHGNS' in xtr_lines[i]) or ('=BLHGPS' in xtr_lines[i]):
                sl = xtr_lines[i].split()
                # qc_lat_lon_ellipse = [sl[3].strip(), sl[4].strip(), sl[5].strip()]
                qc_stn_coords['lat'] = float(sl[3].strip())
                qc_stn_coords['lon'] = float(sl[4].strip())
                qc_stn_coords['ellips'] = float(sl[5].strip())
                break
    except FileNotFoundError as e:
        err_log.warning(f' No {xtr_file} from Anubis QC: {e}')
        compare_rinex_log.move_rinex_to_err_dir(year, doy, rinex_file)
        return None

    # remove anubis.log and xtr_file after the site RINEX analysis (approximated coordinates extraction)
    try:
        os.remove(xtr_file)
    except OSError as e:
        err_log.warning(f" Cannot remove {xtr_file}: {e.strerror}")

    if len(qc_stn_coords) <= 3:
        err_log.warning(f' No QC coordinates found in {xtr_file}')
        compare_rinex_log.move_rinex_to_err_dir(year, doy, rinex_file)
        return None

    return qc_stn_coords


def dos2unix(f_path):
    """
    Function to replace Windows (CRLF) line endings with UNIX (LF) line endings in a file (in place).
    :param f_path: The path of the file.
    :return: None.
    """
    # replacement strings
    w_e = b'\r\n'
    u_e = b'\n'

    with open(f_path, 'rb') as open_file:
        content = open_file.read()
    content = content.replace(w_e, u_e)

    with open(f_path, 'wb') as open_file:
        open_file.write(content)


def dos_line_endings(f_path):
    """
    Function to check whether the first line of a file has DOS (CRLF) line endings.
    :param f_path: The path of the file.
    :return: True if the first line ends with CRLF, False if a CR is not followed by LF, None otherwise (or if the
             file does not exist).
    """
    try:
        with open(f_path, 'rb') as f:
            while True:
                c = f.read(1)
                if not c or c == b'\n':
                    break
                if c == b'\r':
                    if f.read(1) == b'\n':
                        return True
                    else:
                        return False
    except FileNotFoundError as e:
        print('File does not exist: ', e)
