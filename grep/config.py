

proc_split_year = 2000
# RINEX files present, only download logfiles (if needed) and redo the RINEX/logfile comparison for the DOY processed
correct_df_for_doy_logfile_info = False  # if True, then not downloading RINEX

BASE_PATH = '/where_to_install_grep/'
networks = ['igs', 'auspos', 'cacs', 'epn', 'sirgas', 'us_cors', 'unavco', 'uruguay', 'brazil_ibge', 'greenland', 'chile']

logfile_archive_path = BASE_PATH + 'logfiles/'
logfile_err_path = BASE_PATH + 'logfiles_err/'

rinex_archive_path = BASE_PATH + 'RINEX/'
rinex_xyz_err_archive_path = BASE_PATH + 'RINEX_err/'
rinex_v1_archive_path = BASE_PATH + 'RINEX_v1/'

epn_logfiles_url_OLD = 'https://epncb.oma.be/ftp/station/log_9char/'
epn_logfiles_url = 'https://epncb.oma.be/pub/station/log/'
epn_rinex_url = 'https://epncb.oma.be/pub/obs/'

daily_brdc_path = BASE_PATH + 'brdc/'
anubis_executable = '/home/grep_user/Tools/anubis-3.9-lin-static-64b'
rx3name_executable = '/home/grep_user/Tools/RX3name'
rin1to2_executable = '/home/grep_user/Tools/gfzrnx_2.2.0_lx64'

stn_csv_path = BASE_PATH + 'stns/stn_table.csv'
pkl_path = BASE_PATH + 'pickles/'

logging_path = BASE_PATH + 'logging/'
rinex_logfile_header_file = BASE_PATH + 'rinex_logfile_header_file.txt'
df_backups_path = BASE_PATH + 'df_backups/'

igs_log_url_OLD = 'https://files.igs.org/pub/station/log_9char/'
igs_log_url = 'https://files.igs.org/pub/station/log/'
igs_log_url_decommissioned = 'https://files.igs.org/pub/station/finallog/'
igs_rinex_url = 'https://cddis.nasa.gov/archive/gnss/data/daily/'
cacs_rinex_url = 'https://cacsa.nrcan.gc.ca/gps/data/gpsdata/'
cacsa_logfiles_remote_url = 'https://cacsa.nrcan.gc.ca/gps/station_logs/'

us_cors_rinex_url_amazon = 'https://noaa-cors-pds.s3.amazonaws.com/rinex/'
us_cors_rinex_url = 'https://geodesy.noaa.gov/corsdata/rinex/'

uscors_logfiles_url = 'https://geodesy.noaa.gov/corsdata/station_log/'
us_cors_logfiles_url_amazon = 'https://noaa-cors-pds.s3.amazonaws.com/station_log/'

auspos_rinex_url = 'https://data.gnss.ga.gov.au/api/rinexFiles/'
auspos_rinex_url_amazon = 's3://ga-gnss-data-rinex-v1/public/daily/'
auspos_rinex_url_web_api = 'https://data.gnss.ga.gov.au/api/rinexFiles/'
auspos_logfiles_url = 'https://gws.geodesy.ga.gov.au/siteLogs/'

unavco_rinex_url = 'https://gage-data.earthscope.org/archive/gnss/rinex/obs/'
unavco_logfiles_url = 'https://data.unavco.org/archive/gnss/logs/'
unavco_token_path = '/Data/C3S2/GREP_EXT/unavco_tokens'

uchile_rinex_url = 'https://gps.csn.uchile.cl/data/'

brazil_ibge_rinex_url = 'https://geoftp.ibge.gov.br/informacoes_sobre_posicionamento_geodesico/rbmc/dados/'
brazil_ibge_rinex3_url = 'https://geoftp.ibge.gov.br/informacoes_sobre_posicionamento_geodesico/rbmc/dados_RINEX3/'
brazil_ibge_logfiles_url = 'https://geoftp.ibge.gov.br/informacoes_sobre_posicionamento_geodesico/rbmc/relatorio/log_sirgas/'

uruguay_rinex_hist_url = 'sftp://sftp.igm.gub.uy/sftpserver/'
uruguay_rinex_latest_url = 'ftp://pp.igm.gub.uy/hatanaka/'
uruguay_log_url = 'ftp://pp.igm.gub.uy/hatanaka/Logfiles'

greenland_hostname = 'ftp.dataforsyningen.dk'
greenland_username = 'grep_user'
greenland_password = 'grep_user_pwd'
greenland_main_url = f'ftps://{greenland_username}:{greenland_password}@{greenland_hostname}:990/GNSS/'
greenland_rinex2_url = f'{greenland_main_url}RINEX2/GRL/'
greenland_rinex3_url = f'{greenland_main_url}RINEX3/GRL/'
greenland_logfiles_url = f'{greenland_main_url}SITELOGS/'

known_hosts = '/home/kr/.ssh/known_hosts'  # path to your known hosts file

# For GEOID MODEL
egm_path = '/home/kr/EGM2008_WGS84/'  # geoid model EGM2008

# For CHILE
chile_rinex_url = 'https://gps.csn.uchile.cl/data/'
chile_rinex_temp_down_path = 'free_choice'    # For tests in BBox2
download_chile = False  # True, if running normal mode in VM
