import os
import re
import socks
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

def parse_bool_env(env_var, default=False):
    """Parse boolean environment variable"""
    value = os.environ.get(env_var, '').lower()
    return value in ('true', '1', 'yes', 'on') if value else default

def get_proxy_from_env():
    """
    Automatically get proxy settings from environment variables
    Supports: SOCKS5_PROXY, SOCKS_PROXY, HTTP_PROXY, HTTPS_PROXY, ALL_PROXY
    Format: socks5://user:pass@host:port or http://host:port
    """
    proxy_env_vars = [
        'SOCKS5_PROXY', 'socks5_proxy',
        'SOCKS_PROXY', 'socks_proxy',
        'HTTP_PROXY', 'http_proxy',
        'HTTPS_PROXY', 'https_proxy',
        'ALL_PROXY', 'all_proxy'
    ]
    
    proxy_url = None
    for env_var in proxy_env_vars:
        proxy_url = os.environ.get(env_var)
        if proxy_url:
            break
    
    if not proxy_url:
        return None
    
    try:
        parsed = urlparse(proxy_url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
        
        if not host or not port:
            logger.warning(f"Invalid proxy URL format: {proxy_url}")
            return None
        
        if scheme in ('socks5', 'socks5h'):
            proxy_type = socks.SOCKS5
        elif scheme in ('socks4', 'socks4a'):
            proxy_type = socks.SOCKS4
        elif scheme in ('http', 'https'):
            proxy_type = socks.HTTP
        else:
            logger.warning(f"Unsupported proxy type: {scheme}")
            return None
        
        if username and password:
            proxy = (proxy_type, host, port, True, username, password)
        else:
            proxy = (proxy_type, host, port)
        
        logger.info(f"Using proxy: {scheme}://{host}:{port}")
        return proxy
    except Exception as e:
        logger.error(f"Failed to parse proxy URL: {e}")
        return None

# Telegram API settings
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')

# Admin IDs
_admin_id_str = os.environ.get('ADMIN_ID', '')
ADMIN_IDS = []
if _admin_id_str:
    try:
        ADMIN_IDS = [int(x.strip()) for x in _admin_id_str.split(',') if x.strip()]
    except ValueError:
        logger.error('ADMIN_ID format error, should be integer or comma-separated integers')

# Download settings
UPLOAD_FILE_SET = parse_bool_env('UPLOAD_FLAG')
DRIVE_NAME = os.environ.get('DRIVE_NAME', '')
DRIVE_PATH = os.environ.get('DRIVE_PATH', '')
OPERATE = os.environ.get('OPERATE', 'move')
MAX_NUM = int(os.environ.get('MAX_NUM', 10))
FILTER_LIST_STR = os.environ.get('FILTER_LIST', '')
WHITELIST_STR = os.environ.get('WHITE_LIST', '')
WHITELIST_FILE = os.environ.get('WHITELIST_FILE', 'whitelist.txt')
DOWNLOAD_ALL_ENV_SET = parse_bool_env('DOWNLOAD_ALL')
FILTER_FILE_TYPE_STR = os.environ.get('FILTER_FILE_TYPE', '')
SAVE_PATH = 'downloads'

# Timeout and health check settings
DOWNLOAD_TIMEOUT = int(os.environ.get('DOWNLOAD_TIMEOUT', 1800))
HEALTH_CHECK_INTERVAL = int(os.environ.get('HEALTH_CHECK_INTERVAL', 300))
MAX_IDLE_TIME = int(os.environ.get('MAX_IDLE_TIME', 600))
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 3))

# Progress tracking settings
PROGRESS_DIR = os.environ.get('PROGRESS_DIR', 'progress')
PROGRESS_REPORT_INTERVAL = int(os.environ.get('PROGRESS_REPORT_INTERVAL', 600))
AUTO_RESUME = parse_bool_env('AUTO_RESUME')
REPORT_PERCENT_STEP = int(os.environ.get('REPORT_PERCENT_STEP', 1))
REPORT_MIN_INTERVAL = int(os.environ.get('REPORT_MIN_INTERVAL', 180))

# Scanning throttle settings
SCAN_BATCH_SIZE = int(os.environ.get('SCAN_BATCH_SIZE', 100))
DOWNLOAD_BATCH_SIZE = int(os.environ.get('DOWNLOAD_BATCH_SIZE', 50))

# Proxy
PROXY = get_proxy_from_env()

# Logging
LOG_LEVEL_STR = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

def setup_logging():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=LOG_LEVEL,
        force=True
    )
    logger = logging.getLogger('tg_downloader')
    logger.setLevel(LOG_LEVEL)
    
    telethon_logger = logging.getLogger('telethon')
    if LOG_LEVEL == logging.DEBUG:
        telethon_logger.setLevel(logging.INFO)
    else:
        telethon_logger.setLevel(logging.WARNING)
    
    return logger

logger = setup_logging()
