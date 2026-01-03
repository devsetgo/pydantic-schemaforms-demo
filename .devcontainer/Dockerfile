FROM python:3.14

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create user 'mike' with home directory and add to sudoers
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        sudo \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -ms /bin/bash mike \
    && echo "mike ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER mike
WORKDIR /workspaces
