# telegram-downloader
Telegram channel/group file downloader with automatic upload support, progress tracking, and health monitoring.

## Key Features

- ✅ Download files from Telegram channels and groups
- ✅ Auto-download from whitelisted channels
- ✅ Progress tracking with JSON files (per channel)
- ✅ Download timeout control to prevent hanging
- ✅ Automatic retry on errors
- ✅ Health monitoring and periodic progress reports
- ✅ Upload to cloud storage (via rclone)
- ✅ Resume pending downloads on startup

[中文文档](README_CN.md) | [English](README.md)

## Build

```bash
# Build Docker image
make build
```

## Usage

### Method 1: Local Execution (Recommended for Development)

Run the bot directly on your host machine without Docker:

```bash
# Setup virtual environment and install dependencies
make venv

# Start the bot (loads configuration from .env)
make dev
```

### Method 2: Docker Execution

#### 1. Initialize Session
First-time setup to authenticate and create session files:

```bash
docker run --rm -it --name tgd \
    -v $PWD/.session:/app/.session \
    -e API_ID='your_id' \
    -e API_HASH='your_hash' \
    -e BOT_TOKEN='your_bot_token' \
    -e ADMIN_ID='your_user_id' \
    tgd
```

#### 2. Basic Run
```bash
make run
```
Or manually:
```bash
docker run -d --name tgd \
    --restart always \
    -v $PWD/.session:/app/.session \
    -v $PWD/.downloads:/app/downloads \
    --env-file .env \
    tgd
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_ID` | Telegram API ID (from my.telegram.org) | **Required** |
| `API_HASH` | Telegram API Hash | **Required** |
| `BOT_TOKEN` | Telegram Bot Token | **Required** |
| `ADMIN_ID` | Admin User ID (comma-separated for multiple) | **Required** |
| `MAX_NUM` | Max concurrent download workers | `10` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `DOWNLOAD_ALL` | Monitor all joined chats for auto-download | `false` |
| `WHITE_LIST` | Whitelist chat IDs for auto-download | (Empty) |
| `WHITELIST_FILE`| Persistent file for whitelist IDs | `whitelist.txt` |
| `FILTER_LIST` | Keyword filters for filenames (space-separated) | (Empty) |
| `FILTER_FILE_TYPE`| File extension filters (e.g., `.jpg .png`) | (Empty) |
| `DOWNLOAD_TIMEOUT`| Maximum seconds for a single file download | `1800` |
| `HEALTH_CHECK_INTERVAL`| Health check frequency (seconds) | `300` |
| `MAX_IDLE_TIME` | Idle time before health warning (seconds) | `600` |
| `MAX_RETRIES` | Max retry attempts per file | `3` |
| `AUTO_RESUME` | Resume pending downloads on startup | `false` |
| `PROGRESS_DIR` | Directory for tracking JSON files | `progress` |
| `PROGRESS_REPORT_INTERVAL`| Report frequency (seconds) | `600` |
| `REPORT_PERCENT_STEP` | Update progress every X percent | `1` |
| `REPORT_MIN_INTERVAL` | Min seconds between notifications | `180` |
| `UPLOAD_FLAG` | Enable rclone upload after download | `false` |
| `DRIVE_NAME` | Rclone remote drive name | (Empty) |
| `DRIVE_PATH` | Remote path on drive | (Empty) |
| `OPERATE` | Rclone operation (`move` or `copy`) | `move` |

## Bot Commands

Admin users can interact with the bot using the following commands:

- `/start` - Show help message and command list.
- `/download <link> [start] [end]` (or `/dl`) - Manually start downloading from a channel.
  - `start`: Start message ID.
  - `end`: End message ID.
- `/stats` (or `/s`) - Show current download statistics and active tasks.
- `/resume [channel_id]` (or `/r`) - Resume pending downloads from database.
- `/whitelist_add <id...>` (or `/wa`) - Add chat IDs to whitelist.
- `/whitelist_remove <id...>` (or `/wr`) - Remove chat IDs from whitelist.
- `/whitelist_list` (or `/wl`) - List all whitelisted chat IDs.
- `/whitelist_clear` (or `/wc`) - Clear the whitelist.

## File Organization

Downloaded files are organized as follows:
```
downloads/
  └── ChannelName(ChannelID)/
      └── YYYY-MM/
          └── message_id - caption - filename.ext
```

## Progress Tracking & Notifications

The bot uses JSON files in the `.session/progress/` directory to track per-channel status. This allows it to skip already downloaded files even after a container restart.

### Notification Logic
The bot implements a tiered notification system to balance real-time feedback and message frequency:
- **Batch Completion**: Sends a summary report immediately when all queued tasks are finished.
- **Throttling**: During active downloads, reports are sent only if `REPORT_MIN_INTERVAL` (default 180s) has passed.
- **Silent Mode**: For small batches (< 100 files), progress updates are suppressed unless the download duration exceeds the interval.
- **Batch Progress**: For large batches (>= 100 files), updates are sent when both the time interval and the `REPORT_PERCENT_STEP` are met.
