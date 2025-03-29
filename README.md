# ♚ Quick DL Bot ♚

<div align="center">
  <img src="https://raw.githubusercontent.com/RKgroupkg/RKGROUP/refs/heads/main/Assets/Logo/IMG_20250324_003813_410.jpg" width="200" alt="Quick DL Bot Logo">
  
  ### Advanced Multimedia Download Solution for Telegram
  
  [![Telegram Bot](https://img.shields.io/badge/Try%20it%20now-@Quick__dlbot-blue?style=for-the-badge&logo=telegram)](https://t.me/Quick_dlbot)
  [![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](https://github.com/RKgroupkg/Pyrogram-Bot/blob/main/LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.8%2B-yellow?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
</div>

---

## 📋 Table of Contents
- [Project Overview](#-project-overview)
- [Key Technical Capabilities](#-key-technical-capabilities)
- [Advanced Technical Architecture](#-advanced-technical-architecture)
- [Comprehensive Command Set](#-comprehensive-command-set)
- [Performance Optimizations](#-performance-optimizations)
- [Deployment Guide](#-deployment-guide)
- [Contributing](#-contributing)
- [License](#-license)
- [Contact & Support](#-contact--support)

---

## 🌟 Project Overview

Quick DL Bot is an enterprise-grade Telegram bot designed to deliver unparalleled multimedia downloading capabilities across multiple platforms. Built on a robust architecture with advanced engineering principles, this solution offers sophisticated content retrieval with exceptional reliability and performance.

This bot represents the pinnacle of media downloading technology, combining high-performance algorithms with elegant user experience design to create a seamless, powerful tool for multimedia content acquisition.

---

## 🔥 Key Technical Capabilities

### ✅ Universal Content Support
- **Cross-Platform Content Retrieval**
  - YouTube (videos, shorts, playlists, channels, music)
  - Spotify (tracks, albums, playlists, podcasts)
  - Instagram (reels, stories, posts, highlights)
  - **Extended Platform Coverage**: 2000+ websites supported via yt-dlp integration

### ✅ Media Processing Excellence
- **Format Mastery**
  - **Audio**: FLAC (lossless), MP3 (variable bitrate options), WAV, AAC
  - **Video**: MP4, WebM, MKV with resolution options (144p to 8K)
  - **Image**: JPEG, PNG, WebP with metadata preservation

### ✅ Intelligent Queuing System
- **Advanced Request Management**
  - Multi-user request prioritization
  - Dynamic queue management with fair scheduling
  - User-specific download limits and quotas

### ✅ Resource Optimization
- **System Efficiency**
  - Automatic cache management and garbage collection

### ✅  Cookies for youtube
- **Rotator**
  - Automatic rotate cookies to not over ban a yt account.
- **Update**
  - You can update cookie while bot is running.
      - sudo only cmd `/cookie <BastBinUrl> `
         (Note encode the cookie file using bas64) 
---

## 🛠️ Advanced Technical Architecture

### 🔹 Core Infrastructure Components

#### Cookie & API Management System
- **Cookie Rotator**
  - Intelligent cookie repository with dynamic rotation
  - Time-based and request-based cookie invalidation

#### Content Acquisition Pipeline
- **Media Processing Engine**
  - Multi-threaded download acceleration
  - Chunk-based transfer with integrity verification
  - Stream multiplexing for simultaneous segment acquisition
  - Format conversion with quality preservation

#### Performance & Reliability Features
- **Error Recovery Framework**
  - Comprehensive exception handling with categorization
  - Automatic retry mechanisms with exponential backoff
  - Detailed logging with contextual information
  - User-friendly error messaging with resolution suggestions

- **Network Optimization Layer**
  - Connection pooling for resource efficiency
  - Keep-alive management for reduced latency
      [Uses Keep-alive-ping](https://github.com/RKgroupkg/KeepAlive) for hosting compadiblity with render,koyeb etc
### 🔹 Technical Stack Specifications

#### Core Technologies
- **Primary Framework**: Pyrogram Smart Plugin System
- **Download Engine**: yt-dlp with custom extensions
- **Media Processing**: FFmpeg integration for transcoding
- **Database**: MongoDb

#### System Requirements
- **Python Version**: 3.8+
- **Memory**: 512MB minimum (2GB recommended)
- **Storage**: 1GB for base installation (elastic storage for downloads)
- **Network**: 10Mbps minimum for optimal performance

#### Monitoring & Analytics
- **Performance Metrics**
  - Real-time throughput measurement
  - Resource utilization tracking
  - Request success rate monitoring
  - Response time analysis
  - Error rate visualization

---

## 📟 Comprehensive Command Set

### 📥 Content Acquisition Commands

#### YouTube Downloads
```
/yt [URL]
```
- **Format Options**: mp4, webm, mp3, flac
- **Quality Options**: best, 1080p, 720p, 480p, 360p, audio
- **Examples**:
  - `/yt https://youtube.com/watch?v=dQw4w9WgXcQ`
  - `/yt https://youtube.com/playlist?list=PLH0Szn1yYNeef2AIszbltRK15dgoxA_57`

#### Spotify Downloads
```
/spotify [URL]
```
- **Format Options**: mp3, flac
- **Quality Options**: high, medium, low
- **Examples**:
  - `/spotify https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT`
  - `/spotify https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M`

#### Instagram Downloads
```
/insta [URL]
```
- **Examples**:
  - `/insta https://www.instagram.com/p/CgJHrhXLWQY/`
  - `/insta https://www.instagram.com/stories/username/1234567890/`

#### Universal Download
```
/dl [URL] [optional:format]
```
- **Description**: Intelligent format detection for any supported site
- **Examples**:
  - `/dl https://vimeo.com/1234567`
  - `/dl https://soundcloud.com/artist/track mp3`

### 🔧 Utility Commands

#### Bot Information
- `/start` - Initialize bot and display welcome message
- `/help` - Display comprehensive command documentation
- `/about` - Show version information and technical details
- `/stats` - View your download history and usage statistics

#### System Status
- `/ping` - Measure response time and API availability
- `/status` - View current server load and queue metrics
- `/alive` - Verify bot operational status
- `/speedtest` - Evaluate server network performance

### ⚙️ Administrative Commands

#### System Management
- `/serverstats` - View detailed server performance metrics
- `/dbstats` - Analyze database performance and integrity
- `/log [lines]` - Retrieve recent diagnostic logs
- `/clear_queue` - Reset download queue (admin only)

#### Development Operations
- `/update` - Synchronize with repository (admin only)
- `/restart` - Perform controlled restart (admin only)
- `/shell [command]` - Execute shell command (admin only)
- `/py [code]` - Execute Python code snippet (admin only)
- `/broadcast [message]` - Send announcement to all users (admin only)

---

## ⚡ Performance Optimizations

### 🔹 Advanced Queuing Architecture
- **Workload Distribution**
  - Priority-based job scheduling with user
  - Job batching for efficiency with similar request types

### 🔹 Memory Management
- **Optimized Resource Utilization**
  - Scheduled garbage collection with minimal impact
  - Memory pooling for frequent operations
  - Reference management to prevent memory leaks

### 🔹 Caching Strategies
- **Multi-level Caching Implementation**
  - Content metadata caching with TTL
  - Frequently requested media caching
  - API response caching with invalidation rules
  - DNS record caching for reduced lookup latency

### 🔹 Network Optimization
- **Bandwidth Efficiency**
  - Parallel downloads with throttling
  - Header optimization to reduce overhead

---

## 🚀 Deployment Guide

### Step 1: Environment Preparation
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required system dependencies
sudo apt install -y git
# Create project directory
mkdir -p ~/quick-dl-bot
cd ~/quick-dl-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Project Installation
```bash
# Clone repository
git clone https://github.com/RKgroupkg/quick-dl-bot.git .

```

### Step 3: Configuration
```bash
# Create configuration from template
cp config.example.env config.env

# Edit configuration file with your credentials
 nano config.env

# API_ID=    get from my.telegram.org                     
# API_HASH=  get from my.telegram.org           

# MONGO_URI= 
# BOT_TOKEN=
# RAPID_API_KEYS= 

# #SUDO USERID IS OPTIONAL  
# OWNER_USERID = []
# SUDO_USERID  = []

# YT Config (optional)
#COOKIE_ROTATION_COOLDOWN=       # seconds between using the same cookie file (default: 600) sec
#DEFAULT_COOKIES_DIR=            # Dir where cookies are there (optional have cookie or not) (default: '/cookies')
#YT_PROGRESS_UPDATE_INTERVAL=    # Interval in sec for giving progress report (default: 5)
#YT_DOWNLOAD_PATH=               # Temp folder to store yt video as chach (default: '~/tmp')
#MAX_VIDEO_LENGTH_MINUTES=       # maximum limit to video time (default: 15) sec 
 
```
   You can obtain the `RAPID_API_KEY` and `RAPID_API_HOST` by signing up for the [Instagram Looter2 API on RapidAPI](https://rapidapi.com/iq.faceok/api/instagram-looter2).

### Requiremnets installion
```bash

# recommended way:- 
bash install

# Manual way


# Install required system dependencies
sudo apt install -y python3 python3-pip python3-venv git ffmpeg

# Install Python dependencies
pip install -r requirements.txt

```
### Step 4: Launch
```bash
# Start the bot in production mode
bash start
```

### Docker Deployment (Alternative)
```bash
# Build Docker image
docker build -t quick-dl-bot .

# Run Docker container
docker run -d --name quick-dl-bot \
  --restart unless-stopped \
  -v $(pwd)/config.env:/app/config.env \
  -v $(pwd)/data:/app/data \
  quick-dl-bot
```

---

## 🤝 Contributing

We welcome contributions from the community! Here's how you can help improve Quick DL Bot:

### Contribution Guidelines
1. **Fork the repository** and create your feature branch
2. **Implement your changes** following our coding standards
3. **Add tests** for new functionality
4. **Update documentation** to reflect your changes
5. **Submit a pull request** for review

### Development Setup
```bash
# Clone your fork
git clone https://github.com/RKgroupkg/Telegram-AllDlp-Bot
cd Telegram-AllDlp-Bot

# Create development branch
git checkout -b feature/your-amazing-feature

bash install 

```

### Code Standards
- Follow PEP 8 style guidelines
- Write docstrings for all functions and classes
- Maintain test coverage for new code
- Use type hints where appropriate

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/RKgroupkg/Pyrogram-Bot/blob/main/LICENSE) file for details.

```
MIT License

Copyright (C) 2023-2025 RKgroupkg

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files...
```

---

## 📞 Contact & Support

<div align="center">
  <a href="https://t.me/rkgroup_update">
    <img src="https://img.shields.io/static/v1?label=Join&message=Telegram%20Channel&color=blueviolet&style=for-the-badge&logo=telegram&logoColor=white" alt="Rkgroup Channel" />
  </a>
  <a href="https://telegram.me/Rkgroup_helpbot">
    <img src="https://img.shields.io/static/v1?label=Join&message=Telegram%20Group&color=blueviolet&style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram Group" />
  </a>
</div>

### Get Assistance
- Join our Telegram group for community support
- Report bugs via GitHub issues
- Request features through our feature request form
- Follow our channel for updates and announcements

---

<div align="center">
  <p><b>Quick DL Bot</b> — Engineering Excellence in Media Downloads</p>
  <p>Crafted with ❤️ by <a href="https://github.com/RKgroupkg">RKgroupkg</a></p>
</div>