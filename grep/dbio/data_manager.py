import pickle
import os
import pandas as pd
from datetime import datetime
from grep import config
from tabulate import tabulate


def read_df(pickle_name):
    """
    Function to read a pickle file from the configured pickle directory.
    :param pickle_name: The name of the pickle file to be read (relative to config.pkl_path).
    :return: The data read from the pickle file.
    """
    with open(os.path.join(config.pkl_path, pickle_name), 'rb') as f:
        data = pickle.load(f)
    return data


def filter_data(dframe, dframe_name, filter_conditions, filter_name):
    """
    Function to filter a DataFrame by a named filter condition and print the row counts before and after filtering
    together with the first 5 rows of the filtered data.
    :param dframe: The pandas DataFrame to be filtered.
    :param dframe_name: The name of the DataFrame to print in the overview.
    :param filter_conditions: A dictionary mapping condition names to Boolean pandas Series.
    :param filter_name: The name of the filter condition to apply (raises ValueError if not found).
    :return: The filtered DataFrame that satisfies the named filter condition.
    """
    pd.set_option('display.max_columns', None)

    series_condition = filter_conditions.get(filter_name)
    if series_condition is None:
        raise ValueError(f"No such filter: '{filter_name}'")

    row_count = len(dframe.index)
    print(f'Number of rows in {dframe_name} before filtering: {row_count}')

    # apply filter condition
    condition = series_condition
    # condition = condition.fillna(False)
    filtered_df = dframe[condition]

    print('Example 5 lines using such filter:')
    print(tabulate(filtered_df.head(), headers='keys', tablefmt='pretty'))

    row_count = len(filtered_df.index)
    print(f'Number of rows in {dframe_name} after filtering: {row_count}')

    return filtered_df


def delete_rows_by_cond(dframe, col_name, condition):
    """
    Function to delete rows from a DataFrame where the given column equals the given value.
    :param dframe: The DataFrame to delete rows from.
    :param col_name: The name of the column to apply the condition on.
    :param condition: The value; rows whose column value equals it are removed.
    :return: The DataFrame without the matching rows.
    """
    return dframe.loc[dframe[col_name] != condition]


def delete_rows_by_series_mask(dframe, mask):
    """
    Function to delete rows from a DataFrame where the given Boolean Series (mask) is True.
    :param dframe: The DataFrame to delete rows from.
    :param mask: The Boolean Series marking the rows to delete.
    :return: The DataFrame without the masked rows.
    """
    return dframe.loc[~mask]


def write_df_to_csv(dframe, file_path):
    """
    Function to write a DataFrame to a CSV file (without index).
    :param dframe: The DataFrame to be written to CSV.
    :param file_path: The path of the CSV file to be created.
    :return: None.
    """
    dframe.to_csv(file_path, index=False)


def create_filters(dframe):
    """
    Function to create a dictionary of predefined Boolean filter conditions (by network, RINEX name, site name,
    log name, missing log name and download datetime ranges) for the given DataFrame.
    :param dframe: The DataFrame containing the data.
    :return: A dictionary mapping filter names to Boolean pandas Series.
    """
    # Define datetime range
    start_datetime = datetime.strptime("2025-02-12 15:59:00", "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.strptime("2025-02-12 16:30:00", "%Y-%m-%d %H:%M:%S")

    filter_conditions = {
        # 'by_network': (dframe['in_auspos']) & (dframe['in_cacs']),
        'by_network': (dframe['in_unavco']),
        'by_rinexname': (dframe['rinex_name'] == 'AUT000USA_R_20132150000_01D_00U_MO.rnx.gz'),
        # 'by_sitename': (dframe['site_name'] == 'CTI400USA'),
        # 'by_sitename': (dframe['site_name'] == 'TAT200CAN'),
        'by_sitename': (dframe['site_name'] == 'P39200USA'),
        'by_logname': (dframe['log_name'] == 'bcov_20190307.log'),
        'by_logname_missing': (dframe['log_name'].isnull()),
        'by_log_datetime_range':
            (dframe['log_download_dt'] >= start_datetime) & (dframe['log_download_dt'] <= end_datetime),
        'by_rinex_datetime_range':
            (dframe['rinex_download_dt'] >= start_datetime) & (dframe['rinex_download_dt'] <= end_datetime)
    }

    return filter_conditions


def yearly_to_monthly_pkl(year):
    """
    Function to split a yearly pickle file into monthly pickle files based on the RINEX file names.
    Writes the monthly pickles to config.pkl_path/<year>/<year>_<month>.pkl.
    :param year: The year for which data will be converted from yearly to monthly pickles.
    :return: None.
    """
    year = int(year)
    for year in range(year, year + 1):
        data_file = os.path.join(config.pkl_path, f'{year}.pkl')
        if os.path.exists(data_file):
            df_year = pd.read_pickle(data_file)
            df_year['rinex_datetime'] = df_year.apply(
                lambda row: datetime.strptime(row['rinex_name'].split('_')[2][:7], '%Y%j').strftime('%Y-%m'), axis=1)
            for month in df_year['rinex_datetime'].unique():
                df_month = df_year[df_year['rinex_datetime'] == month]
                year, month = month.split('-')
                month_path = os.path.join(config.pkl_path, f'{year}')
                if not os.path.exists(month_path):
                    os.makedirs(month_path)
                df_month = df_month.drop(columns=['rinex_datetime'])
                df_month.to_pickle(os.path.join(month_path, f'{year}_{month}.pkl'))


def df_dir_diff_files(df_grep):
    """
    Function to compare RINEX file names in a DataFrame with files in a hardcoded local directory
    and compute the differences in both directions (debugging helper).
    :param df_grep: The DataFrame containing a 'rinex_name' column.
    :return: None.
    """
    directory_path = '/media/hannes/suurketas/BARON/grep_ext/RINEX/2016/297'
    directory_files = os.listdir(directory_path)
    df_directory = pd.DataFrame(directory_files, columns=['rinex_name'])

    # Files in df_grep['rinex_name'] not present in the folder
    df_diff1 = df_grep[~df_grep['rinex_name'].isin(df_directory['rinex_name'])]

    # Files in the folder not present in df['rinex_name']
    df_diff2 = df_directory[~df_directory['rinex_name'].isin(df_grep['rinex_name'])]

    print('a')


def filter_df_by_criteria(df_name):
    """
    Function to read a pickled DataFrame, apply and print several predefined filters, compare against a local
    directory and write the DataFrame to a CSV backup file.
    :param df_name: The name of the pickle file (relative to config.pkl_path).
    :return: A dictionary of filter conditions created for the DataFrame.
    """
    df = read_df(df_name)
    df['in_unavco'] = df['in_unavco'].fillna(False)
    filters = create_filters(df)
    filtered_data1 = filter_data(df, df_name, filters, 'by_log_datetime_range')
    filtered_data2 = filter_data(df, df_name, filters, 'by_rinex_datetime_range')
    filtered_data3 = filter_data(df, df_name, filters, 'by_sitename')
    filtered_data4 = filter_data(df, df_name, filters, 'by_logname')
    filtered_data5 = filter_data(df, df_name, filters, 'by_network')
    df_dir_diff_files(filtered_data2)
    write_df_to_csv(df, os.path.join(config.df_backups_path, df_name.replace('.pkl', '.csv')))
    return filters


if __name__ == '__main__':
    pkl_name = '2018/2018_02.pkl'
    filters = filter_df_by_criteria(pkl_name)

    df = read_df(pkl_name)

    stn_df = df = pd.read_csv('/media/hannes/suurketas/BARON/grep_ext/stns/stn_table.csv')
    # Delete rows by compared_dt value range:
    # # Get the mask for the datetime range condition
    # mask = filters['by_compared_dt_range']
    # Use the mask to remove rows in the datetime range from the DataFrame
    # df = delete_rows_by_series_mask(df, mask)

    # df = delete_rows_by_cond(df, 'in_unavco', True)
    df = delete_rows_by_cond(df, 'site_name', 'P39200USA')

    df.to_pickle(os.path.join(config.pkl_path, pkl_name))
    write_df_to_csv(df, os.path.join(config.df_backups_path, pkl_name.replace('.pkl', '.csv')))
    print()
