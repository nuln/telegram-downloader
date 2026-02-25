import os
import asyncio
import time
import json
import logging
import config
import state
import storage
import downloader

logger = logging.getLogger('tg_downloader')

async def watch_whitelist_file(poll_interval=5):
    """Watch whitelist file and reload on modification."""
    while True:
        try:
            if os.path.exists(config.WHITELIST_FILE):
                m = os.path.getmtime(config.WHITELIST_FILE)
                if storage.whitelist_file_mtime is None or m != storage.whitelist_file_mtime:
                    storage.load_whitelist_from_file()
                    logger.info(f'Whitelist reloaded: {storage.whitelist}')
                    if not config.DOWNLOAD_ALL_ENV_SET and storage.whitelist:
                        if state.client and not state.all_chat_listener_registered:
                            from client import all_chat_download  # Local import to avoid circular dependency
                            from telethon import events
                            state.client.add_event_handler(all_chat_download, events.NewMessage())
                            state.all_chat_listener_registered = True
                            state.download_all_chat = True
                            logger.info('Auto-download listener registered by watcher')
                    if not config.DOWNLOAD_ALL_ENV_SET and not storage.whitelist:
                        state.download_all_chat = False
            else:
                if storage.whitelist:
                    storage.whitelist = []
                    storage.whitelist_file_mtime = None
                    logger.info('Whitelist file removed; cleared whitelist')
        except Exception as e:
            logger.warning(f'Error watching whitelist file: {e}')
        await asyncio.sleep(poll_interval)

async def periodic_rescan_task():
    """Periodically re-scan channels for new messages."""
    logger.info(f'[RESCAN] Task started: threshold {config.DOWNLOAD_BATCH_SIZE}')
    while True:
        try:
            await asyncio.sleep(30)
            if not os.path.exists(config.PROGRESS_DIR): continue
            
            for filename in os.listdir(config.PROGRESS_DIR):
                if not filename.startswith('channel_') or not filename.endswith('.json'): continue
                
                try:
                    progress = storage.load_channel_progress(filename[8:-5])
                    ch_id = progress['channel_id']
                    ch_name = progress.get('channel_name', f'Channel {ch_id}')
                    last_message_id = progress.get('last_message_id', 0)
                    
                    if ch_id not in state.channel_scan_state:
                        state.channel_scan_state[ch_id] = {
                            'last_scanned_id': last_message_id,
                            'last_download_count': 0,
                            'last_scan_time': time.time()
                        }
                    
                    state_info = state.channel_scan_state[ch_id]
                    completed_since_scan = progress.get('completed_count', 0) - state_info['last_download_count']
                    
                    if completed_since_scan >= config.DOWNLOAD_BATCH_SIZE:
                        entity = await state.client.get_entity(ch_id)
                        logger.info(f'[RESCAN] Triggered for {ch_name}')
                        
                        queued, last_id, scanned = await downloader.process_channel_messages(
                            entity, ch_name, offset_id=last_message_id, limit=config.SCAN_BATCH_SIZE
                        )
                        
                        state_info['last_scanned_id'] = last_id
                        state_info['last_download_count'] = progress.get('completed_count', 0)
                        state_info['last_scan_time'] = time.time()
                except Exception as e:
                    logger.warning(f'Error rescaning {filename}: {e}')
        except Exception as e:
            logger.error(f'Periodic rescan error: {e}')

async def health_check_task():
    """Monitor download health."""
    while True:
        try:
            await asyncio.sleep(config.HEALTH_CHECK_INTERVAL)
            current_time = time.time()
            idle_time = current_time - state.last_download_activity
            
            # Stuck downloads check
            for key, info in list(state.active_downloads.items()):
                if current_time - info['start_time'] > config.DOWNLOAD_TIMEOUT:
                    logger.warning(f"Stuck download detected: {info['file_name']}")
            
            if state.active_downloads:
                logger.info(f'Health: {len(state.active_downloads)} active, idle {int(idle_time)}s')
            
            if idle_time > config.MAX_IDLE_TIME and not state.queue.empty():
                logger.warning('Deadlock detected!')
                try:
                    stats = storage.get_download_stats()
                    await state.bot.send_message(config.ADMIN_IDS[0], f'⚠️ Health Warning: Deadlock detected! Stats: {stats}')
                except: pass
            
            if current_time - state.last_progress_report >= config.PROGRESS_REPORT_INTERVAL:
                await send_progress_report()
                state.last_progress_report = current_time
        except Exception as e:
            logger.error(f'Health check error: {e}')

async def send_progress_report(force=False):
    """Send progress report based on tiered throttling rules."""
    try:
        now = time.time()
        stats = storage.get_download_stats()
        total = stats['total']
        
        # Determine current activity
        is_active = not state.queue.empty() or len(state.active_downloads) > 0
        
        # Track batch start time
        if is_active and not state.was_active_last_check:
            state.batch_start_time = now
            
        # Notification logic:
        # 1. Immediate notification when tasks JUST finished (was_active -> not active)
        finished_now = not is_active and state.was_active_last_check
        
        # Calculate current percentage more accurately
        current_percent = -1
        if total > 0:
            completed_and_failed = stats['completed'] + stats['failed']
            partial_progress = 0
            for info in state.active_downloads.values():
                if info.get('file_size', 0) > 0:
                    partial_progress += info.get('downloaded', 0) / info['file_size']
            
            # Use min(99, ...) to avoid showing 100% until it's actually recorded in storage
            current_percent = int((completed_and_failed + partial_progress) / total * 100)
            if current_percent >= 100 and is_active:
                current_percent = 99

        should_send = False
        if finished_now:
            should_send = True
        elif is_active:
            # Throttling: minimum interval check (e.g. 180s)
            time_since_last = now - state.last_notification_time
            interval_reached = time_since_last >= config.REPORT_MIN_INTERVAL
            
            if interval_reached:
                if total < 100:
                    # Silent for small batches unless they take longer than the interval
                    should_send = True
                else:
                    # For large batches, notify if there's progress
                    percent_jump = current_percent >= (state.last_reported_percent + config.REPORT_PERCENT_STEP)
                    if percent_jump or force:
                        should_send = True
        
        if not should_send:
            # Still update state but don't send message
            state.was_active_last_check = is_active
            return
            
        all_progress = []
        if os.path.exists(config.PROGRESS_DIR):
            for filename in os.listdir(config.PROGRESS_DIR):
                if filename.startswith('channel_') and filename.endswith('.json'):
                    all_progress.append(storage.load_channel_progress(filename[8:-5]))
        
        # Build report
        status_icon = "⏳" if is_active else "✅"
        percent_str = f" ({current_percent}%)" if current_percent >= 0 else ""
        report = f'{status_icon} Progress Report{percent_str}\n'
        report += f'Overall: {stats["completed"]} completed, {stats["failed"]} failed, {total} total\n'
        report += f'Queue: {state.queue.qsize()} pending\n'
        report += f'Active: {len(state.active_downloads)} downloads\n'
        
        # Show details of active downloads if any
        if state.active_downloads:
            report += '\nDownloading:\n'
            for key, info in list(state.active_downloads.items()):
                fname = info['file_name']
                size = info['file_size']
                dl = info.get('downloaded', 0)
                p = int(dl/size*100) if size > 0 else 0
                report += f"  • {fname[:30]}... {p}%\n"
        
        if all_progress and not is_active:
            batch_duration = int(now - state.batch_start_time) if state.batch_start_time > 0 else 0
            report += f'\nBatch Summary (Time: {batch_duration}s):\n'
            for prog in sorted(all_progress, key=lambda x: x.get('channel_name', '')):
                completed = prog.get('completed_count', 0)
                if completed > 0:
                    report += f"  • {prog.get('channel_name', 'ID_'+str(prog['channel_id']))[:20]}: {completed} done\n"
        
        # Send message
        await state.bot.send_message(config.ADMIN_IDS[0], report)
        
        # Update tracking state
        state.last_reported_completed_count = stats['completed']
        state.last_reported_failed_count = stats['failed']
        state.last_reported_percent = current_percent
        state.was_active_last_check = is_active
        state.last_notification_time = now
        
    except Exception as e:
        logger.error(f'Error sending report: {e}')
