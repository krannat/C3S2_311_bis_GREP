import os
import pandas as pd
import config
from dbio import data_manager


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
                df = df[['rinex_name', 'site_name', 'log_name', 'log_source', 'log_download_dt', *df.columns[idx:]]]
                df_list.append(df)

    # Concatenate all dataframes in the list
    print('Merging all dataframes...')
    merged_data_df = pd.concat(df_list)
    unique_sites_count = merged_data_df['site_name'].nunique()
    print(f'Total number of unique sites in merged df: {unique_sites_count}')
    
    row_count = len(merged_data_df)
    print(f'Total number of rows in merged df: {row_count}')
    
    return merged_data_df


def read_stn_csv_as_df():
    """
    Reads the station table from a CSV file and returns it as a pandas DataFrame.
    :return: The station table as a pandas DataFrame.
    """

    csv_file = config.stn_csv_path
    # The station table may consist of additional columns but use only the following
    cols_to_read = ['site_name', 'country_code', 'lat', 'lon', 'elev', 'x', 'y', 'z']
    station_df = pd.read_csv(csv_file, usecols=cols_to_read)
    return station_df


def add_logfile_col_to_stn_csv(combined_df, station_df):
    """
    :param combined_df: DataFrame containing data to be merged with station dataframe
    :param station_df: DataFrame for stations
    :return: DataFrame with added logfile information
    """

    # Drop duplicates for each 'site_name', take only the FIRST line where latest_log_name, latest_log_download_dt
    # and latest_log_source are extracted
    # Also, 'first' can be used if the last entry for every station is correct.
    # combined_df_unique = combined_df.drop_duplicates(subset=['site_name'], keep='last')

    # Getting unique values for 'site_name'
    unique_sites = combined_df['site_name'].unique()

    # Creating a subset in which 'log_name' is not None
    combined_df_log_present = combined_df.dropna(subset=['log_name'])

    # Getting the last row for each site where log_name is not None
    final_df_log_present = combined_df_log_present.sort_values('log_name').groupby('site_name').tail(1)

    # Sites present in unique_sites but missing in final_df_log_present
    missing_sites = set(unique_sites) - set(final_df_log_present['site_name'].unique())

    # Filter rows where site_name is in missing_sites and get the last one of each group
    missing_rows = combined_df[combined_df['site_name'].isin(missing_sites)].groupby('site_name').tail(1)

    # Concatenate final_df_log_present with missing_rows
    combined_df_unique = pd.concat([final_df_log_present, missing_rows], ignore_index=True)

    # sort df by the first column
    combined_df_unique = combined_df_unique.sort_values(by=combined_df_unique.columns[0])

    station_df['site_name_9char'] = station_df['site_name'] + '00' + station_df['country_code']
    station_df = station_df.rename(columns={'site_name': 'site_name_old'})
    station_df = station_df.rename(columns={'site_name_9char': 'site_name'})

    # Create a new dataframe from combined_df that only contains four columns
    combined_df_unique_ss = combined_df_unique[['site_name', 'log_name', 'log_download_dt',
                                                'log_source']]

    # Merge stn_df with the subset dataframe
    merged_df = pd.merge(station_df, combined_df_unique_ss, on='site_name', how='left')

    # Rename columns so that the output has same column names as before + new columns
    merged_df = merged_df.rename(columns={'site_name': 'site_name_9char'})
    merged_df = merged_df.rename(columns={'site_name_old': 'site_name'})
    merged_df = merged_df.rename(columns={'log_name': 'latest_log_name'})
    merged_df = merged_df.rename(columns={'log_download_dt': 'latest_log_download_dt'})
    merged_df = merged_df.rename(columns={'log_source': 'latest_log_source'})
    # merged_df = merged_df.drop(columns=['site_name_9char'])

    merged_df['latest_log_download_dt'] = merged_df['latest_log_download_dt'].dt.strftime(
        '%Y-%m-%d %H:%M:%S')

    output_path = config.stn_csv_path.replace('stn_table', 'stn_table_new')
    merged_df.to_csv(output_path, index=False)
    print(f"Output saved at: {output_path}")
    print('Rename this file to stn_table.csv and run GREP again')

    return merged_df


def get_file_diff(log_dir, unique_values):
    dir_files = os.listdir(log_dir)

    # a) Loop over all files in this dir and find files which are not named in unique_values
    diff_in_dir = [file for file in dir_files if file not in unique_values]

    # b) Loop over all files in unique_values and find files which are not present in log_dir
    diff_in_unique = [file for file in unique_values if file not in dir_files]

    return diff_in_dir, diff_in_unique


def diff_logfiles_and_df_col(merged_data_df):
    # Get unique values
    unique_values = merged_data_df['log_name'].unique()

    # Get count of each unique value
    value_counts = merged_data_df['log_name'].value_counts()

    log_dir = '/media/hannes/suurketas/BARON/grep_ext/logfiles'

    diff_in_dir, diff_in_unique = get_file_diff(log_dir, unique_values)
    filters = data_manager.create_filters(merged_data_df)
    filtered_data1 = data_manager.filter_data(merged_data_df, 'full_df', filters, 'by_logname')
    filtered_data2 = data_manager.filter_data(merged_data_df, 'full_df', filters, 'by_sitename')
    print('end')


def main():
    mrgd_data_df = merge_all_data_dfs()
    # diff_logfiles_and_df_col(mrgd_data_df)
    stn_df = read_stn_csv_as_df()
    add_logfile_col_to_stn_csv(mrgd_data_df, stn_df)


if __name__ == '__main__':
    main()

