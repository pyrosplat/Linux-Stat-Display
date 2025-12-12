#!/bin/bash
#==============================================================================
# Raspberry Pi Stats Display Installer
# Recommended: Raspberry Pi 3 or newer for best performance
#==============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/stats-display"
SERVICE_NAME="stats-display"
STATS_SCRIPT="stats_display_v1.py"
CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME=$(getent passwd "$CURRENT_USER" | cut -d: -f6)

# Print functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run this script with sudo"
    exit 1
fi

print_header "Raspberry Pi Stats Display Installer"
echo "Recommended: Raspberry Pi 3 or newer"
echo ""
echo "Display orientation options:"
echo "  1) Portrait (vertical - 480x1920)"
echo "  2) Landscape (horizontal - 1920x480)"
echo ""
read -p "Choose orientation (1-2, default=1): " ORIENTATION_CHOICE
ORIENTATION_CHOICE=${ORIENTATION_CHOICE:-1}

#==============================================================================
# 1. UPDATE SYSTEM
#==============================================================================
print_header "Updating System"
apt-get update
apt-get upgrade -y
print_success "System updated"

#==============================================================================
# 2. INSTALL DEPENDENCIES
#==============================================================================
print_header "Installing Dependencies"

# Common dependencies
apt-get install -y \
    python3 \
    python3-pip \
    python3-flask \
    x11-xserver-utils \
    xdotool \
    unclutter \
    lightdm \
    openbox \
    xinit \
    python3-xdg

# Install Firefox ESR
print_info "Installing Firefox ESR..."
apt-get install -y firefox-esr
BROWSER_CMD="firefox-esr"
KIOSK_FLAGS="--kiosk --private-window"
BROWSER_CLASS="firefox"

pip3 install --break-system-packages --root-user-action=ignore flask
print_success "Dependencies installed"

#==============================================================================
# 3. CREATE INSTALLATION DIRECTORY
#==============================================================================
print_header "Setting Up Installation Directory"
mkdir -p "$INSTALL_DIR"
mkdir -p "$USER_HOME/game_art"
chown -R "$CURRENT_USER:$CURRENT_USER" "$USER_HOME/game_art"
print_success "Directories created"

#==============================================================================
# 4. COPY STATS DISPLAY SCRIPT
#==============================================================================
print_header "Installing Stats Display Script"
if [ -f "$STATS_SCRIPT" ]; then
    cp "$STATS_SCRIPT" "$INSTALL_DIR/stats_display.py"
    chmod +x "$INSTALL_DIR/stats_display.py"
    print_success "Stats display script installed"
elif [ -f "/home/$CURRENT_USER/$STATS_SCRIPT" ]; then
    cp "/home/$CURRENT_USER/$STATS_SCRIPT" "$INSTALL_DIR/stats_display.py"
    chmod +x "$INSTALL_DIR/stats_display.py"
    print_success "Stats display script installed"
else
    print_warning "Stats script not found in current directory"
    print_info "Please place $STATS_SCRIPT in $INSTALL_DIR and make it executable"
fi

#==============================================================================
# 5. CONFIGURE DISPLAY ORIENTATION
#==============================================================================
print_header "Configuring Display Orientation"

# Create scripts directory
SCRIPTS_DIR="$USER_HOME/stats-display"
mkdir -p "$SCRIPTS_DIR"
chown $CURRENT_USER:$CURRENT_USER "$SCRIPTS_DIR"

# Set orientation based on user choice
if [ "$ORIENTATION_CHOICE" = "2" ]; then
    ORIENTATION="landscape"
    print_info "Setting orientation to: Landscape (1920x480)"
else
    ORIENTATION="portrait"
    print_info "Setting orientation to: Portrait (480x1920)"
fi

# Update the Python stats display script orientation
if [ -f "$INSTALL_DIR/stats_display.py" ]; then
    sed -i "s/DEFAULT_ORIENTATION = \"portrait\"/DEFAULT_ORIENTATION = \"$ORIENTATION\"/" "$INSTALL_DIR/stats_display.py"
    sed -i "s/DEFAULT_ORIENTATION = \"landscape\"/DEFAULT_ORIENTATION = \"$ORIENTATION\"/" "$INSTALL_DIR/stats_display.py"
    print_success "Stats display orientation set to: $ORIENTATION"
fi

# Create rotation management scripts
print_info "Creating display rotation scripts..."

# Create portrait rotation script
cat > "$SCRIPTS_DIR/rotate-portrait.sh" << 'PORTRAIT_EOF'
#!/bin/bash
# Portrait rotation script - optimized for speed

export DISPLAY=:0

# Rotate display to portrait (normal)
xrandr --output HDMI-1 --rotate normal 2>/dev/null &
XRANDR_PID=$!

# Find touchscreen device ID while xrandr runs
TOUCH_ID=$(xinput list 2>/dev/null | grep -i "QDTECH\|MPI\|touch" | grep -v "XTEST" | head -1 | sed 's/.*id=\([0-9]*\).*/\1/')

# Wait for xrandr to finish
wait $XRANDR_PID

# Map touchscreen immediately
if [ -n "$TOUCH_ID" ]; then
    xinput map-to-output "$TOUCH_ID" HDMI-1 2>/dev/null
fi

echo "Display rotated to portrait"
PORTRAIT_EOF

# Create landscape rotation script
cat > "$SCRIPTS_DIR/rotate-landscape.sh" << 'LANDSCAPE_EOF'
#!/bin/bash
# Landscape rotation script - optimized for speed

export DISPLAY=:0

# Rotate display to landscape (left)
xrandr --output HDMI-1 --rotate left 2>/dev/null &
XRANDR_PID=$!

# Find touchscreen device ID while xrandr runs
TOUCH_ID=$(xinput list 2>/dev/null | grep -i "QDTECH\|MPI\|touch" | grep -v "XTEST" | head -1 | sed 's/.*id=\([0-9]*\).*/\1/')

# Wait for xrandr to finish
wait $XRANDR_PID

# Map touchscreen immediately
if [ -n "$TOUCH_ID" ]; then
    xinput map-to-output "$TOUCH_ID" HDMI-1 2>/dev/null
fi

echo "Display rotated to landscape"
LANDSCAPE_EOF

# Make scripts executable
chmod +x "$SCRIPTS_DIR/rotate-portrait.sh"
chmod +x "$SCRIPTS_DIR/rotate-landscape.sh"
chown $CURRENT_USER:$CURRENT_USER "$SCRIPTS_DIR/rotate-portrait.sh"
chown $CURRENT_USER:$CURRENT_USER "$SCRIPTS_DIR/rotate-landscape.sh"

# Create boot-time wrappers (with X server wait)
cat > "$SCRIPTS_DIR/rotate-landscape-boot.sh" << 'BOOT_LANDSCAPE_EOF'
#!/bin/bash
# Boot-time landscape rotation (with X server wait)
sleep 5
export HOME=/home/pi
/bin/bash $HOME/stats-display/rotate-landscape.sh
BOOT_LANDSCAPE_EOF

cat > "$SCRIPTS_DIR/rotate-portrait-boot.sh" << 'BOOT_PORTRAIT_EOF'
#!/bin/bash
# Boot-time portrait rotation (with X server wait)
sleep 5
export HOME=/home/pi
/bin/bash $HOME/stats-display/rotate-portrait.sh
BOOT_PORTRAIT_EOF

chmod +x "$SCRIPTS_DIR/rotate-portrait-boot.sh"
chmod +x "$SCRIPTS_DIR/rotate-landscape-boot.sh"
chown $CURRENT_USER:$CURRENT_USER "$SCRIPTS_DIR/rotate-portrait-boot.sh"
chown $CURRENT_USER:$CURRENT_USER "$SCRIPTS_DIR/rotate-landscape-boot.sh"

print_success "Rotation scripts created in $SCRIPTS_DIR"

# Note: Physical display rotation via config.txt is NOT used anymore
# We use xrandr for rotation which is more reliable
print_info "Display rotation will be handled via xrandr (software rotation)"

#==============================================================================
# 6. CREATE SYSTEMD SERVICE FOR FLASK SERVER
#==============================================================================
print_header "Creating Systemd Service"

# Determine which rotation script to use
if [ "$ORIENTATION" = "landscape" ]; then
    ROTATION_SCRIPT="$SCRIPTS_DIR/rotate-landscape-boot.sh"
else
    ROTATION_SCRIPT="$SCRIPTS_DIR/rotate-portrait-boot.sh"
fi

cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Stats Display Flask Server
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
Environment="PYTHONUNBUFFERED=1"
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/var/run/lightdm/$CURRENT_USER/:0"
Environment="HOME=$USER_HOME"
ExecStartPre=/bin/sleep 15
ExecStartPre=-/bin/bash $ROTATION_SCRIPT
ExecStart=/usr/bin/python3 $INSTALL_DIR/stats_display.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service
print_success "Systemd service created and enabled"

#==============================================================================
# 7. DISABLE POWER MANAGEMENT & SCREENSAVER
#==============================================================================
print_header "Configuring Power Management"

# Disable screen blanking in boot config
if ! grep -q "hdmi_blanking=1" /boot/config.txt 2>/dev/null && \
   ! grep -q "hdmi_blanking=1" /boot/firmware/config.txt 2>/dev/null; then
    if [ -f /boot/firmware/config.txt ]; then
        echo "hdmi_blanking=1" >> /boot/firmware/config.txt
    elif [ -f /boot/config.txt ]; then
        echo "hdmi_blanking=1" >> /boot/config.txt
    fi
fi

# Disable HDMI power saving
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
fi

if [ -n "$CONFIG_FILE" ]; then
    if ! grep -q "hdmi_force_hotplug=1" "$CONFIG_FILE"; then
        echo "hdmi_force_hotplug=1" >> "$CONFIG_FILE"
    fi
    if ! grep -q "hdmi_drive=2" "$CONFIG_FILE"; then
        echo "hdmi_drive=2" >> "$CONFIG_FILE"
    fi
fi

# GPU memory optimization for Pi Zero
if [ -n "$CONFIG_FILE" ]; then
    if ! grep -q "gpu_mem=" "$CONFIG_FILE"; then
        echo "# GPU memory allocation (optimized for stats display)" >> "$CONFIG_FILE"
        echo "gpu_mem=128" >> "$CONFIG_FILE"
        print_info "Set GPU memory to 128MB for better browser performance"
    fi
fi

print_success "Power management configured"

#==============================================================================
# 8. CONFIGURE OPENBOX FOR AUTO-START
#==============================================================================
print_header "Configuring Openbox Auto-start"

# Create openbox config directory
mkdir -p "$USER_HOME/.config/openbox"

# Create autostart script with optimized browser launch
cat > "$USER_HOME/.config/openbox/autostart" << EOF
#!/bin/bash

# Disable screen blanking and power management
xset s off
xset s noblank
xset -dpms

# Hide mouse cursor after 0.1 seconds of inactivity
unclutter -idle 0.1 -root &

# Wait for network and Flask server to be ready
sleep 5

# Get local IP address
LOCAL_IP=\$(hostname -I | awk '{print \$1}')

# Launch browser in kiosk mode
$BROWSER_CMD $KIOSK_FLAGS "http://\${LOCAL_IP}:5000" &

# Wait for browser to start
sleep 3

# Make sure it's fullscreen (backup for some browsers)
WID=\$(xdotool search --class "$BROWSER_CLASS" | head -1)
if [ -n "\$WID" ]; then
    xdotool windowactivate "\$WID"
    xdotool key F11
fi
EOF

chmod +x "$USER_HOME/.config/openbox/autostart"
chown -R "$CURRENT_USER:$CURRENT_USER" "$USER_HOME/.config"
print_success "Openbox autostart configured with $BROWSER_CMD"

#==============================================================================
# 9. CONFIGURE LIGHTDM AUTO-LOGIN (FIXED)
#==============================================================================
print_header "Configuring Auto-Login"

# Backup the original lightdm.conf
if [ -f /etc/lightdm/lightdm.conf ]; then
    cp /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.backup
    print_info "Backed up original lightdm.conf"
fi

# Comment out any existing autologin-session and user-session in main config
# This prevents Raspberry Pi OS defaults (LXDE-pi-labwc) from overriding our settings
if [ -f /etc/lightdm/lightdm.conf ]; then
    sed -i 's/^autologin-session=/#autologin-session=/g' /etc/lightdm/lightdm.conf
    sed -i 's/^user-session=/#user-session=/g' /etc/lightdm/lightdm.conf
    print_info "Disabled default session settings in main config"
fi

# Configure LightDM for auto-login with Openbox
mkdir -p /etc/lightdm/lightdm.conf.d/
cat > /etc/lightdm/lightdm.conf.d/50-autologin.conf << EOF
[Seat:*]
autologin-user=$CURRENT_USER
autologin-user-timeout=0
autologin-session=openbox
EOF

print_success "Auto-login configured for user: $CURRENT_USER"

#==============================================================================
# 10. OPTIMIZE FLASK SERVER FOR PI ZERO
#==============================================================================
print_header "Optimizing Flask Server"

# Create optimized Python startup script
cat > "$INSTALL_DIR/start_optimized.sh" << 'EOF'
#!/bin/bash
# Set Python to use less memory
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

# Reduce Flask worker threads
exec python3 -u stats_display.py
EOF

chmod +x "$INSTALL_DIR/start_optimized.sh"

# Update service to use optimized startup
sed -i "s|ExecStart=/usr/bin/python3.*|ExecStart=$INSTALL_DIR/start_optimized.sh|" /etc/systemd/system/${SERVICE_NAME}.service
systemctl daemon-reload

print_success "Flask server optimized for low memory"

#==============================================================================
# 11. CREATE HELPER SCRIPTS
#==============================================================================
print_header "Creating Helper Scripts"

# Restart script
cat > "$USER_HOME/restart-display.sh" << EOF
#!/bin/bash
sudo systemctl restart ${SERVICE_NAME}.service
killall chromium firefox-esr falkon 2>/dev/null
sleep 2
echo "Stats display service restarted"
echo "Browser will auto-launch on next login or reboot"
EOF
chmod +x "$USER_HOME/restart-display.sh"

# Stop script
cat > "$USER_HOME/stop-display.sh" << EOF
#!/bin/bash
sudo systemctl stop ${SERVICE_NAME}.service
killall chromium firefox-esr falkon 2>/dev/null
echo "Stats display stopped"
EOF
chmod +x "$USER_HOME/stop-display.sh"

# Status script
cat > "$USER_HOME/status-display.sh" << EOF
#!/bin/bash
echo "Service Status:"
sudo systemctl status ${SERVICE_NAME}.service --no-pager
echo ""
echo "Browser: $BROWSER_CMD"
echo "Network Info:"
hostname -I
echo ""
echo "Access display at: http://\$(hostname -I | awk '{print \$1}'):5000"
echo ""
echo "Memory Usage:"
free -h
echo ""
echo "Running Browser:"
ps aux | grep -E 'chromium|firefox|falkon' | grep -v grep | head -1
EOF
chmod +x "$USER_HOME/status-display.sh"

chown "$CURRENT_USER:$CURRENT_USER" "$USER_HOME"/*.sh
print_success "Helper scripts created"

#==============================================================================
# 12. CONFIGURE SUDO PERMISSIONS FOR SETTINGS PAGE
#==============================================================================
print_header "Configuring Sudo Permissions for Settings Page"

# Create sudoers file for stats display settings
# This allows the web interface to update boot config and reboot
cat > /tmp/stats-display-settings << EOF
# Allow pi user to run specific commands for stats display settings
$CURRENT_USER ALL=(ALL) NOPASSWD: /bin/cp, /bin/rm, /sbin/shutdown, /sbin/reboot
EOF

# Install sudoers file with proper permissions
cp /tmp/stats-display-settings /etc/sudoers.d/stats-display-settings
chmod 0440 /etc/sudoers.d/stats-display-settings
rm /tmp/stats-display-settings

# Verify sudoers file is valid
if visudo -c -f /etc/sudoers.d/stats-display-settings &>/dev/null; then
    print_success "Sudo permissions configured for settings page"
    print_info "User '$CURRENT_USER' can now use web interface to change orientation and reboot"
else
    print_warning "Sudoers file validation failed - settings page may not work"
    rm /etc/sudoers.d/stats-display-settings
fi

#==============================================================================
# 13. START THE SERVICE
#==============================================================================
print_header "Starting Stats Display Service"
systemctl start ${SERVICE_NAME}.service
sleep 2

if systemctl is-active --quiet ${SERVICE_NAME}.service; then
    print_success "Stats display service is running"
else
    print_warning "Service may not be running. Check with: sudo systemctl status ${SERVICE_NAME}.service"
fi

#==============================================================================
# INSTALLATION COMPLETE
#==============================================================================
print_header "Installation Complete!"
echo ""
echo -e "${GREEN}✓ Stats Display Ready${NC}"
echo ""
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "Browser: $BROWSER_CMD"
echo "Orientation: $ORIENTATION"
echo "IP Address: $LOCAL_IP"
echo ""
echo -e "${GREEN}Access Points:${NC}"
echo "  Main Display:  http://${LOCAL_IP}:5000"
echo "  Settings Page: http://${LOCAL_IP}:5000/settings"
echo ""
echo -e "${GREEN}Quick Commands:${NC}"
echo "  Restart display: ~/restart-display.sh"
echo "  Stop display:    ~/stop-display.sh"
echo "  Check status:    ~/status-display.sh"
echo ""
echo -e "${YELLOW}Next Step:${NC}"
echo "  Reboot to start auto-display: ${GREEN}sudo reboot${NC}"
echo ""
print_success "Setup complete!"
