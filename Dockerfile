FROM python:3.11

WORKDIR /app

COPY requirements.txt /app/

# Install OS packages needed for DB drivers
RUN apt-get update && \
	apt-get install -y build-essential libpq-dev curl --no-install-recommends && \
	rm -rf /var/lib/apt/lists/*

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
