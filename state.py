import asyncio
import time
import config

# Telegram clients
client = None
bot = None

# Queue for downloads
queue = None

# Health monitoring state
last_download_activity = time.time()
active_downloads = {}
last_progress_report = time.time()

# Activity tracking for notifications
last_reported_completed_count = 0
last_reported_failed_count = 0
last_reported_percent = -1
was_active_last_check = False
last_notification_time = 0
batch_start_time = 0

# Scanning state
channel_scan_state = {}  # channel_id -> state
download_all_chat = config.DOWNLOAD_ALL_ENV_SET
all_chat_listener_registered = False

# Caches
group_caption_cache = {}  # grouped_id -> caption

async def update_download_activity():
    """Update last download activity timestamp"""
    global last_download_activity
    last_download_activity = time.time()

def update_active_download(key, downloaded):
    """Update downloaded bytes for an active task."""
    if key in active_downloads:
        active_downloads[key]['downloaded'] = downloaded
