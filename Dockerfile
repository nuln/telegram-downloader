FROM python:3.10-slim

ADD . /app

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        gcc \
        g++ \
        unzip \
        python3-dev \
        build-essential \
        libffi-dev \
        libssl-dev \
        zlib1g-dev \
        libjpeg-dev \
        libpng-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    curl https://rclone.org/install.sh | bash && \
    apt-get remove -y git curl gcc g++ python3-dev build-essential && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

CMD [ "python", "-u", "/app/main.py" ]