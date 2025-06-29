#!/bin/bash

SERVICE_NAME="AutoBuildMCP.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
SOURCE_PATH="./$SERVICE_NAME"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}Installing systemd service: $SERVICE_NAME${NC}"

# Check if the service file exists
if [[ ! -f "$SOURCE_PATH" ]]; then
    echo -e "${RED}Error: Service file '$SOURCE_PATH' not found.${NC}"
    exit 1
fi

# Get current user and working directory
CURRENT_USER=$(whoami)
WORKING_DIRECTORY=$(pwd)
TEMP_SERVICE_FILE="/tmp/$SERVICE_NAME"

# Replace placeholders in the service file
echo -e "${GREEN}Configuring service file...${NC}"
sed -e "s|__USER__|$CURRENT_USER|g" -e "s|__WORKING_DIRECTORY__|$WORKING_DIRECTORY|g" "$SOURCE_PATH" > "$TEMP_SERVICE_FILE"

# Copy the service file
echo -e "${GREEN}Copying service file to $SERVICE_PATH...${NC}"
sudo cp "$TEMP_SERVICE_FILE" "$SERVICE_PATH"
rm "$TEMP_SERVICE_FILE"

# Reload systemd daemon
echo -e "${GREEN}Reloading systemd daemon...${NC}"
sudo systemctl daemon-reload

# Enable the service to start on boot
echo -e "${GREEN}Enabling service...${NC}"
sudo systemctl enable "$SERVICE_NAME"

# Optionally restart if already running
if [[ "$1" == "--restart" ]]; then
    echo -e "${GREEN}Restarting service...${NC}"
    sudo systemctl restart "$SERVICE_NAME"
else
    echo -e "${GREEN}Starting service...${NC}"
    sudo systemctl start "$SERVICE_NAME"
fi

# Show service status
echo -e "${CYAN}Service status:${NC}"
sudo systemctl status "$SERVICE_NAME" --no-pager

echo -e "${GREEN}Done.${NC}"
