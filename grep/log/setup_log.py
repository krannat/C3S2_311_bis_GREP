import logging
import config
from multiprocessing import Queue
import os
import shutil

logging_dir = config.logging_path

# Create a queue and a queue handler
log_queue = Queue(-1)  # no limit on message size
queue_listener = None


def write_dailylog(level=logging.INFO):
    """
    Function to set up the result and error loggers writing to daily.log and daily_errors.log in the logging directory.
    :param level: The logging level for both loggers.
    :return: Tuple (result, errors) of the result and error loggers.
    """
    global queue_listener
    formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Create a log file for regular messages (`resultpath`).
    resultpath = logging_dir + 'daily.log'
    result_file_handler = logging.FileHandler(resultpath)
    result_file_handler.setFormatter(formatter)

    result = logging.getLogger('logfile_result')
    result.setLevel(level)

    if not result.handlers:
        result.addHandler(result_file_handler)

    # Create an error log file (`errorpath`).
    errorspath = logging_dir + 'daily_errors.log'
    error_file_handler = logging.FileHandler(errorspath)
    error_file_handler.setFormatter(formatter)

    errors = logging.getLogger('logfile_errors')
    errors.setLevel(level)

    if not errors.handlers:
        errors.addHandler(error_file_handler)

    return result, errors

    
def copy_with_numbering(src_path, dest_dir):
    """
    Function to copy a file to a destination directory, adding _2, _3, ... (up to _100) to the name if it exists.
    :param src_path: The path of the file to be copied.
    :param dest_dir: The destination directory.
    :return: None. Raises RuntimeError if all numbered variants already exist.
    """
    filename = os.path.basename(src_path)
    name, ext = os.path.splitext(filename)
    dest_path = os.path.join(dest_dir, filename)

    if not os.path.exists(dest_path):
        shutil.copy2(src_path, dest_path)
        return

    # Try numbered variants
    for i in range(2, 101):
        numbered_name = f"{name}_{i}{ext}"
        numbered_path = os.path.join(dest_dir, numbered_name)
        if not os.path.exists(numbered_path):
            shutil.copy2(src_path, numbered_path)
            return

    raise RuntimeError(f"All filename variants from 2 to 100 already exist for {filename}")


def copy_daily_logfiles(result, errors, dest_dir):
    """
    Function to copy the log files of the result and error loggers to a destination directory (with numbering).
    :param result: The result logger.
    :param errors: The error logger.
    :param dest_dir: The destination directory.
    :return: None.
    """
    result_handler = result.handlers[0]
    result_src = result_handler.baseFilename
    copy_with_numbering(result_src, dest_dir)

    errors_handler = errors.handlers[0]
    errors_src = errors_handler.baseFilename
    copy_with_numbering(errors_src, dest_dir)


def rollover_logs():
    """
    Function to rotate daily.log and daily_errors.log by renaming them to .1, .2, ... (keeping up to 40 backups).
    Note: moves and overwrites files in the logging directory.
    :return: None.
    """
    max_backups = 40
    log_files = ['daily.log', 'daily_errors.log']

    for log_file in log_files:
        # Move existing log files
        for i in range(max_backups, 0, -1):  # Start from max_backups and decrement down to 0
            old_log = f"{log_file}.{i}"
            old_log_path = os.path.join(logging_dir, old_log)

            # If the old log file exists, move it to the next index
            if os.path.exists(old_log_path):
                new_log = f"{log_file}.{i + 1}"
                new_log_path = os.path.join(logging_dir, new_log)

                # Remove the old file at the new location, if it exists
                if os.path.exists(new_log_path):
                    os.remove(new_log_path)

                shutil.move(old_log_path, new_log_path)

        # Then, move the current log file
        current_log_path = os.path.join(logging_dir, log_file)
        if os.path.exists(current_log_path):
            shutil.move(current_log_path, os.path.join(logging_dir, f"{log_file}.1"))
