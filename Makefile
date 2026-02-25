# Makefile for telegram-downloader

IMAGE ?= tgd
NAME ?= telegram-downloader
SESSION_DIR ?= $(PWD)/.session
DOWNLOAD_DIR ?= $(PWD)/.downloads
PROGRESS_DIR ?= $(SESSION_DIR)/progress
ENV_FILE ?= .env
PYTHON ?= python3
VENV ?= venv
BIN ?= $(VENV)/bin

.PHONY: build run stop logs shell ps clean venv dev restart package

venv:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -r requirements.txt

dev: venv
	@if [ ! -f $(ENV_FILE) ]; then echo "$(ENV_FILE) not found! Please copy .env.example to $(ENV_FILE)"; exit 1; fi
	@echo "Starting bot locally..."
	env $$(grep -v '^#' $(ENV_FILE) | xargs) $(BIN)/python main.py

build:
	docker build -t $(IMAGE) .

run: stop
	@echo "Starting container $(NAME) using env file '$(ENV_FILE)'"
	@mkdir -p "$(SESSION_DIR)" "$(DOWNLOAD_DIR)"
	docker run -d --name $(NAME) \
		--restart always \
		--env-file $(ENV_FILE) \
		-v "$(SESSION_DIR):/app/.session" \
		-v "$(DOWNLOAD_DIR):/app/downloads" \
		$(IMAGE)

stop:
	-docker rm -f $(NAME) || true

restart: stop run

logs:
	docker logs -f $(NAME)

shell:
	docker exec -it $(NAME) /bin/sh

ps:
	docker ps -a | grep $(NAME) || true

clean: stop
	-docker rmi $(IMAGE) || true
	rm -rf $(VENV) .session/progress .session/telegram_downloader.session .session/telegram_downloader_bot.session dist build *.spec
	@echo "Cleaned up intermediate files, build artifacts and docker image."

package: venv
	$(BIN)/pip install pyinstaller
	$(BIN)/pyinstaller --onefile --name telegram-downloader main.py
