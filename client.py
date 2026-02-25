import re
import logging
from telethon import TelegramClient, events
import config
import state
import storage
import utils
import downloader

logger = logging.getLogger('tg_downloader')

async def all_chat_download(update):
    """Event handler for new messages in all chats."""
    message = update.message
    chat_id = message.chat_id or message.to_id
    
    try:
        entity = await state.client.get_entity(chat_id)
    except Exception as e:
        logger.error(f"Failed to get entity for chat_id {chat_id}: {e}")
        return
    
    entity_id = entity.id
    chat_title = getattr(entity, 'title', str(entity_id))
    
    if storage.whitelist:
        variants = [entity_id, -entity_id]
        if entity_id > 0: variants.append(int(f"-100{entity_id}"))
        id_str = str(entity_id)
        if id_str.startswith("-100") and len(id_str) > 4:
            actual_id = int(id_str[4:])
            variants.extend([actual_id, -actual_id])
        
        if not any(v in storage.whitelist for v in set(variants)):
            return
    
    if not message.media: return
    
    logger.info(f"Auto-downloading media from: {chat_title}")
    await downloader.queue_message_for_download(message, entity, chat_title)

async def start_handler(update):
    """Help command handler."""
    help_msg = (
        'Bot command reference:\n\n'
        '/download <link> [<start>] [<end>] or /dl - Start downloads.\n'
        '/stats or /s - Show statistics.\n'
        '/resume [<channel_id>] or /r - Resume downloads.\n\n'
        '/whitelist_add <id...> or /wa - Add to whitelist.\n'
        '/whitelist_list or /wl - List whitelist.\n'
        '/whitelist_remove <id...> or /wr - Remove from whitelist.\n'
        '/whitelist_clear or /wc - Clear whitelist.\n'
    )
    await state.bot.send_message(config.ADMIN_IDS[0], help_msg)

async def stats_handler(update):
    """Show live and database statistics."""
    stats = storage.get_download_stats()
    msg = f"📊 Stats:\nDB: {stats['completed']} done, {stats['failed']} failed, {stats['pending']} pending\nQueue: {state.queue.qsize()}\nActive: {len(state.active_downloads)}"
    await update.reply(msg)

async def resume_handler(update):
    """Handle /resume command."""
    text = update.message.text.split()
    channel_id = int(text[1]) if len(text) > 1 and text[1].isdigit() else None
    _, msg = await downloader.resume_downloads(channel_id)
    await update.reply(msg)

async def whitelist_add_handler(update):
    """Add IDs to whitelist."""
    text = update.message.text or ''
    parts = text.split()[1:]
    added = []
    for p in parts:
        nums = re.findall(r'-?\d+', p)
        if nums:
            nid = int(nums[0])
            if nid not in storage.whitelist:
                storage.whitelist.append(nid)
                added.append(nid)
    if added:
        storage.save_whitelist_to_file(storage.whitelist)
        if not config.DOWNLOAD_ALL_ENV_SET and not state.download_all_chat:
            state.download_all_chat = True
            if state.client and not state.all_chat_listener_registered:
                state.client.add_event_handler(all_chat_download, events.NewMessage())
                state.all_chat_listener_registered = True
        await update.reply(f'Added: {added}')
    else:
        await update.reply('No new IDs added')

async def whitelist_remove_handler(update):
    """Remove IDs from whitelist."""
    text = update.message.text or ''
    parts = text.split()[1:]
    removed = []
    for p in parts:
        nums = re.findall(r'-?\d+', p)
        if nums:
            nid = int(nums[0])
            if nid in storage.whitelist:
                storage.whitelist.remove(nid)
                removed.append(nid)
    if removed:
        storage.save_whitelist_to_file(storage.whitelist)
        if not config.DOWNLOAD_ALL_ENV_SET and not storage.whitelist:
            state.download_all_chat = False
        await update.reply(f'Removed: {removed}')

async def whitelist_clear_handler(update):
    """Clear whitelist."""
    storage.whitelist = []
    storage.save_whitelist_to_file([])
    await update.reply('Whitelist cleared')

async def whitelist_list_handler(update):
    """List whitelist entries."""
    await update.reply(f'Whitelist: {storage.whitelist}')

async def download_handler(update):
    """Handle /download command."""
    text = update.message.text.split()
    if len(text) < 2:
        await update.reply('Usage: /download <link> [<start>] [<end>]')
        return
    
    link = text[1]
    start_id = int(text[2]) if len(text) > 2 else 0
    end_id = int(text[3]) if len(text) > 3 else None
    
    try:
        entity = await state.client.get_entity(link)
        await update.reply(f"Scanning {entity.title}...")
        queued, _, _ = await downloader.process_channel_messages(entity, entity.title, offset_id=start_id, end_id=end_id)
        await update.reply(f"Queued {queued} messages.")
    except Exception as e:
        await update.reply(f"Error: {e}")

def register_handlers(bot_instance):
    """Register all command handlers."""
    admin_ids = config.ADMIN_IDS
    bot_instance.add_event_handler(start_handler, events.NewMessage(pattern='/start', from_users=admin_ids))
    bot_instance.add_event_handler(stats_handler, events.NewMessage(pattern=r'/(stats|s)', from_users=admin_ids))
    bot_instance.add_event_handler(resume_handler, events.NewMessage(pattern=r'/(resume|r)', from_users=admin_ids))
    bot_instance.add_event_handler(whitelist_add_handler, events.NewMessage(pattern=r'/(whitelist_add|wa)', from_users=admin_ids))
    bot_instance.add_event_handler(whitelist_remove_handler, events.NewMessage(pattern=r'/(whitelist_remove|wr)', from_users=admin_ids))
    bot_instance.add_event_handler(whitelist_clear_handler, events.NewMessage(pattern=r'/(whitelist_clear|wc)', from_users=admin_ids))
    bot_instance.add_event_handler(whitelist_list_handler, events.NewMessage(pattern=r'/(whitelist_list|wl)', from_users=admin_ids))
    bot_instance.add_event_handler(download_handler, events.NewMessage(pattern=r'/(download|dl)', from_users=admin_ids))
