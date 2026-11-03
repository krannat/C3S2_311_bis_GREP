import requests
import urllib3
import logging
import time
import os
from compare import compare_rinex_log

res_log = logging.getLogger('logfile_result')
err_log = logging.getLogger('logfile_errors')


def rinex_requests_igs(prepared_req, pf_name, rinex_down_path, network, called_by_func):
    """
    Function to send a prepared request to IGS/CDDIS with browser-like headers, download the RINEX file and
    resolve its unzipped file name, retrying up to 5 times. A partially downloaded file is removed on failure.
    :param prepared_req: The prepared requests.Request to send.
    :param pf_name: The name of the RINEX file to download.
    :param rinex_down_path: The local directory to download the file to.
    :param network: The network name used in log messages.
    :param called_by_func: The name of the calling function used in log messages.
    :return: The unzipped file name, or None if access was forbidden or the download failed.
    """

    rep = 0
    max_retries = 5
    unzipped_file_name = None
    rinex_full_fn = os.path.join(rinex_down_path, pf_name)

    # Headers to improve reliability when contacting CDDIS/IGS
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Connection": "keep-alive",
        "Accept-Encoding": "gzip, deflate"
    }

    while not unzipped_file_name and rep < max_retries:

        try:
            if not os.path.exists(rinex_down_path):
                os.makedirs(rinex_down_path)

            # Send the prepared request using safe timeouts
            with requests.Session() as session:
                session.headers.update(headers)
                r = session.send(
                    prepared_req,
                    timeout=(5, 5),      # (connect timeout, read timeout)
                    stream=True
                )

            # 403 Forbidden → exit early (do NOT retry)
            if r.status_code == 403:
                err_log.warning(f' {network}: From rinex_requests() (called by {called_by_func}). '
                                                f'Forbidden access to {pf_name}. Skipping this RINEX.')
                return None

            # Any non-OK status → retry
            if r.status_code != 200:
                rep += 1
                continue

            # Safe download using iter_content, but with shorter read timeout
            with open(rinex_full_fn, "wb") as fd:
                for chunk in r.iter_content(chunk_size=1024):
                    fd.write(chunk)

            # Process & unzip
            rinex_lines, unzipped_file_name = compare_rinex_log.readlines_zipped(
                rinex_full_fn, get_only_path=True
            )
            if unzipped_file_name:
                break

        except (requests.exceptions.Timeout,
                requests.exceptions.RequestException,
                requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:

            err_log.warning(
                f" {network}: rinex_requests() (called by {called_by_func}). "
                f"Exception for {pf_name}: {ex}"
            )

        except Exception as ex:
            err_log.error(
                f" {network}: rinex_requests() (called by {called_by_func}). "
                f"Unexpected exception: {ex}"
            )

        # Schedule retry delay
        if rep < max_retries - 1:
            err_log.warning(
                f" {network}: rinex_requests() (called by {called_by_func}). "
                f"Retrying {pf_name} in 10 seconds..."
            )
            time.sleep(10)
            rep += 1
        else:
            break

    if not unzipped_file_name:
        err_log.error(
            f" {network}: rinex_requests() (called by {called_by_func}). "
            f"{pf_name} download aborted. Max retries reached."
        )
        if os.path.isfile(rinex_full_fn):
            os.remove(rinex_full_fn)

    return unzipped_file_name


def rinex_requests(prepared_req, pf_name, rinex_down_path, network, called_by_func):
    """
    Function to send a prepared request, download the RINEX file and resolve its unzipped file name, retrying up
    to 5 times. For Brazil IBGE an SSL error triggers a retry without certificate verification.
    A partially downloaded file is removed on failure.
    :param prepared_req: The prepared requests.Request to send.
    :param pf_name: The name of the RINEX file to download.
    :param rinex_down_path: The local directory to download the file to.
    :param network: The network name used in log messages.
    :param called_by_func: The name of the calling function used in log messages and SSL handling.
    :return: The unzipped file name, or None if access was forbidden or the download failed.
    """
    rep = 0  # maximum number of attempts if process unsuccessful
    max_retries = 5  # maximum number of attempts if process unsuccessful
    unzipped_file_name = None
    rinex_full_fn = os.path.join(rinex_down_path, pf_name)

    while not unzipped_file_name and rep < max_retries:
        try:
            if not os.path.exists(rinex_down_path):
                os.makedirs(rinex_down_path)
            with requests.Session() as session:
                try:
                    r = session.send(prepared_req, timeout=60, stream=True)
                except requests.exceptions.SSLError as ex:
                    if called_by_func == 'download_brazil_ibge_rinex_file':
                        err_log.warning(f' {network}: From rinex_requests() (called by {called_by_func}). '
                                        f'SSL verification failed for {pf_name}: {ex}. '
                                        f'Retrying with certificate verification disabled...')
                        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                        r = session.send(prepared_req, timeout=60, stream=True, verify=False)
                    else:
                        raise

            if r.status_code == 403:  # Access forbidden
                err_log.warning(f' {network}: From rinex_requests() (called by {called_by_func}). '
                                f'Forbidden access to {pf_name}. Skipping this RINEX.')
                return None

            if r.status_code != 200:
                rep += 1
                continue

            with open(rinex_full_fn, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=1000):
                    fd.write(chunk)

            rinex_lines, unzipped_file_name = compare_rinex_log.readlines_zipped(rinex_full_fn, get_only_path=True)
            if unzipped_file_name is not None:
                break

        except (requests.exceptions.Timeout, requests.exceptions.RequestException, requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as ex:
            err_log.warning(f' {network}: From rinex_requests() (called by {called_by_func}). '
                            f'Exception for {pf_name}: {ex}')

        except Exception as ex:
            err_log.error(f' {network}: From rinex_requests() (called by {called_by_func}). '
                          f'Exception for %s' % ex)

        # If not the last attempt, wait before retrying
        if rep < max_retries - 1:
            err_log.warning(f' {network}: From rinex_requests() (called by {called_by_func}). '
                            f'Retrying to download {pf_name} in 10 seconds...')
            time.sleep(10)
            rep += 1
        else:
            break

    if not unzipped_file_name:
        err_log.warning(f' {network}: From rinex_requests() (called by {called_by_func}). '
                      f'{pf_name} download aborted. Max retries reached.')
        if os.path.isfile(rinex_full_fn):
            os.remove(rinex_full_fn)

    return unzipped_file_name
