import time
import re
import difflib

def validate_title(title):
    """Clean filenames by replacing illegal characters with underscores."""
    r_str = r"[\/\\\:\*\?\"\<\>\|\n]"
    new_title = re.sub(r_str, "_", title)
    return new_title

def get_local_time():
    """Get current time formatted as YYYY-MM-DD HH:MM:SS."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def get_equal_rate(str1, str2):
    """Calculate similarity rate between two strings."""
    return difflib.SequenceMatcher(None, str1, str2).quick_ratio()

def bytes_to_string(byte_count):
    """Convert bytes to human-readable string (KB, MB, GB, etc.)."""
    suffix_index = 0
    while byte_count >= 1024:
        byte_count /= 1024
        suffix_index += 1

    return '{:.2f}{}'.format(
        byte_count, [' bytes', 'KB', 'MB', 'GB', 'TB'][suffix_index]
    )
