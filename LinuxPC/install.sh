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
    read -p "Pi IP: " PI_IP < /dev/tty
    
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

# Ask for display orientation
echo ""
echo -e "${YELLOW}Please choose your display orientation:${NC}"
echo "  1) Portrait  (vertical  - 480×1920)"
echo "  2) Landscape (horizontal - 1920×480)"
echo ""
read -p "Choose orientation (1-2, default=1): " ORIENTATION_CHOICE < /dev/tty
ORIENTATION_CHOICE=${ORIENTATION_CHOICE:-1}

if [ "$ORIENTATION_CHOICE" = "2" ]; then
    ORIENTATION="landscape"
    echo -e "${GREEN}OK Orientation set to: Landscape${NC}"
else
    ORIENTATION="portrait"
    echo -e "${GREEN}OK Orientation set to: Portrait${NC}"
fi
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

# Detect SteamOS / immutable OS
IS_STEAMOS=false
if [ -f /etc/os-release ] && grep -qi "steamos\|holo" /etc/os-release 2>/dev/null; then
    IS_STEAMOS=true
fi

# Set up RAPL permissions for CPU power reading
echo -e "${BLUE}→ Setting up CPU power monitoring...${NC}"
RAPL_PATH="/sys/devices/virtual/powercap/intel-rapl/intel-rapl:0/energy_uj"
TMPFILES_CONF="/etc/tmpfiles.d/rapl-read.conf"

if [ -f "$RAPL_PATH" ]; then
    # Use systemd-tmpfiles to make RAPL readable on every boot
    # This is cleaner than sudo - no TTY issues with systemd services
    echo "f $RAPL_PATH 0444 root root -" | sudo tee "$TMPFILES_CONF" > /dev/null

    # Apply immediately without rebooting
    sudo systemd-tmpfiles --create "$TMPFILES_CONF"

    # Verify it worked
    if [ -r "$RAPL_PATH" ]; then
        echo -e "${GREEN}OK CPU power monitoring enabled${NC}"
    else
        echo -e "${YELLOW}⚠ Could not set RAPL permissions - CPU power will show N/A${NC}"
        sudo rm -f "$TMPFILES_CONF"
    fi
else
    echo -e "${YELLOW}⚠ RAPL interface not found - CPU power will show N/A${NC}"
fi
echo ""

# Create directories
echo -e "${BLUE}→ Creating directories...${NC}"
mkdir -p ~/.config/systemd/user
mkdir -p ~/linux-stats
echo -e "${GREEN}OK Directories created${NC}"
echo ""

# Save orientation preference to config
cat > ~/linux-stats/config.json << CONF_EOF
{
    "pi_ip": "$PI_IP",
    "orientation": "$ORIENTATION"
}
CONF_EOF
echo -e "${GREEN}OK Config saved (orientation: $ORIENTATION)${NC}"
echo ""

# Set up Python venv (required on SteamOS - pip is blocked system-wide)
echo -e "${BLUE}→ Setting up Python virtual environment...${NC}"
if [ ! -d ~/linux-stats/venv ]; then
    python3 -m venv ~/linux-stats/venv
    echo -e "${GREEN}OK Virtual environment created${NC}"
else
    echo -e "${GREEN}OK Virtual environment already exists${NC}"
fi
~/linux-stats/venv/bin/pip install --quiet requests
echo -e "${GREEN}OK Python dependencies installed${NC}"
echo ""

PYTHON_BIN="$HOME/linux-stats/venv/bin/python3"

# Create FPS Logger Script
echo -e "${BLUE}→ Creating MangoHud FPS logger...${NC}"
cat > ~/linux-stats/fps_logger.sh << 'EOF'
#!/bin/bash

FPS_FILE="/tmp/fps.txt"
# SteamOS writes MangoHud CSVs to ~/.local/share/MangoHud/
# Bazzite/other distros write to $HOME directly - check both
WATCH_DIRS=("$HOME/.local/share/MangoHud" "$HOME")

while true; do
    latest_csv=""
    for WATCH_DIR in "${WATCH_DIRS[@]}"; do
        candidate=$(ls -t "$WATCH_DIR"/*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv 2>/dev/null | head -1)
        if [ -n "$candidate" ]; then latest_csv="$candidate"; break; fi
    done
    # latest_csv now holds the most recent MangoHud CSV from either location
    
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

# Create MangoHud config - FPS only, hidden overlay, auto-logging
echo -e "${BLUE}→ Configuring MangoHud...${NC}"
mkdir -p ~/.config/MangoHud
cat > ~/.config/MangoHud/MangoHud.conf << 'MANGOHUD_EOF'
# Stats Display - MangoHud config
# Overlay is hidden (no_display=1) but logs FPS continuously in the background
# Toggle overlay visibility with Shift+F12 if needed

no_display=1
fps

# Auto-logging - writes CSV continuously without needing Shift+F2
log_interval=500
output_folder=~/.local/share/MangoHud
MANGOHUD_EOF
echo -e "${GREEN}OK MangoHud configured (FPS-only, auto-logging enabled)${NC}"
echo ""

# Create CSV Cleanup Script
echo -e "${BLUE}→ Creating CSV cleanup script...${NC}"
cat > ~/linux-stats/cleanup_fps_logs.sh << 'EOF'
#!/bin/bash

CLEANUP_DELAY=30  # Seconds after logging stops before cleanup
# Check both MangoHud log locations
WATCH_DIRS=("$HOME/.local/share/MangoHud" "$HOME")

while true; do
    for WATCH_DIR in "${WATCH_DIRS[@]}"; do
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
    done  # end WATCH_DIRS loop
    
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
    # No local copy found - likely running standalone via `curl | bash`
    # without a repo checkout next to it, so fetch it from GitHub directly.
    echo -e "${BLUE}→ No local copy found - downloading from GitHub...${NC}"
    SENDER_URL="https://raw.githubusercontent.com/pyrosplat/Linux-Stat-Display/main/LinuxPC/stat_sender_v1.py"
    if curl -fsSL "$SENDER_URL" -o ~/linux-stats/stat_sender.py; then
        SENDER_FOUND=true
        echo -e "${GREEN}OK Stats sender downloaded${NC}"
    fi
fi

if [ "$SENDER_FOUND" = false ]; then
    echo -e "${RED}ERROR: Error: stat_sender_v1.py not found${NC}"
    echo -e "${YELLOW}  Either run this installer from inside a cloned repo, or check your network connection${NC}"
    exit 1
fi

# Normalize line endings in case of a Windows-edited or CRLF source file
sed -i 's/\r$//' ~/linux-stats/stat_sender.py

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
ExecStart=$HOME/linux-stats/venv/bin/python3 $HOME/linux-stats/stat_sender.py
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

# Remove RAPL tmpfiles rule
sudo rm -f /etc/tmpfiles.d/rapl-read.conf
echo "OK Removed CPU power tmpfiles rule"

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
