import os
import re
import json
import logging
from datetime import datetime
import config

logger = logging.getLogger('tg_downloader')

whitelist = []
whitelist_file_mtime = None

def init_progress_dir():
    """Initialize progress directory for tracking download progress"""
    if not os.path.exists(config.PROGRESS_DIR):
        os.makedirs(config.PROGRESS_DIR)
        logger.info(f'Progress directory created: {config.PROGRESS_DIR}')

def load_whitelist_from_file():
    """Load whitelist IDs from file."""
    global whitelist, whitelist_file_mtime
    try:
        if os.path.exists(config.WHITELIST_FILE):
            with open(config.WHITELIST_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content == '':
                whitelist = []
            else:
                parts = [s for s in re.split(r'[\s,;]+', content) if s]
                wl = []
                for p in parts:
                    try:
                        wl.append(int(p))
                    except Exception:
                        continue
                whitelist = wl
            try:
                whitelist_file_mtime = os.path.getmtime(config.WHITELIST_FILE)
            except Exception:
                whitelist_file_mtime = None
        else:
            whitelist = []
            whitelist_file_mtime = None
        
        if config.DOWNLOAD_ALL_ENV_SET:
            whitelist = []
            whitelist_file_mtime = None
    except Exception as e:
        logger.warning(f'Failed to load whitelist file: {e}')

def save_whitelist_to_file(ids):
    """Persist IDs to whitelist file."""
    try:
        unique_ids = sorted(set(int(i) for i in ids))
        content = ''.join(f"{i}\n" for i in unique_ids)

        try:
            with open(config.WHITELIST_FILE, 'w', encoding='utf-8') as tf:
                tf.write(content)
                tf.flush()
                try:
                    os.fsync(tf.fileno())
                except Exception:
                    pass
            return
        except Exception as e_direct:
            logger.debug(f"Direct write failed: {e_direct}; falling back to replace")

        pid = os.getpid()
        tmp_path = f"{config.WHITELIST_FILE}.tmp.{pid}"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass

        try:
            os.replace(tmp_path, config.WHITELIST_FILE)
        except OSError as e:
            if getattr(e, 'errno', None) == 16:
                with open(config.WHITELIST_FILE, 'w', encoding='utf-8') as tf:
                    tf.write(content)
            else:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
    except Exception as e:
        logger.warning(f'Failed to save whitelist file: {e}')

def get_progress_file(channel_id):
    """Get progress file path for a channel."""
    return os.path.join(config.PROGRESS_DIR, f'channel_{channel_id}.json')

def load_channel_progress(channel_id):
    """Load progress for a specific channel."""
    progress_file = get_progress_file(channel_id)
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f'Error loading progress file: {e}')
    
    return {
        'channel_id': channel_id,
        'channel_name': '',
        'last_message_id': 0,
        'downloading': {},
        'completed_count': 0,
        'failed_count': 0,
        'failed_ids': []
    }

def save_channel_progress(channel_id, progress):
    """Save progress for a specific channel."""
    progress_file = get_progress_file(channel_id)
    progress['last_update'] = datetime.now().isoformat()
    try:
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f'Error saving progress file: {e}')

def record_file_start(channel_id, channel_name, message_id):
    """Record the start of a file download with minimal info (ID only)."""
    progress = load_channel_progress(channel_id)
    progress['channel_name'] = channel_name
    
    # Handle legacy dict or new int
    current_val = progress['downloading'].get(str(message_id))
    retry_count = 0
    if isinstance(current_val, dict):
        retry_count = current_val.get('retry_count', 0)
    elif isinstance(current_val, int):
        retry_count = current_val
        
    progress['downloading'][str(message_id)] = retry_count
    save_channel_progress(channel_id, progress)

def record_file_complete(channel_id, message_id, status='completed', error_message=None):
    """Record file download completion or failure."""
    progress = load_channel_progress(channel_id)
    msg_id_str = str(message_id)
    
    if status == 'completed':
        if msg_id_str in progress['downloading']:
            del progress['downloading'][msg_id_str]
            progress['completed_count'] += 1
            # Remove from failed_ids if present (e.g. successful retry)
            if message_id in progress.get('failed_ids', []):
                progress['failed_ids'].remove(message_id)
        progress['last_message_id'] = max(progress['last_message_id'], message_id)
        save_channel_progress(channel_id, progress)
    else:
        if msg_id_str in progress['downloading']:
            # Handle legacy dict or new int
            current_val = progress['downloading'][msg_id_str]
            retry_count = 0
            if isinstance(current_val, dict):
                retry_count = current_val.get('retry_count', 0)
            elif isinstance(current_val, int):
                retry_count = current_val
            
            retry_count += 1
            progress['downloading'][msg_id_str] = retry_count
            
            if retry_count >= config.MAX_RETRIES:
                del progress['downloading'][msg_id_str]
                progress['failed_count'] += 1
                if 'failed_ids' not in progress:
                    progress['failed_ids'] = []
                if message_id not in progress['failed_ids']:
                    progress['failed_ids'].append(message_id)
        progress['last_message_id'] = max(progress['last_message_id'], message_id)
        save_channel_progress(channel_id, progress)

def get_file_status(channel_id, message_id):
    """Check if a file has been completed or is downloading."""
    progress = load_channel_progress(channel_id)
    msg_id_str = str(message_id)
    if msg_id_str in progress['downloading']:
        val = progress['downloading'][msg_id_str]
        retry = val if isinstance(val, int) else val.get('retry_count', 0)
        return ('downloading', '', retry)
    if message_id <= progress['last_message_id']:
        return ('completed', '', 0)
    return None

def get_pending_files(channel_id=None):
    """Get all pending files for retry."""
    pending = []
    if not os.path.exists(config.PROGRESS_DIR):
        return pending
    
    for filename in os.listdir(config.PROGRESS_DIR):
        if not filename.startswith('channel_') or not filename.endswith('.json'):
            continue
        filepath = os.path.join(config.PROGRESS_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                progress = json.load(f)
                if channel_id and progress['channel_id'] != channel_id:
                    continue
                for msg_id, val in progress['downloading'].items():
                    retry = val if isinstance(val, int) else val.get('retry_count', 0)
                    fname = None if isinstance(val, int) else val.get('file_name')
                    if retry < config.MAX_RETRIES:
                        pending.append((progress['channel_id'], int(msg_id), fname, retry))
        except Exception as e:
            logger.error(f'Error reading {filename}: {e}')
    
    return sorted(pending, key=lambda x: (x[0], x[1]))

def get_download_stats():
    """Get download statistics."""
    total_completed = 0
    total_failed = 0
    total_downloading = 0
    
    if not os.path.exists(config.PROGRESS_DIR):
        return {'total': 0, 'completed': 0, 'failed': 0, 'pending': 0}
    
    for filename in os.listdir(config.PROGRESS_DIR):
        if filename.startswith('channel_') and filename.endswith('.json'):
            filepath = os.path.join(config.PROGRESS_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                    total_completed += progress.get('completed_count', 0)
                    total_failed += progress.get('failed_count', 0)
                    # Sync failed_count with failed_ids length if available
                    if 'failed_ids' in progress:
                        total_failed = total_failed - progress.get('failed_count', 0) + len(progress['failed_ids'])
                    total_downloading += len(progress.get('downloading', {}))
            except Exception as e:
                logger.error(f'Error reading stats from {filename}: {e}')
    
    total = total_completed + total_failed + total_downloading
    return {'total': total, 'completed': total_completed, 'failed': total_failed, 'pending': total_downloading}
