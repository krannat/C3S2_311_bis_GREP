import os
import datetime
import xmltodict
import json
import requests
from bs4 import BeautifulSoup
import logging
import time

from dbio import shared_funcs
from t_box import tools
import pysftp
import subprocess

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def get_rinex_list_geoscience_australia(year, doy):
    """
    Function to get the daily Geoscience Australia observation RINEX list from the AWS S3 bucket (via the 'aws s3 ls'
    command), keeping only 'YYd', 'YYo' and '_MO' files. Retries up to 5 times.
    :param year: The year of the RINEX files.
    :param doy: The day of year of the RINEX files.
    :return: Case-insensitively sorted list of RINEX file names, or None on failure.
    """
    cmd = [
        'aws', 's3', '--region=eu-north-1', '--no-sign-request', 'ls',
        f's3://ga-gnss-data-rinex-v1/public/daily/{year}/{str(doy).zfill(3)}/'
    ]

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            output = subprocess.check_output(cmd)
            output = output.decode('utf-8')  # convert bytes to string
            files = output.split('\n')  # split output into list of lines
            filenames = [f.split(' ')[-1] for f in files if
                         f]  # split lines into parts and take the last one, which is filename

            obs_rinex_list = []
            for filename in filenames:
                fs = filename.split('.')
                yr = str(year)[-2:]
                yyd, yyo, ymo = yr + 'd', yr + 'o', '_MO'
                if (yyd in fs[1]) or (yyo in fs[1]) or (ymo in fs[0]):
                    obs_rinex_list.append(filename)

            return sorted(obs_rinex_list, key=str.casefold)

        except subprocess.CalledProcessError:
            if attempt < max_attempts - 1:  # if it's not the final attempt
                err_log.warning(' Failed to get RINEX list for auspos. Retrying in 10 seconds...')
                time.sleep(10)  # wait for 10 seconds before retrying
            else:  # if it's the final attempt
                err_log.warning(' Failed to get RINEX list for auspos after 5 attempts. Aborting...')
                return None


def remove_duplicated_sites_from_sites_list(mixed_list):
    """
    Function to remove sites with duplicated RINEX files from a list; sites having more than one file are dropped
    entirely and logged.
    :param mixed_list: List of RINEX file names.
    :return: Sorted list of RINEX file names of sites without duplicates.
    """
    rinex_list = mixed_list  # gets list of files from URL
    site_dict = {}  # create dictionary for all sites, including duplicates for each site (if present)

    for file in rinex_list:
        site_acr = file[:4].lower()
        if site_acr not in site_dict:
            site_dict[site_acr] = {}
        site_dict[site_acr][file.rsplit('.', 2)[-2]] = file

    stn_dup_list = []  # loop over dict and find stations with more than one file available
    for stn, stn_files in site_dict.items():
        if len(stn_files) == 2:  # both .gz and .Z available
            stn_dup_list.append(stn)
        elif len(stn_files) == 3:
            print('More than two duplicates were found for %s. Modify scripts to deal with this!' % stn)
    res_log.info(' Duplicates were found for the following sites (%s in total): \n%s' %
                 (len(stn_dup_list), stn_dup_list))

    # create new list from dict that does NOT contain duplicates
    rinex_list_without_dup = []
    for stn, stn_files in site_dict.items():
        try:  # if .crx.gz file present
            tmp_stn_keys = list(stn_files.keys())  # keys to a list

            for i in range(len(tmp_stn_keys)):
                if tmp_stn_keys[i] and (stn not in stn_dup_list):
                    rinex_list_without_dup.append(stn_files[tmp_stn_keys[i]])
        except KeyError:  #
            print('KeyError in remove_duplicated_sites_from_sites_list() ...')

    return sorted(rinex_list_without_dup)


def params_from_xml_log(xml_file_name):
    """
    Function to parse a GeodesyML (XML) site log and extract site identification/location, receiver epochs and
    antenna epochs.
    :param xml_file_name: The path of the XML site log file.
    :return: Tuple (site_id_and_loc, rec_epochs, ant_epochs) of lists, or (-1, -1, -1) if the file is missing, empty or not XML.
    """

    try:
        if os.path.getsize(xml_file_name) == 0:
            err_log.error(' Logfile is empty: %s' % xml_file_name)
            return -1, -1, -1
        # if file does not start with '<?xml version=' in first line, it is not an XML-file, reason whatever
        with open(xml_file_name) as x_file:
            first_line = x_file.readline()
            if '<?xml version=' not in first_line:
                err_log.error(' Not XML file: %s' % xml_file_name)
                return -1, -1, -1
    except FileNotFoundError as e:
        err_log.error(' File %s not found in params_from_xml_log(), error: %s' % (xml_file_name, e))
        return -1, -1, -1

    js = xml_to_json(xml_file_name)  # string-json
    dict_x = json.loads(js)  # string-json --> json
    # print(json.dumps(dict_x, indent=4))  # just for reading ...

    s_log = dict_x.get('geo:GeodesyML').get('geo:siteLog')
    sid = s_log.get('geo:siteIdentification')

    s_name = sid.get('geo:SiteIdentification').get('geo:fourCharacterID')
    site_name_long = sid.get('geo:SiteIdentification').get('geo:siteName')
    approx_pos = s_log.get('geo:siteLocation').get('geo:SiteLocation').get('geo:approximatePositionITRF')
    xyz = approx_pos.get('geo:cartesianPosition').get('gml:Point').get('gml:pos')
    # added try/except for AttributeError  -- it may happen that geodeticPosition is not given! In fact, also not used
    geodetic_pos = ''
    try:
        geodetic_pos = approx_pos.get('geo:geodeticPosition').get('gml:Point').get('gml:pos')
    except AttributeError as e:
        # If we still have Cartesian XYZ, we can calculate the geodetic_position [lat, lon, elev.]
        s_xyz = xyz.split()
        g_pos = shared_funcs.cartesian2geodetic(float(s_xyz[0]), float(s_xyz[1]), float(s_xyz[2]))
        # make it a string with coordinates separated by 'space'
        geodetic_pos = str(g_pos[0]) + ' ' + str(g_pos[1]) + ' ' + str(g_pos[2])
        err_log.warning(' Geodetic position not given for site %s, calculated from xyz %s' % (s_name, xyz))
        pass

    site_id_and_loc = [s_name, site_name_long, xyz, geodetic_pos]

    # rec_epochs = [] for receiver by epochs
    rec_epochs = []
    rec_tmp_epoch = []

    # XML to JSON conversion works differently for only one receiver or antenna epoch's. In case of epochs > 1 it
    # generates a list abject, otherwise just one dictionary!!!
    rec = s_log.get('geo:gnssReceiver')
    if isinstance(rec, list):
        # print('rec is a list')
        rec[0].get('geo:GnssReceiver').get('geo:manufacturerSerialNumber')
        for i in range(len(rec)):
            rec_serial_number = rec[i].get('geo:GnssReceiver').get('geo:manufacturerSerialNumber')
            try:
                rec_type = rec[i].get('geo:GnssReceiver').get('geo:igsModelCode').get('@codeListValue')
            except AttributeError as e:
                print(e)
                rec_type = ''  # Finally, missing receiver type will rise error 30 in comparison results
                err_log.error('Attribute error with GnssReceiver, site: %s: , %s' % (s_name, e))

            rec_firmware = rec[i].get('geo:GnssReceiver').get('geo:firmwareVersion')
            rec_date_installed = rec[i].get('geo:GnssReceiver').get('geo:dateInstalled')

            if i == len(rec) - 1:  # if list does not end with "unknown", then dateRemoved is a String
                #  for antenna
                if isinstance(rec[i].get('geo:GnssReceiver').get('geo:dateRemoved'), str):
                    rec_date_removed = rec[i].get('geo:GnssReceiver').get('geo:dateRemoved')
                    tmp_rec_pars = [rec_date_installed, rec_date_removed, rec_serial_number, rec_type, rec_firmware]
                    rec_tmp_epoch.append(tmp_rec_pars)
                    rec_epochs.append(rec_tmp_epoch)
                    break

                try:
                    if rec[i].get('geo:GnssReceiver').get('geo:dateRemoved').get('@indeterminatePosition') == 'unknown':
                        rec_date_removed = 'unknown'
                        tmp_rec_pars = [rec_date_installed, rec_date_removed, rec_serial_number, rec_type, rec_firmware]
                        rec_tmp_epoch.append(tmp_rec_pars)
                        rec_epochs.append(rec_tmp_epoch)
                        break
                except AttributeError as e:
                    err_log.error('Attribute error with GnssReceiver dates, site: %s: , %s' % (s_name, e))

            rec_date_removed = rec[i].get('geo:GnssReceiver').get('geo:dateRemoved')
            tmp_rec_pars = [rec_date_installed, rec_date_removed, rec_serial_number, rec_type, rec_firmware]
            rec_tmp_epoch.append(tmp_rec_pars)
    else:
        rec_serial_number = rec.get('geo:GnssReceiver').get('geo:manufacturerSerialNumber')
        rec_type = rec.get('geo:GnssReceiver').get('geo:igsModelCode').get('@codeListValue')
        rec_firmware = rec.get('geo:GnssReceiver').get('geo:firmwareVersion')
        rec_date_installed = rec.get('geo:GnssReceiver').get('geo:dateInstalled')

        try:
            if rec.get('geo:GnssReceiver').get('geo:dateRemoved').get('@indeterminatePosition') == 'unknown':
                rec_date_removed = 'unknown'
        except AttributeError:
            rec_date_removed = rec.get('geo:GnssReceiver').get('geo:dateRemoved')

        tmp_rec_pars = [rec_date_installed, rec_date_removed, rec_serial_number, rec_type, rec_firmware]
        rec_tmp_epoch.append(tmp_rec_pars)
        rec_epochs.append(rec_tmp_epoch)

    ant = s_log.get('geo:gnssAntenna')  # list of antenna directories
    ant_epochs = []
    ant_tmp_epoch = []

    # ... the same as for rec for case list and if not
    if isinstance(ant, list):
        # loop over all subdirectories,
        for i in range(len(ant)):
            ant_serial_number = ant[i].get('geo:GnssAntenna').get('geo:manufacturerSerialNumber')
            ant_x = ant[i].get('geo:GnssAntenna').get('geo:igsModelCode').get('@codeListValue').split()
            ant_type = ant_x[0]
            ant_radome = ant_x[1]
            arp_up_ecc = ant[i].get('geo:GnssAntenna').get('geo:marker-arpUpEcc.')
            arp_north_ecc = ant[i].get('geo:GnssAntenna').get('geo:marker-arpNorthEcc.')
            arp_east_ecc = ant[i].get('geo:GnssAntenna').get('geo:marker-arpEastEcc.')
            alignment_from_true_north = ant[0].get('geo:GnssAntenna').get('geo:alignmentFromTrueNorth')
            date_installed = ant[i].get('geo:GnssAntenna').get('geo:dateInstalled')
            # break the loop if all directories checked
            if i == len(ant) - 1:
                if isinstance(ant[i].get('geo:GnssAntenna').get('geo:dateRemoved'), str):
                    date_removed = ant[i].get('geo:GnssAntenna').get('geo:dateRemoved')
                    tmp_pars = [date_installed, date_removed, ant_serial_number, ant_type, ant_radome, arp_up_ecc,
                                arp_north_ecc, arp_east_ecc, alignment_from_true_north]
                    ant_tmp_epoch.append(tmp_pars)
                    ant_epochs.append(ant_tmp_epoch)
                    break
                try:
                    if ant[i].get('geo:GnssAntenna').get('geo:dateRemoved').get('@indeterminatePosition') == 'unknown':
                        date_removed = 'unknown'
                        tmp_pars = [date_installed, date_removed, ant_serial_number, ant_type, ant_radome, arp_up_ecc,
                                    arp_north_ecc, arp_east_ecc, alignment_from_true_north]
                        ant_tmp_epoch.append(tmp_pars)
                        ant_epochs.append(ant_tmp_epoch)
                        break
                except AttributeError as e:
                    err_log.error('AttributeError with GnssAntenna, site: %s, i= %s, %s' % (sid, str(i), e))

            date_removed = ant[i].get('geo:GnssAntenna').get('geo:dateRemoved')
            tmp_pars = [date_installed, date_removed, ant_serial_number, ant_type, ant_radome, arp_up_ecc,
                        arp_north_ecc, arp_east_ecc, alignment_from_true_north]
            ant_tmp_epoch.append(tmp_pars)
    else:
        # print('ant is a dictonary')
        ant_serial_number = ant.get('geo:GnssAntenna').get('geo:manufacturerSerialNumber')
        ant_x = ant.get('geo:GnssAntenna').get('geo:igsModelCode').get('@codeListValue').split()
        ant_type = ant_x[0]
        # It can be that ant type is not given together with a radome. In case of IndexError
        try:
            ant_radome = ant_x[1]
        except IndexError as e:
            ant_radome = ant.get('geo:GnssAntenna').get('geo:antennaRadomeType').get('#text')
        arp_up_ecc = ant.get('geo:GnssAntenna').get('geo:marker-arpUpEcc.')
        arp_north_ecc = ant.get('geo:GnssAntenna').get('geo:marker-arpNorthEcc.')
        arp_east_ecc = ant.get('geo:GnssAntenna').get('geo:marker-arpEastEcc.')
        alignment_from_true_north = ant.get('geo:GnssAntenna').get('geo:alignmentFromTrueNorth')
        date_installed = ant.get('geo:GnssAntenna').get('geo:dateInstalled')
        # break the loop if all directories checked
        # if i == len(ant) - 1:

        try:
            if ant.get('geo:GnssAntenna').get('geo:dateRemoved').get('@indeterminatePosition') == 'unknown':
                date_removed = 'unknown'
        except AttributeError:
            date_removed = ant.get('geo:GnssAntenna').get('geo:dateRemoved')

        tmp_pars = [date_installed, date_removed, ant_serial_number, ant_type, ant_radome, arp_up_ecc,
                    arp_north_ecc, arp_east_ecc, alignment_from_true_north]
        ant_tmp_epoch.append(tmp_pars)
        ant_epochs.append(ant_tmp_epoch)
    # print('here we are')
    return site_id_and_loc, rec_epochs, ant_epochs


def get_site_par_by_date_from_log(site_inf, receiver_inf, antenna_inf, year, doy):
    """
    Function to find the receiver and antenna epochs from site log data that are valid for the given year and day of
    year. On section 3/4 format errors, rec_data and/or ant_data are returned as empty lists.
    :param site_inf: List with site name, long site name, XYZ and geodetic position.
    :param receiver_inf: List of lists with receiver epochs.
    :param antenna_inf: List of lists with antenna epochs.
    :param year: The year (int).
    :param doy: The day of year (int).
    :return: Tuple (rec_data, ant_data, format_errors), where format_errors lists section 3/4 time-label errors.
    """
    # /Data/C3S2/AUSTRALIA_RINEX_test/2023/001/ALIC00AUS_R_20230010000_01D_30S_MO.crx
    # "geo:dateInstalled": "1994-05-15T00:00:00.000Z",
    # "geo:dateRemoved": "1999-07-31T01:00:00.000Z",
    # date from new format filename -- YYYYDOY
    # date from old type of filenames like albh0010.23d -- DOY and YY

    # test ALIC year = 2021, doy = 002

    s_name, site_name_long, xyz, geodetic_pos = site_inf
    rec_epochs = receiver_inf
    ant_epochs = antenna_inf
    rec_data, ant_data = [], []
    format_errors = ['', '']

    my_date = tools.doy_to_date(str(doy), str(year))
    dt = datetime.datetime.strptime(my_date, '%Y-%m-%d')

    # search receiver data for year and doy
    lr = len(rec_epochs[0])
    for i in range(lr):
        try:
            tmp_installed = rec_epochs[0][i][0]
            tmp_removed = rec_epochs[0][i][1]
            if isinstance(tmp_removed, dict):
                tmp_key = tmp_removed.keys()
                k_list = list(tmp_key)
                k_l = k_list[0]
                tmp_removed = tmp_removed.get(k_l)
            #tmp_inst_old = datetime.datetime.strptime(tmp_installed, '%Y-%m-%dT%H:%M:%S.%fZ')

            # check if the first epoch is also the last
            if ((tmp_removed == 'unknown') or (tmp_removed == '(CCYY-MM-DDThh:mmZ)')) and (i < 1):
                rec_data = rec_epochs[0][i]     # first epoch is still actual, no changes in receivers' logfile
                break
            # get tmp_removed datetime if not the last epoch
            if not ((tmp_removed == 'unknown') or (tmp_removed == '(CCYY-MM-DDThh:mmZ)')):
                tmp_rem_old = datetime.datetime.strptime(tmp_removed, '%Y-%m-%dT%H:%M:%S.%fZ')

            # IF i < lr and tmp_removed is not a string, it is an ERROR in SECTION 3 (RECEIVER DATA) and this kind of
            #  error cannot be handled with comparing script. Writing 'ERROR-30' to rec_data
            if i < lr and not isinstance(tmp_removed, str):
                print('Error in receiver time-label format, messy section 3, site:', s_name)
                format_errors[0] = 'section_3_format_error'
                break

            tmp_inst = datetime.datetime.strptime(tmp_installed, '%Y-%m-%dT%H:%M:%S.%fZ')

            if (dt > tmp_rem_old) and (dt < tmp_inst):
                err_log.warning(
                    f'Date {my_date} not covering any receiver installed-removed epochs in a logfile {s_name}!')
                break
            else:
                if not ((tmp_removed == 'unknown') or (tmp_removed == '(CCYY-MM-DDThh:mmZ)')): # if tmp_removed = unknown or ...
                    tmp_rem = datetime.datetime.strptime(tmp_removed, '%Y-%m-%dT%H:%M:%S.%fZ')
                else:
                    if dt > tmp_inst:   # if dt fits into the last epoch ending with unknown or ...
                        rec_data = rec_epochs[0][i]
                    else:
                        err_log.warning(
                            f'Date {my_date} not covering any receiver installed-removed epochs in logfile {s_name}!')
                        break

            if tmp_inst <= dt <= tmp_rem:   # if dt fits into an epoch
                rec_data = rec_epochs[0][i]
                break

        except TypeError as e:
            format_errors[0] = 'section_3_format_error'
            err_log.error('Error in receiver time-label format, messy section 3, site: %s, %s' % (s_name, e))
            break

    # search antenna data for year and doy
    la = len(ant_epochs[0])
    for i in range(la):
        try:
            tmp_installed = ant_epochs[0][i][0]
            tmp_removed = ant_epochs[0][i][1]

            if isinstance(tmp_removed, dict):
                tmp_key = tmp_removed.keys()
                k_list = list(tmp_key)
                k_l = k_list[0]
                tmp_removed = tmp_removed.get(k_l)

            # check if the first epoch is also the last
            if ((tmp_removed == 'unknown') or (tmp_removed == '(CCYY-MM-DDThh:mmZ)')) and (i < 1):
                ant_data = ant_epochs[0][i]  # first epoch is still actual, no changes in antenna's logfile
                break
            # get tmp_removed datetime if not the last epoch
            if not ((tmp_removed == 'unknown') or (tmp_removed == '(CCYY-MM-DDThh:mmZ)')):
                tmp_rem_old = datetime.datetime.strptime(tmp_removed, '%Y-%m-%dT%H:%M:%S.%fZ')

            if i < la and not isinstance(tmp_removed, str):
                print('Error in antenna time-label format, messy section 3, site:', s_name)
                format_errors[1] = 'section_4_format_error'
                break

            tmp_inst = datetime.datetime.strptime(tmp_installed, '%Y-%m-%dT%H:%M:%S.%fZ')

            if (dt > tmp_rem_old) and (dt < tmp_inst):
                err_log.warning(
                    f'Date {my_date} not covering any installed-removed epochs in the antenna logfile {s_name}!')
                break
            else:
                if not ((tmp_removed == 'unknown') or (tmp_removed == '(CCYY-MM-DDThh:mmZ)')): # if tmp_removed = unknown or ...
                    tmp_rem = datetime.datetime.strptime(tmp_removed, '%Y-%m-%dT%H:%M:%S.%fZ')
                else:
                    if dt > tmp_inst:   # if det fits into the last epoch ending with unknown or ...
                        ant_data = ant_epochs[0][i]
                    else:
                        err_log.warning(
                            f'Date {my_date} not covering any installed-removed epochs in the antenna logfile {s_name}!')
                        break

            if tmp_inst <= dt <= tmp_rem:  # if dt fits into an epoch
                ant_data = ant_epochs[0][i]
                break

        except TypeError as e:
            # print('Error in antenna time-label format, messy section 4, site: ' + s_name + ' ' + e)
            format_errors[1] = 'section_4_format_error'
            err_log.error('Error in antenna time-label format, messy section 4, site: %s, %s' % (s_name, e))
            break
    # print('Receiver and antenna data for RINEX year and DOY extracted for site ', s_name)
    return rec_data, ant_data, format_errors


def xml_to_json(xml_file_name):
    """
    Function to read an XML file and convert it into a JSON string.
    :param xml_file_name: The path of the XML file.
    :return: The JSON string of the parsed XML document.
    """
    with open(xml_file_name) as fd:
        doc = xmltodict.parse(fd.read())
    # print()
    # return json.dumps(doc, indent=4)  # readable result (string)
    return json.dumps(doc)
