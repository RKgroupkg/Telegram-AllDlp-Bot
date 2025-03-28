# Copyright (c) 2025 Rkgroup.
# Quick Dl is an open-source Downloader bot licensed under MIT.
# All rights reserved where applicable.

# Use an official Python runtime as the base image.
# https://hub.docker.com/_/python


FROM python:3.13-slim

# Set the working directory in the container.
WORKDIR /app

# Copy the installation script and requirements.txt first to leverage caching.
COPY install.sh requirements.txt ./

# Make the install.sh script executable.
RUN chmod +x install.sh

# Run the install.sh script to install all dependencies.
RUN ./install.sh

# Copy the rest of the application code.
COPY . .

# Make the start.sh script executable.
RUN chmod +x start.sh

# Set the default command to run when the container starts.
CMD ["./start.sh"]