import config
import os
import pandas as pd
import sys
from datetime import datetime, timedelta
from dbio import shared_funcs
from log import setup_log


def get_month_from_doy(year, doy):
    """
    Function to get the month for a given year and day of year.
    :param year: The year.
    :param doy: The day of year.
    :return: The month as a zero-padded string (e.g. '03').
    """
    date = datetime(year, 1, 1) + timedelta(doy - 1)
    return date.strftime('%m')


def daily_run(year, doy, df_month, res_log, err_log, clear_log_handlers):
    """
    Function to run the daily repository update (logfiles, RINEX, QC) for all selected networks for one day.
    Note: downloads daily SP3, deletes it afterwards and copies the daily log files to the RINEX DOY directory.
    :param year: The year to process.
    :param doy: The day of year to process.
    :param df_month: The monthly dataframe to be updated.
    :param res_log: The result logger.
    :param err_log: The error logger.
    :param clear_log_handlers: Whether log handlers should be cleared during processing.
    :return: The updated monthly dataframe (exits the program if processing is aborted).
    """

    network_list = config.network_list

    # Get daily BRDC for Anubis
    shared_funcs.get_sp3_cddis(year, doy, config.daily_brdc_path)

    for network in network_list:
        print("\nRunning daily updates for year %s and DOY %s for %s" % (year, doy, network))
        df_month = shared_funcs.process_network(year, doy, df_month, res_log, err_log, clear_log_handlers, network)
        if isinstance(df_month, str) and df_month == 'abort':
            sys.exit()

    # By the end of the day - remove daily BRDC (we don't archive BRDC, only using for coordinate check by Anubis)
    cmd = 'rm ' + config.daily_brdc_path + '*.*'
    os.system(cmd)

    rinex_doy_dir = os.path.join(config.rinex_archive_path, str(year), str(doy).zfill(3))
    setup_log.copy_daily_logfiles(res_log, err_log, rinex_doy_dir)
    return df_month


def main(year, from_doy, to_doy):
    """
    Function to run the daily routines for a range of days, loading and saving the monthly dataframe (pkl and csv).
    :param year: The year to process.
    :param from_doy: The first day of year to process.
    :param to_doy: The last day of year to process (inclusive).
    :return: None.
    """
    year, from_doy, to_doy = map(int, (year, from_doy, to_doy))

    for idx, doy in enumerate(range(from_doy, to_doy + 1)):

        month_str = get_month_from_doy(year, doy)
        pkl_year_dir = os.path.join(config.pkl_path, f'{year}')
        pkl_filepath = os.path.join(pkl_year_dir, f'{year}_{month_str}.pkl')

        if os.path.exists(pkl_filepath):
            df_month = pd.read_pickle(pkl_filepath)
        else:
            df_month = shared_funcs.create_empty_df(pkl_year_dir)

        if 'in_unavco' not in df_month.columns:
            df_month['in_unavco'] = False
        if 'uruguay' not in df_month.columns:
            df_month['in_uruguay'] = False
        if 'brazil_ibge' not in df_month.columns:
            df_month['in_brazil_ibge'] = False
        if 'greenland' not in df_month.columns:
            df_month['in_greenland'] = False
        if 'chile' not in df_month.columns:
            df_month['in_chile'] = False

        # clear_log_handler is set to True only when idx is not the first element of any range
        setup_log.rollover_logs()
        res_log, err_log = setup_log.write_dailylog()
        clear_log_handlers = idx != 0
        df_month = daily_run(year, doy, df_month, res_log, err_log, clear_log_handlers=clear_log_handlers)

        df_month.to_pickle(pkl_filepath)

        csv_year_dir = os.path.join(config.df_backups_path, f'{year}')
        if not os.path.exists(csv_year_dir):
            os.makedirs(csv_year_dir)
        df_month.to_csv(os.path.join(csv_year_dir, f'{year}_{month_str}.csv'), index=False)


if __name__ == '__main__':
    if len(sys.argv) == 4:
        main(sys.argv[1], sys.argv[2], sys.argv[3])  # python script.py arg1 arg2 arg3
    else:
        # for year in range(2000, 2001):
        #     main(year, 287, 365)
        main(2020, 328, 328)
