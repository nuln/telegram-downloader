import asyncio
import sys
import logging
from telethon import TelegramClient, events
import config
import state
import storage
import client
import tasks
import downloader

logger = logging.getLogger('tg_downloader')

def check_environ():
    """Verify essential environment variables."""
    if config.API_ID == 0 or not config.API_HASH or not config.BOT_TOKEN or not config.ADMIN_IDS:
        print("Essential configuration (API_ID, API_HASH, BOT_TOKEN, ADMIN_ID) is missing!")
        sys.exit(1)
    
    # Adjust max concurrency if uploading is enabled
    if config.DRIVE_NAME and config.UPLOAD_FILE_SET:
        config.MAX_NUM = 1
    
    storage.init_progress_dir()
    
    if config.DOWNLOAD_ALL_ENV_SET:
        state.download_all_chat = True
        logger.info('DOWNLOAD_ALL is set: ignoring WHITE_LIST env and file')
    else:
        if config.WHITELIST_STR:
            # If WHITE_LIST env is provided, it takes precedence and is persisted
            import re
            ids = [int(s) for s in re.split(r'[\s,;]+', config.WHITELIST_STR) if s.isdigit() or (s.startswith('-') and s[1:].isdigit())]
            storage.whitelist = ids
            storage.save_whitelist_to_file(ids)
            state.download_all_chat = True
        else:
            storage.load_whitelist_from_file()
            if storage.whitelist:
                state.download_all_chat = True
    
    # Initialize reporter state to avoid immediate notification on startup
    stats = storage.get_download_stats()
    state.last_reported_completed_count = stats['completed']
    state.last_reported_failed_count = stats['failed']
    if stats['total'] > 0:
        state.last_reported_percent = int((stats['completed'] + stats['failed']) / stats['total'] * 100)
    else:
        state.last_reported_percent = 0

async def main():
    state.queue = asyncio.Queue()
    check_environ()
    
    # Initialize Clients
    state.client = TelegramClient('.session/telegram_downloader', config.API_ID, config.API_HASH, proxy=config.PROXY)
    state.bot = await TelegramClient('.session/telegram_downloader_bot', config.API_ID, config.API_HASH, proxy=config.PROXY).start(bot_token=config.BOT_TOKEN)
    
    await state.client.start()
    
    # Register handlers
    client.register_handlers(state.bot)
    
    if state.download_all_chat:
        state.client.add_event_handler(client.all_chat_download, events.NewMessage())
        state.all_chat_listener_registered = True
        logger.info('Auto-download listener registered')
    
    # Start workers
    for i in range(config.MAX_NUM):
        asyncio.create_task(downloader.worker(f'Worker-{i}'))
    
    # Start background tasks
    asyncio.create_task(tasks.watch_whitelist_file())
    asyncio.create_task(tasks.periodic_rescan_task())
    asyncio.create_task(tasks.health_check_task())
    
    # Auto resume if enabled
    if config.AUTO_RESUME:
        await downloader.resume_downloads(send_notification=False)
    
    logger.info("Bot is running...")
    await state.client.run_until_disconnected()

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
