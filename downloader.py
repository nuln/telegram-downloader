import os
import time
import asyncio
import logging
from telethon import errors
from telethon.tl.types import MessageMediaWebPage
import config
import state
import storage
import utils

logger = logging.getLogger('tg_downloader')

async def get_group_caption(message):
    """Retrieve caption from a media group with caching."""
    if not message.grouped_id:
        return ""
    
    # Check cache first
    if message.grouped_id in state.group_caption_cache:
        return state.group_caption_cache[message.grouped_id]
        
    group_caption = ""
    try:
        entity = await state.client.get_entity(message.to_id)
        # Search nearby messages to find the one with the caption for this grouped_id
        async for msg in state.client.iter_messages(entity=entity, reverse=True, offset_id=message.id - 9, limit=10):
            if msg.grouped_id == message.grouped_id:
                if msg.text:
                    group_caption = msg.text
                    break
        
        # Cache the result (even if empty) to avoid re-scanning
        state.group_caption_cache[message.grouped_id] = group_caption
        # Limit cache size to avoid memory issues (simple FIFO-ish cleanup)
        if len(state.group_caption_cache) > 500:
            # Clear about 10% of the cache
            keys_to_remove = list(state.group_caption_cache.keys())[:50]
            for k in keys_to_remove:
                del state.group_caption_cache[k]
                
    except Exception as e:
        logger.error(f"Error getting group caption: {e}")
    return group_caption

async def build_file_name_from_message(message, entity):
    """Extract and build file name from a Telegram message."""
    caption = await get_group_caption(message) if (message.grouped_id and message.text == "") else message.text
    
    filter_list = config.FILTER_LIST_STR.split(' ') if config.FILTER_LIST_STR else []
    
    if caption:
        for fw in filter_list:
            caption = caption.replace(fw, '')
    
    caption = "" if not caption else f'{utils.validate_title(caption)} - '[:50]
    
    file_name = ''
    if message.document:
        if type(message.media) == MessageMediaWebPage:
            return None, True
        if message.media.document.mime_type in ("image/webp", "application/x-tgsticker"):
            return None, True
        for attr in message.document.attributes:
            try:
                file_name = attr.file_name
            except:
                continue
        if file_name == '':
            file_name = f'{message.id} - {caption}.{message.media.document.mime_type.split("/")[-1]}'
        else:
            if utils.get_equal_rate(caption, file_name) > 0.6:
                caption = ""
            file_name = f'{message.id} - {caption}{file_name}'
    elif message.photo:
        file_name = f'{message.id} - {caption}{message.photo.id}.jpg'
    else:
        return None, True
    
    for filter_keyword in filter_list:
        file_name = file_name.replace(filter_keyword, "")
    
    return file_name, False

async def queue_message_for_download(message, entity, chat_title, file_name=None):
    """Queue a message for download."""
    try:
        if file_name is None:
            file_name, should_skip = await build_file_name_from_message(message, entity)
            if should_skip or not file_name:
                return False
        
        dirname = utils.validate_title(f'{chat_title}({entity.id})')
        datetime_dir_name = message.date.strftime("%Y-%m")
        file_save_path = os.path.join(config.SAVE_PATH, dirname, datetime_dir_name)
        
        if not os.path.exists(file_save_path):
            os.makedirs(file_save_path, exist_ok=True)
        
        download_path = os.path.join(file_save_path, file_name)
        
        file_size = 0
        try:
            if message.document:
                file_size = message.document.size
            elif message.photo:
                file_size = max((s.size for s in message.photo.sizes if hasattr(s, 'size')), default=0)
        except:
            pass
        
        storage.record_file_start(entity.id, chat_title, message.id)
        await state.queue.put((message, chat_title, entity, file_name))
        return True
    except Exception as e:
        logger.error(f'Error queueing message {message.id} from {chat_title}: {e}')
        return False

async def worker(name):
    """Worker loop for downloading files."""
    while True:
        queue_item = await state.queue.get()
        message, chat_title, entity, file_name = queue_item
        
        filter_file_types = config.FILTER_FILE_TYPE_STR.split(' ') if config.FILTER_FILE_TYPE_STR else []
        should_skip = any(file_name.endswith(ft) for ft in filter_file_types)
        if should_skip:
            print(f"{utils.get_local_time()} Skipping filtered file: {file_name}")
            state.queue.task_done()
            continue
        
        channel_id, message_id = entity.id, message.id
        file_status = storage.get_file_status(channel_id, message_id)
        
        if file_status:
            status, _, retry_count = file_status
            if status == 'completed':
                state.queue.task_done()
                continue
            if retry_count >= config.MAX_RETRIES:
                state.queue.task_done()
                continue
        
        dirname = utils.validate_title(f'{chat_title}({entity.id})')
        datetime_dir_name = message.date.strftime("%Y-%m")
        file_save_path = os.path.join(config.SAVE_PATH, dirname, datetime_dir_name)
        if not os.path.exists(file_save_path):
            os.makedirs(file_save_path)
        
        download_path = os.path.join(file_save_path, file_name)
        if os.path.exists(download_path):
            file_size = os.path.getsize(download_path)
            if file_status and file_status[0] == 'downloading':
                try: os.remove(download_path)
                except: pass
            else:
                storage.record_file_complete(channel_id, message_id, 'completed')
                state.queue.task_done()
                continue
        
        file_size = 0
        try:
            if message.document: file_size = message.document.size
            elif message.photo: file_size = max((s.size for s in message.photo.sizes if hasattr(s, 'size')), default=0)
        except: pass
        
        storage.record_file_start(channel_id, chat_title, message_id)
        download_key = f"{channel_id}_{message_id}"
        state.active_downloads[download_key] = {
            'file_name': file_name, 
            'start_time': time.time(), 
            'file_size': file_size,
            'downloaded': 0
        }
        
        print(f"{utils.get_local_time()} [{name}] Starting download: {chat_title} - {file_name} ({utils.bytes_to_string(file_size)})")
        
        download_success = False
        error_msg = None
        
        async def progress_callback(downloaded, total):
            state.update_active_download(download_key, downloaded)
            # Optional: trigger quick report if percent jumps significantly? 
            # For now, let the periodic task handle it or completion.
        
        try:
            await state.update_download_activity()
            await asyncio.wait_for(
                state.client.download_media(message, download_path, progress_callback=progress_callback), 
                timeout=config.DOWNLOAD_TIMEOUT
            )
            
            if os.path.exists(download_path):
                download_success = True
                print(f"{utils.get_local_time()} [{name}] Download completed: {file_name}")
                
                if config.UPLOAD_FILE_SET:
                    try:
                        proc = await asyncio.wait_for(
                            asyncio.create_subprocess_exec(
                                'rclone', config.OPERATE, download_path,
                                f"{config.DRIVE_NAME}:{config.DRIVE_PATH}/{dirname}/{datetime_dir_name}",
                                '--ignore-existing'
                            ), timeout=config.DOWNLOAD_TIMEOUT
                        )
                        await proc.wait()
                        if proc.returncode == 0:
                            print(f"{utils.get_local_time()} [{name}] Upload completed: {file_name}")
                            try: os.remove(download_path)
                            except: pass
                    except Exception as e:
                        logger.error(f'Upload error for {file_name}: {e}')
            else:
                error_msg = "File not found after download"
        except asyncio.TimeoutError:
            error_msg = "Download timeout"
            if file_status and file_status[2] < config.MAX_RETRIES - 1:
                await state.queue.put((message, chat_title, entity, file_name))
        except errors.FloodWaitError as e:
            error_msg = f"FloodWait: {e.seconds}s"
            await asyncio.sleep(min(e.seconds, 300))
            await state.queue.put((message, chat_title, entity, file_name))
        except (errors.FileReferenceExpiredError, errors.FileReferenceInvalidError):
            error_msg = "File reference expired"
            try:
                async for new_message in state.client.iter_messages(entity=entity, offset_id=message_id - 1, reverse=True, limit=1):
                    await state.queue.put((new_message, chat_title, entity, file_name))
                    break
            except: pass
        except Exception as e:
            error_msg = str(e)
        finally:
            if download_key in state.active_downloads:
                del state.active_downloads[download_key]
            if download_success:
                storage.record_file_complete(channel_id, message_id, 'completed')
            elif error_msg:
                storage.record_file_complete(channel_id, message_id, 'failed', error_msg)
            if not download_success and os.path.exists(download_path):
                try: os.remove(download_path)
                except: pass
            await state.update_download_activity()
            
            # Immediately trigger a progress report check on completion
            try:
                import tasks
                asyncio.create_task(tasks.send_progress_report(force=True))
            except: pass
            
            state.queue.task_done()

async def resume_downloads(channel_id=None, send_notification=True):
    """Resume downloads from last checkpoint."""
    if not os.path.exists(config.PROGRESS_DIR):
        return 0, 'No progress records found' if send_notification else None
    
    channels_to_resume = []
    for filename in os.listdir(config.PROGRESS_DIR):
        if not filename.startswith('channel_') or not filename.endswith('.json'): continue
        try:
            progress = storage.load_channel_progress(filename[8:-5])
            ch_id = progress['channel_id']
            if channel_id and ch_id != channel_id: continue
            
            # Cleanup of old paths is no longer possible/needed as we don't store them
             # We just rely on downloading keys to know what to resume
            
            start_msg_id = progress.get('last_message_id', 0)
            if progress.get('downloading'):
                start_msg_id = min([int(mid) for mid in progress['downloading'].keys()] + [start_msg_id])
            
            if start_msg_id > 0 or progress.get('downloading'):
                channels_to_resume.append((ch_id, start_msg_id, progress.get('channel_name', f'Channel {ch_id}')))
        except Exception as e:
            logger.error(f'Error reading progress for {filename}: {e}')
    
    if not channels_to_resume:
        return 0, 'No channels to resume' if send_notification else None
    
    total_added = 0
    for ch_id, start_msg_id, ch_name in channels_to_resume:
        try:
            entity = await state.client.get_entity(ch_id)
            chat_title = entity.title
            progress = storage.load_channel_progress(ch_id)
            downloading_ids = sorted([int(x) for x in progress.get('downloading', {}).keys()])
            
            for mid in downloading_ids:
                try:
                    message = await state.client.get_messages(entity, ids=mid)
                    if message and message.media:
                        if await queue_message_for_download(message, entity, chat_title):
                            total_added += 1
                except: pass
            
            iter_offset = max(0, start_msg_id - 1)
            async for message in state.client.iter_messages(entity, offset_id=iter_offset, reverse=True, limit=config.SCAN_BATCH_SIZE):
                if not message.media or message.id <= progress['last_message_id'] or message.id in downloading_ids:
                    continue
                if await queue_message_for_download(message, entity, chat_title):
                    total_added += 1
        except Exception as e:
            logger.error(f'Error resuming channel {ch_id}: {e}')
    
    result_msg = f'Resumed {len(channels_to_resume)} channels, added {total_added} files to queue'
    logger.info(result_msg)
    return total_added, result_msg

async def process_channel_messages(entity, chat_title, offset_id=0, end_id=None, limit=None):
    """Scan and process messages from a channel."""
    queued_count = 0
    last_id = offset_id
    scanned_count = 0
    
    try:
        async for message in state.client.iter_messages(entity, offset_id=offset_id, reverse=True, limit=limit):
            scanned_count += 1
            if end_id and message.id > end_id:
                break
                
            last_id = max(last_id, message.id)
            
            if not message.media:
                continue
                
            # Check if already completed or downloading
            status = storage.get_file_status(entity.id, message.id)
            if status and (status[0] == 'completed' or status[2] >= config.MAX_RETRIES):
                continue
                
            if await queue_message_for_download(message, entity, chat_title):
                queued_count += 1
                
    except Exception as e:
        logger.error(f"Error processing messages for {chat_title}: {e}")
        
    return queued_count, last_id, scanned_count
