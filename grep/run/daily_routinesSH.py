import sys

from grep import config
import os
import pandas as pd

from grep.dbio import shared_funcs
from grep.log import setup_log


def daily_run(year, doy, df_year, res_log, err_log, clear_log_handlers):
    """
    Scripts for daily updates of the repository
    a) logfiles
    b) RINEX
    c) QC (comparing headers and logfiles, if used in any known reprocessing, ..., + ANUBIS, if planned to do so??)
    :return:
    """

    # network_list = ['igs']
    network_list = ['us_cors']
    #network_list = ['epn']
    #network_list = ['auspos']
    # network_list = ['igs', 'epn', 'us_cors', 'cacs', 'auspos']

    # Get daily BRDC for Anubis
    shared_funcs.get_brdc_mixed_rinex3_cddis(year, doy, config.daily_brdc_path)

    for network in network_list:
        print("\nRunning daily updates for year %s and DOY %s for %s" % (year, doy, network))
        df_year = shared_funcs.process_network(year, doy, df_year, res_log, err_log, clear_log_handlers, network)

    # By the end of the day - remove daily BRDC (we don't archive BRDC, only using for coordinate check by Anubis)
    cmd = 'rm ' + config.daily_brdc_path + '*.*'
    os.system(cmd)

    rinex_doy_dir = os.path.join(config.rinex_archive_path, str(year), str(doy).zfill(3))
    setup_log.copy_daily_logfiles(res_log, err_log, rinex_doy_dir)
    return df_year


def main(year, from_doy, to_doy):

    year = int(year)
    from_doy = int(from_doy)
    to_doy = int(to_doy)

    for year in range(year, year + 1):
        data_file = os.path.join(config.pkl_path, f'{year}.pkl')

        if os.path.exists(data_file):
            df_year = pd.read_pickle(data_file)
        else:
            df_year = shared_funcs.create_empty_df()

        # clear_log_handler is set to True only when idx is not the first element of any range
        for idx, doy in enumerate(range(from_doy, to_doy)):
            setup_log.rollover_logs()
            res_log, err_log = setup_log.write_dailylog()
            clear_log_handlers = idx != 0
            df_year = daily_run(year, doy, df_year, res_log, err_log, clear_log_handlers=clear_log_handlers)
            df_year.to_pickle(data_file)
            df_year.to_csv(os.path.join(config.df_backups_path, f'{year}.csv'), index=False)


if __name__ == '__main__':
    main()


