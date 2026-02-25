# telegram-downloader
Telegram 频道/群组文件下载器，支持自动上传（rclone）、进度追踪和健康监控。

## 主要功能

- ✅ 从 Telegram 频道和群组下载文件
- ✅ 白名单频道自动下载新消息
- ✅ 基于 JSON 的进度追踪（逐频道记录）
- ✅ 下载超时控制，防止任务卡死
- ✅ 错误后自动重试
- ✅ 健康监控及定期进度报告
- ✅ 支持通过 rclone 上传到云端
- ✅ 启动时自动恢复未完成的任务

[English](README.md) | [中文文档](README_CN.md)

## 构建

```bash
# 构建 Docker 镜像
make build
```

## 使用方法

### 方法 1：本地启动 (推荐用于开发)

无需 Docker，直接在宿主机运行：

```bash
# 创建虚拟环境并安装依赖
make venv

# 启动机器人 (自动加载 .env 配置)
make dev
```

### 方法 2：Docker 启动

#### 1. 初始化会话
首次运行需进行身份验证并创建会话文件：

```bash
docker run --rm -it --name tgd \
    -v $PWD/.session:/app/.session \
    -e API_ID='你的ID' \
    -e API_HASH='你的HASH' \
    -e BOT_TOKEN='机器人Token' \
    -e ADMIN_ID='你的用户ID' \
    tgd
```

#### 2. 常规运行
```bash
make run
```
或手动运行：
```bash
docker run -d --name tgd \
    --restart always \
    -v $PWD/.session:/app/.session \
    -v $PWD/.downloads:/app/downloads \
    --env-file .env \
    tgd
```

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `API_ID` | Telegram API ID (my.telegram.org 获取) | **必填** |
| `API_HASH` | Telegram API Hash | **必填** |
| `BOT_TOKEN` | Telegram 机器人 Token | **必填** |
| `ADMIN_ID` | 管理员用户 ID (多个 ID 用逗号分隔) | **必填** |
| `MAX_NUM` | 最大并发下载工作线程数 | `10` |
| `LOG_LEVEL` | 日志级别 (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `DOWNLOAD_ALL` | 是否监听所有已加入的频道进行自动下载 | `false` |
| `WHITE_LIST` | 自动下载的白名单频道 ID | (空) |
| `WHITELIST_FILE`| 白名单持久化文件路径 | `whitelist.txt` |
| `FILTER_LIST` | 文件名关键词过滤 (空格分隔) | (空) |
| `FILTER_FILE_TYPE`| 文件后缀过滤 (如 `.jpg .png`) | (空) |
| `DOWNLOAD_TIMEOUT`| 单个文件下载最大超时时间 (秒) | `1800` |
| `HEALTH_CHECK_INTERVAL`| 健康检查频率 (秒) | `300` |
| `MAX_IDLE_TIME` | 空闲告警前的最大静默时间 (秒) | `600` |
| `MAX_RETRIES` | 单个文件最大重试次数 | `3` |
| `AUTO_RESUME` | 启动时自动恢复待下载任务 | `false` |
| `PROGRESS_DIR` | 进度追踪 JSON 文件存放目录 | `progress` |
| `PROGRESS_REPORT_INTERVAL`| 进度报告发送频率 (秒) | `600` |
| `REPORT_PERCENT_STEP` | 每完成 X% 进度时更新 | `1` |
| `REPORT_MIN_INTERVAL` | 两次通知间的最小间隔 (秒) | `180` |
| `UPLOAD_FLAG` | 下载完成后是否启用 rclone 上传 | `false` |
| `DRIVE_NAME` | rclone 远程驱动器名称 | (空) |
| `DRIVE_PATH` | 云端存储路径 | (空) |
| `OPERATE` | rclone 操作类型 (`move` 或 `copy`) | `move` |

## 机器人命令

管理员可以向机器人发送以下命令：

- `/start` - 显示帮助信息和命令列表。
- `/download <链接> [起始ID] [结束ID]` (或 `/dl`) - 手动触发频道下载。
  - `起始ID`: 消息起始 ID。
  - `结束ID`: 消息截止 ID。
- `/stats` (或 `/s`) - 查看当前下载统计和活跃任务。
- `/resume [频道ID]` (or `/r`) - 从数据库恢复挂起的下载任务。
- `/whitelist_add <ID...>` (或 `/wa`) - 添加频道 ID 到白名单。
- `/whitelist_remove <ID...>` (or `/wr`) - 从白名单移除频道 ID。
- `/whitelist_list` (或 `/wl`) - 列出所有白名单 ID。
- `/whitelist_clear` (或 `/wc`) - 清空白名单。

## 文件组织结构

下载的文件按以下规则存放：
```
downloads/
  └── 频道名(频道ID)/
      └── 年-月/
          └── 消息ID - 标题 - 原始文件名.后缀
```

## 进度追踪与通知

机器人在 `.session/progress/` 目录下为每个频道维护一个 JSON 文件。这使得它即使在容器重启后也能识别并跳过已下载的文件。

### 通知逻辑
机器人采用分层通知机制，以平衡实时反馈与消息频率：
- **批次完成**：所有排队任务完成时，**立即**发送总结报告。
- **发送限流**：下载进行中时，仅在满足 `REPORT_MIN_INTERVAL`（默认 180s）间隔时才发送进度更新。
- **少于 100 个文件**：下载期间默认静默，除非下载总时长超过了设定的限流间隔（此时每 180s 报一次进度）。
- **多于 100 个文件**：同时满足时间间隔和 `REPORT_PERCENT_STEP` 进度跳变时发送更新。
