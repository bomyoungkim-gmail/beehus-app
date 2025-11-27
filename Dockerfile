FROM python:3.11

WORKDIR /app

COPY requirements.txt /app/

# Install OS packages needed for DB drivers and Chrome
RUN apt-get update && \
	apt-get install -y wget build-essential libpq-dev curl gnupg2 ca-certificates --no-install-recommends && \
	rm -rf /var/lib/apt/lists/*

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Install Chrome
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
	apt-get update && apt-get install -y ./google-chrome-stable_current_amd64.deb --no-install-recommends && \
	rm -rf /var/lib/apt/lists/* && rm google-chrome-stable_current_amd64.deb

COPY . /app/
