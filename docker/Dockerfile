# ===============================
# Base image: Ubuntu 20.04
# ===============================
FROM ubuntu:20.04

# Avoid timezone and interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive

# -------------------------------
# 1. System dependencies
# -------------------------------
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-opencv \
    build-essential \
    pkg-config \
    libopencv-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------
# 2. Python packages
# -------------------------------
RUN pip3 install --no-cache-dir \
    opencv-contrib-python \
    scipy \
    matplotlib

# -------------------------------
# 3. Default work directory
# -------------------------------
WORKDIR /app
