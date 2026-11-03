from t_box import stn_table_from_dfs


def find_year_doy_wo_logfiles(merged_df, network):
    # Filter DataFrame where 'in_NETWORK' is True
    network_df = merged_df[(merged_df[f'in_{network}']) & (merged_df['rinex_source'] == network)]

    # Extract year and day of year (doy) from 'rinex_name'
    network_df['year'] = network_df['rinex_name'].str.slice(12, 16)  # Extract the year
    network_df['doy'] = network_df['rinex_name'].str.slice(16, 19)  # Extract the doy

    # Group by year and doy and check if all 'log_name' entries are null in each group
    group_df = network_df.groupby(['year', 'doy'])
    df_combinations = group_df.filter(lambda x: x['log_name'].isnull().all())

    # Select year and doy columns
    df_combinations = df_combinations[['year', 'doy']].drop_duplicates()
    print('A')


if __name__ == '__main__':
    mrgd_df = stn_table_from_dfs.merge_all_data_dfs()
    ntwrk = 'igs'
    find_year_doy_wo_logfiles(mrgd_df, ntwrk)
