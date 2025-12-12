#!/bin/bash
#
# Linux PC Stats Display - Auto Setup Script v1.0
# Installs FPS logger, CSV cleanup, and stats sender
# Works on Bazzite, SteamOS, and other Linux systems
#
# Usage: ./install.sh
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}"
echo "========================================================"
echo "                                                        "
echo "    Linux PC Stats Display - Auto Installer v1.0       "
echo "                                                        "
echo "========================================================"
echo -e "${NC}"
echo ""
echo "This installer will set up:"
echo "  - MangoHud FPS logger"
echo "  - Auto CSV cleanup"
echo "  - Stats sender to Raspberry Pi"
echo "  - Systemd services (auto-start on boot)"
echo ""

# Get user input with validation
while true; do
    echo -e "${YELLOW}Please enter your Raspberry Pi's IP address:${NC}"
    echo -e "${BLUE}(Example: 192.168.1.100)${NC}"
    read -p "Pi IP: " PI_IP
    
    if [ -z "$PI_IP" ]; then
        echo -e "${RED}ERROR: Error: IP address cannot be empty${NC}"
        echo ""
        continue
    fi
    
    # Basic IP validation
    if [[ $PI_IP =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        echo -e "${GREEN}OK Valid IP format${NC}"
        break
    else
        echo -e "${RED}ERROR: Error: Invalid IP format. Please use format: xxx.xxx.xxx.xxx${NC}"
        echo ""
    fi
done

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Installing with Pi IP: ${YELLOW}$PI_IP${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Test connectivity to Pi
echo -e "${BLUE}→ Testing connection to Raspberry Pi...${NC}"
if timeout 2 ping -c 1 "$PI_IP" &> /dev/null; then
    echo -e "${GREEN}OK Pi is reachable!${NC}"
else
    echo -e "${YELLOW}⚠ Warning: Cannot reach Pi at $PI_IP${NC}"
    echo -e "${YELLOW}  Installation will continue, but verify the IP is correct.${NC}"
fi
echo ""

# Create directories
echo -e "${BLUE}→ Creating directories...${NC}"
mkdir -p ~/.config/systemd/user
mkdir -p ~/linux-stats
echo -e "${GREEN}OK Directories created${NC}"
echo ""

# Create FPS Logger Script
echo -e "${BLUE}→ Creating MangoHud FPS logger...${NC}"
cat > ~/linux-stats/fps_logger.sh << 'EOF'
#!/bin/bash

FPS_FILE="/tmp/fps.txt"
WATCH_DIR="$HOME"

while true; do
    # Find the most recent CSV file with date-time pattern (MangoHud format)
    latest_csv=$(ls -t "$WATCH_DIR"/*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv 2>/dev/null | head -1)
    
    if [ -f "$latest_csv" ]; then
        # Check if file was modified in the last 3 seconds (active game)
        if [ $(($(date +%s) - $(stat -c %Y "$latest_csv"))) -lt 3 ]; then
            # Get the last line and extract FPS (first column)
            fps=$(tail -1 "$latest_csv" | grep -v "^fps" | cut -d',' -f1)
            
            # Check if it's a valid number
            if [[ "$fps" =~ ^[0-9]+\.?[0-9]*$ ]]; then
                fps_int=$(printf "%.0f" "$fps" 2>/dev/null || echo "0")
                echo "$fps_int" > "$FPS_FILE"
            else
                echo "0" > "$FPS_FILE"
            fi
        else
            echo "0" > "$FPS_FILE"
        fi
    else
        echo "0" > "$FPS_FILE"
    fi
    
    sleep 0.5
done
EOF

chmod +x ~/linux-stats/fps_logger.sh
echo -e "${GREEN}OK FPS logger created${NC}"
echo ""

# Create CSV Cleanup Script
echo -e "${BLUE}→ Creating CSV cleanup script...${NC}"
cat > ~/linux-stats/cleanup_fps_logs.sh << 'EOF'
#!/bin/bash

WATCH_DIR="$HOME"
CLEANUP_DELAY=30  # Seconds after logging stops before cleanup

while true; do
    # Find all CSV files with date-time pattern in home directory
    for csv_file in "$WATCH_DIR"/*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv; do
        if [ -f "$csv_file" ]; then
            # Check how old the file is (last modified time)
            file_age=$(($(date +%s) - $(stat -c %Y "$csv_file")))
            
            # If file hasn't been modified in CLEANUP_DELAY seconds, delete it
            if [ $file_age -gt $CLEANUP_DELAY ]; then
                rm -f "$csv_file"
            fi
        fi
    done
    
    sleep 10
done
EOF

chmod +x ~/linux-stats/cleanup_fps_logs.sh
echo -e "${GREEN}OK CSV cleanup script created${NC}"
echo ""

# Copy Stats Sender Script
echo -e "${BLUE}→ Setting up stats sender...${NC}"

# Look for stat_sender in current directory or home
SENDER_FOUND=false
for location in "$(pwd)/stat_sender_v1.py" "$(pwd)/stats_sender_v1.py" "$HOME/stat_sender_v1.py" "$(pwd)/bazzite_stats_sender_v10.py"; do
    if [ -f "$location" ]; then
        cp "$location" ~/linux-stats/stat_sender.py
        SENDER_FOUND=true
        echo -e "${GREEN}OK Found stat_sender at: $location${NC}"
        break
    fi
done

if [ "$SENDER_FOUND" = false ]; then
    echo -e "${RED}ERROR: Error: stat_sender_v1.py not found${NC}"
    echo -e "${YELLOW}  Please ensure stat_sender_v1.py is in the same directory as this installer${NC}"
    exit 1
fi

# Update PI_IP in the sender script
if [ -f ~/linux-stats/stat_sender.py ]; then
    sed -i "s/PI_IP = .*/PI_IP = \"$PI_IP\"/" ~/linux-stats/stat_sender.py
    echo -e "${GREEN}OK Stats sender configured with Pi IP: $PI_IP${NC}"
fi
echo ""

# Create systemd services
echo -e "${BLUE}→ Creating systemd services...${NC}"

# FPS Logger service
cat > ~/.config/systemd/user/fps-logger.service << EOF
[Unit]
Description=MangoHud FPS Logger for Stats Display
After=graphical.target

[Service]
Type=simple
ExecStart=$HOME/linux-stats/fps_logger.sh
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

# CSV Cleanup service
cat > ~/.config/systemd/user/fps-cleanup.service << EOF
[Unit]
Description=FPS CSV Cleanup Service
After=graphical.target

[Service]
Type=simple
ExecStart=$HOME/linux-stats/cleanup_fps_logs.sh
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

# Stats Sender service
cat > ~/.config/systemd/user/stats-sender.service << EOF
[Unit]
Description=Linux PC Stats Sender to Pi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $HOME/linux-stats/stat_sender.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

echo -e "${GREEN}OK Systemd services created${NC}"
echo ""

# Reload and enable services
echo -e "${BLUE}→ Enabling and starting services...${NC}"

# Check if we have a proper session bus
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    echo -e "${YELLOW}⚠ No D-Bus session detected, using loginctl to enable services${NC}"
    # Enable lingering so services start on boot
    loginctl enable-linger $USER 2>/dev/null || true
    
    # Reload daemon
    systemctl --user daemon-reload 2>/dev/null || echo -e "${YELLOW}⚠ Could not reload daemon (this is OK)${NC}"
    
    # Create a script to enable services on next login
    cat > ~/linux-stats/enable-services.sh << 'ENABLE_EOF'
#!/bin/bash
systemctl --user daemon-reload
systemctl --user enable fps-logger.service fps-cleanup.service stats-sender.service
systemctl --user start fps-logger.service fps-cleanup.service stats-sender.service
echo "OK Services enabled and started"
ENABLE_EOF
    chmod +x ~/linux-stats/enable-services.sh
    
    echo -e "${GREEN}OK Service files created${NC}"
    echo -e "${YELLOW}⚠ Services will auto-start on next login/reboot${NC}"
    echo -e "${YELLOW}⚠ To start now, run: ~/linux-stats/enable-services.sh${NC}"
else
    # Normal flow with D-Bus session
    systemctl --user daemon-reload
    
    systemctl --user enable fps-logger.service
    systemctl --user enable fps-cleanup.service
    systemctl --user enable stats-sender.service
    
    systemctl --user start fps-logger.service
    systemctl --user start fps-cleanup.service
    systemctl --user start stats-sender.service
    
    echo -e "${GREEN}OK All services enabled and started${NC}"
fi
echo ""

# Create uninstall script
echo -e "${BLUE}→ Creating uninstall script...${NC}"
cat > ~/linux-stats/uninstall.sh << 'EOF'
#!/bin/bash

echo "Uninstalling Linux PC Stats Display..."

# Stop and disable services
systemctl --user stop fps-logger.service fps-cleanup.service stats-sender.service
systemctl --user disable fps-logger.service fps-cleanup.service stats-sender.service

# Remove service files
rm -f ~/.config/systemd/user/fps-logger.service
rm -f ~/.config/systemd/user/fps-cleanup.service
rm -f ~/.config/systemd/user/stats-sender.service

systemctl --user daemon-reload

# Remove scripts directory
rm -rf ~/linux-stats

# Clean up any remaining CSV files
rm -f ~/*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv

# Remove FPS file
rm -f /tmp/fps.txt

echo "OK Uninstall complete!"
EOF

chmod +x ~/linux-stats/uninstall.sh
echo -e "${GREEN}OK Uninstall script created${NC}"
echo ""

# Create README
cat > ~/linux-stats/README.txt << EOF
===========================================
Linux PC Stats Display - Installation Info
===========================================

Installation Date: $(date)
Raspberry Pi IP: $PI_IP

INSTALLED SERVICES:
-------------------
OK fps-logger.service      - Monitors MangoHud CSV files for FPS
OK fps-cleanup.service     - Auto-deletes old CSV files after 30 seconds
OK stats-sender.service    - Sends system stats to Raspberry Pi display

QUICK COMMANDS:
---------------
Check service status:
  systemctl --user status stats-sender.service

View live logs:
  journalctl --user -u stats-sender.service -f

Restart services:
  systemctl --user restart stats-sender.service

Update Pi IP address:
  nano ~/linux-stats/stat_sender.py
  (Change: PI_IP = "$PI_IP")
  systemctl --user restart stats-sender.service

Uninstall everything:
  ~/linux-stats/uninstall.sh

FILES LOCATION:
---------------
All files are in: ~/linux-stats/
  - fps_logger.sh
  - cleanup_fps_logs.sh
  - stat_sender.py
  - uninstall.sh
  - README.txt

HOW IT WORKS:
-------------
1. MangoHud logs FPS to CSV files in your home directory
2. fps_logger.sh reads the CSV and writes FPS to /tmp/fps.txt
3. stat_sender.py sends FPS + system stats to your Pi every second
4. cleanup_fps_logs.sh deletes old CSV files after 30 seconds

TROUBLESHOOTING:
----------------
FPS showing 0:
  1. Launch a game and check: ls ~/*.csv
  2. Verify FPS file: cat /tmp/fps.txt
  3. Check logger: systemctl --user status fps-logger.service

Stats not on Pi:
  1. Ping Pi: ping $PI_IP
  2. Check sender: systemctl --user status stats-sender.service
  3. View logs: journalctl --user -u stats-sender.service -f

===========================================
EOF

# Final success message
clear
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════╗"
echo "║                                                        ║"
echo "║          OK  Installation Complete!  OK                 ║"
echo "║                                                        ║"
echo "╚════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${GREEN}OK Successfully installed:${NC}"
echo "  • MangoHud FPS Logger"
echo "  • CSV Cleanup Service"
echo "  • Stats Sender (→ $PI_IP)"
echo ""
echo -e "${BLUE}📁 Files location:${NC} ~/linux-stats/"
echo ""

# Check if services need manual start
if [ -f ~/linux-stats/enable-services.sh ]; then
    echo -e "${YELLOW}⚠️  Services created but not started yet${NC}"
    echo -e "${YELLOW}   Run this to start them now:${NC}"
    echo "   ~/linux-stats/enable-services.sh"
    echo ""
    echo -e "${YELLOW}   Or they will auto-start on next login/reboot${NC}"
    echo ""
fi

echo -e "${YELLOW}🔍 Verify services are running:${NC}"
echo "  systemctl --user status stats-sender.service"
echo ""
echo -e "${YELLOW}📊 Check if FPS is detected:${NC}"
echo "  cat /tmp/fps.txt"
echo ""
echo -e "${YELLOW}📖 Read documentation:${NC}"
echo "  cat ~/linux-stats/README.txt"
echo ""
echo -e "${YELLOW}🗑️  To uninstall:${NC}"
echo "  ~/linux-stats/uninstall.sh"
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Next Steps:${NC}"
echo "  1. Launch any game to test FPS detection"
echo "  2. Make sure your Raspberry Pi display server is running"
echo "  3. Open http://$PI_IP:5000 in a browser"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}Happy gaming! 🎮${NC}"
echo ""
