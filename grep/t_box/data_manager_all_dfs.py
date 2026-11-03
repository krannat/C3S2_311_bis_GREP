from grep.t_box import stn_table_from_dfs
import os
from dbio import data_manager
from datetime import datetime
import pandas as pd
import config


def merge_all_data_dfs():
    """
    Merge all dataframes present in the specified directory and return the merged dataframe.
    :return: Merged dataframe containing all dataframes from the specified directory.
    """

    base_path = config.pkl_path
    df_list = []

    # os.walk yields a 3-tuple containing dirpath, dirnames and filenames respectively
    for dirpath, dirnames, filenames in os.walk(base_path):
        for filename in filenames:
            if filename.endswith('.pkl'):
                filepath = os.path.join(dirpath, filename)
                print(f'Reading {filename}...')
                df = pd.read_pickle(str(filepath))
                # Index of 'error_codes' column plus 1 to get columns after 'error_codes'
                idx = df.columns.get_loc('error_codes') + 1
                # Select necessary columns
                df = df[['rinex_name', 'rinex_source', 'rinex_download_dt', 'site_name', 'log_name', 'log_source', 'log_download_dt', *df.columns[idx:]]]
                df_list.append(df)

    # Concatenate all dataframes in the list
    print('Merging all dataframes...')
    merged_data_df = pd.concat(df_list)
    unique_values_count = merged_data_df['site_name'].nunique()
    # print(unique_values_count)
    return merged_data_df


def create_filters(dframe):
    """
    Create filter conditions based on the given DataFrame.

    :param dframe: The DataFrame containing the data.
    :return: A dictionary of filter conditions.
    """
    # Define datetime range
    start_datetime = datetime.strptime("2025-02-12 15:59:00", "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.strptime("2025-02-12 16:30:00", "%Y-%m-%d %H:%M:%S")

    filter_conditions = {
        # 'by_network': (dframe['in_auspos']) & (dframe['in_cacs']),
        'by_network': (dframe['in_unavco']),
        'by_rinexname': (dframe['rinex_name'] == 'AUT000USA_R_20132150000_01D_00U_MO.rnx.gz'),
        'by_sitename': (dframe['site_name'] == 'GA0400AUS'),
        'by_logname': (dframe['log_name'] == 'bcov_20190307.log'),
        'by_logname_missing': (dframe['log_name'].isnull()),
        'by_log_datetime_range':
            (dframe['log_download_dt'].notnull()) & (dframe['log_download_dt'] >= start_datetime) & (dframe['log_download_dt'] <= end_datetime),
        'by_rinex_datetime_range':
            (dframe['log_download_dt'].notnull()) & (dframe['rinex_download_dt'] >= start_datetime) & (dframe['rinex_download_dt'] <= end_datetime)
    }
    return filter_conditions


def main():
    mrgd_df = merge_all_data_dfs()
    # print(mrgd_data_df.columns)
    mrgd_df['in_unavco'] = mrgd_df['in_unavco'].fillna(False)
    filters = create_filters(mrgd_df)
    flt_log_dt_range = data_manager.filter_data(mrgd_df, 'all_dfs', filters, 'by_log_datetime_range')
    flt_rnx_dt_range = data_manager.filter_data(mrgd_df, 'all_dfs', filters, 'by_rinex_datetime_range')
    flt_sitename = data_manager.filter_data(mrgd_df, 'all_dfs', filters, 'by_sitename')
    flt_logname = data_manager.filter_data(mrgd_df, 'all_dfs', filters, 'by_logname')
    flt_network = data_manager.filter_data(mrgd_df, 'all_dfs', filters, 'by_network')

    data_manager.write_df_to_csv(flt_sitename, os.path.join(config.df_backups_path, 'flt_sitename.csv'))

    print('This line is just for the breakpoint')


if __name__ == '__main__':
    main()
