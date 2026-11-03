import os
from zipfile import ZipFile, BadZipfile
import subprocess


def unzip_brazil_ibge_rinex_file_test(rinex_full_fn):
    """
    A test function for extracting Brazil IBGE RINEX zip files.
    :param rinex_full_fn: full path to Brazil IBGE RINEX zip file
    """
    print('----------')
    print('Trying to unzip Brazil IBGE RINEX zip file')
    try:
        with ZipFile(rinex_full_fn, 'r') as zipf:  # If zip is corrupted than this line fails and BadZipfile exception is used
            file_inside_zip = None
            # Loop through the filenames in the zip looking for one ending in 'd'
            for filename in zipf.namelist():
                print(filename)
                if filename.endswith('d') or filename.endswith('D') or filename.endswith('O') or \
                        filename.endswith('o'):
                    file_inside_zip = filename
                    break
            # If we found a file ending in 'd'
            if file_inside_zip is not None:
                # Determine the directory of the unzipped file
                unzip_dir = os.path.dirname(rinex_full_fn)
                # Extract the 'o' file into the unzipped directory
                zipf.extract(file_inside_zip, path=unzip_dir)
        # Once done with the extracted file, remove it
        os.remove(rinex_full_fn)

    except BadZipfile:
        print('Bad zip file. The download process must be repeated!')

    except Exception as ex:
        print(' Unknown exception in unzip_brazil_ibge_rinex_file_test(): %s' % ex)
        raise ex

    return True


def unzip_sp3_file_test(sp3_full_fn):
    print('----------')
    print('Trying to unzip sp3.Z file using gunzip')
    rinex_full_fn = '/home/kr/Downloads/spbp0731.zip'
    sp3_full_fn = '/Data/C3S2/abi/igs19924.sp3.Z'
    unzip_brazil_ibge_rinex_file_test(rinex_full_fn)
    unzip_sp3_file_test(sp3_full_fn)

    try:
        result = subprocess.run(['gunzip', sp3_full_fn], check=True)
    except subprocess.CalledProcessError as e:
        print(f"gunzip operation failed with error: {e.returncode} - The download process must be repeated!")


