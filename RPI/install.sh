#!/bin/bash
#==============================================================================
# Raspberry Pi Stats Display Installer
# Recommended: Raspberry Pi 3 or newer for best performance
#
# PATCHED for Rock Pi 4B+ / Radxa Bookworm KDE images:
#   1. Added python3-requests to the dependency list (stats_display.py
#      imports `requests`, which is not preinstalled on Debian like it
#      often is on Raspberry Pi OS).
#   2. Forced LightDM to actually become the active display manager.
#      Radxa's KDE image ships with SDDM by default; installing the
#      lightdm package alone does not switch the system over to it, so
#      the autologin-into-openbox config below was silently never used.
#
# Everything this app owns lives under one consolidated directory:
#   ~/stats-display/
#     app/      <- stats_display.py, start_optimized.sh
#     scripts/  <- rotate-portrait.sh, rotate-landscape.sh, rotate-boot.sh,
#                  restart-display.sh, stop-display.sh, status-display.sh
#     state/    <- orientation.txt (persisted orientation choice)
#     game_art/ <- custom game artwork
#
# A handful of files still have to live in OS-mandated locations and can't be
# moved into the tree above: the systemd unit (/etc/systemd/system/), the
# sudoers rule (/etc/sudoers.d/), the LightDM autologin config
# (/etc/lightdm/lightdm.conf.d/), and the openbox autostart script
# (~/.config/openbox/). Those are left where the OS expects them, but now
# point at the consolidated tree instead of /opt or loose home-dir files.
#==============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="stats-display"
STATS_SCRIPT="stats_display_v1.py"
CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME=$(getent passwd "$CURRENT_USER" | cut -d: -f6)

# Raw GitHub URL for the companion script, used only as a fallback when this
# installer is run standalone (e.g. via `curl | bash`) without a full repo
# checkout sitting next to it.
REPO_RAW_BASE="https://raw.githubusercontent.com/pyrosplat/Linux-Stat-Display/main"
STATS_SCRIPT_URL="$REPO_RAW_BASE/RPI/stats_display_v1.py"

# Consolidated app directory tree (all under the user's home, all owned by
# the user - no more /opt with root ownership complicating things)
APP_ROOT="$USER_HOME/stats-display"
APP_DIR="$APP_ROOT/app"
SCRIPTS_DIR="$APP_ROOT/scripts"
STATE_DIR="$APP_ROOT/state"
GAME_ART_DIR="$APP_ROOT/game_art"
ORIENTATION_STATE_FILE="$STATE_DIR/orientation.txt"

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
read -p "Choose orientation (1-2, default=1): " ORIENTATION_CHOICE < /dev/tty
ORIENTATION_CHOICE=${ORIENTATION_CHOICE:-1}

if [ "$ORIENTATION_CHOICE" = "2" ]; then
    ORIENTATION="landscape"
else
    ORIENTATION="portrait"
fi

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
# PATCH: added python3-requests - stats_display.py imports `requests`,
# which isn't preinstalled by default on plain Debian/Radxa images the way
# it often is on Raspberry Pi OS.
apt-get install -y \
    python3 \
    python3-pip \
    python3-flask \
    python3-requests \
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

pip3 install --break-system-packages --root-user-action=ignore flask requests
print_success "Dependencies installed"

#==============================================================================
# 3. CREATE CONSOLIDATED APP DIRECTORY TREE
#==============================================================================
print_header "Setting Up Installation Directory"
mkdir -p "$APP_DIR" "$SCRIPTS_DIR" "$STATE_DIR" "$GAME_ART_DIR"
chown -R "$CURRENT_USER:$CURRENT_USER" "$APP_ROOT"
print_success "Directory tree created at $APP_ROOT"

#==============================================================================
# 4. COPY STATS DISPLAY SCRIPT
#==============================================================================
print_header "Installing Stats Display Script"

if [ -f "$STATS_SCRIPT" ]; then
    cp "$STATS_SCRIPT" "$APP_DIR/stats_display.py"
    print_success "Stats display script installed (found locally)"
elif [ -f "/home/$CURRENT_USER/$STATS_SCRIPT" ]; then
    cp "/home/$CURRENT_USER/$STATS_SCRIPT" "$APP_DIR/stats_display.py"
    print_success "Stats display script installed (found in home directory)"
else
    # No local copy found - this installer is likely being run standalone
    # (e.g. `curl -fsSL .../install.sh | sudo bash`) without a repo checkout
    # next to it, so fetch the companion script directly from GitHub.
    print_info "No local copy found - downloading from GitHub..."
    if curl -fsSL "$STATS_SCRIPT_URL" -o "$APP_DIR/stats_display.py"; then
        print_success "Stats display script downloaded"
    else
        print_error "Could not download stats display script from $STATS_SCRIPT_URL"
        print_info "Either run this installer from inside a cloned repo, or check your network connection"
        exit 1
    fi
fi

# Normalize line endings in case of a Windows-edited or CRLF source file
sed -i 's/\r$//' "$APP_DIR/stats_display.py"
chmod +x "$APP_DIR/stats_display.py"
chown "$CURRENT_USER:$CURRENT_USER" "$APP_DIR/stats_display.py" 2>/dev/null || true

#==============================================================================
# 5. CONFIGURE DISPLAY ORIENTATION
#==============================================================================
print_header "Configuring Display Orientation"

if [ "$ORIENTATION" = "landscape" ]; then
    print_info "Setting orientation to: Landscape (1920x480)"
else
    print_info "Setting orientation to: Portrait (480x1920)"
fi

# Update the compiled-in fallback default in the script itself
if [ -f "$APP_DIR/stats_display.py" ]; then
    sed -i "s/DEFAULT_ORIENTATION = \"portrait\"/DEFAULT_ORIENTATION = \"$ORIENTATION\"/" "$APP_DIR/stats_display.py"
    sed -i "s/DEFAULT_ORIENTATION = \"landscape\"/DEFAULT_ORIENTATION = \"$ORIENTATION\"/" "$APP_DIR/stats_display.py"
    print_success "Stats display orientation set to: $ORIENTATION"
fi

# Persist the choice to the state file - this is what the boot-time rotation
# script and the settings-panel API both read/write, so there's a single
# source of truth and no need to ever edit the systemd unit at runtime.
echo -n "$ORIENTATION" > "$ORIENTATION_STATE_FILE"
chown "$CURRENT_USER:$CURRENT_USER" "$ORIENTATION_STATE_FILE"

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

# Single boot-time wrapper that reads the persisted orientation state file
# and calls the matching rotation script. This is the key simplification:
# the systemd unit's ExecStartPre NEVER needs to change based on which
# orientation is selected - it always calls this same script, and this
# script is what decides. Changing orientation from the settings panel just
# rewrites the state file; no systemd-unit editing or sudo needed for that.
cat > "$SCRIPTS_DIR/rotate-boot.sh" << BOOT_EOF
#!/bin/bash
# Boot-time rotation (with X server wait) - reads the persisted orientation
sleep 5
export HOME=$USER_HOME
STATE_FILE="$ORIENTATION_STATE_FILE"
ORIENTATION="portrait"
if [ -f "\$STATE_FILE" ]; then
    ORIENTATION=\$(cat "\$STATE_FILE")
fi
if [ "\$ORIENTATION" = "landscape" ]; then
    /bin/bash "$SCRIPTS_DIR/rotate-landscape.sh"
else
    /bin/bash "$SCRIPTS_DIR/rotate-portrait.sh"
fi
BOOT_EOF

chmod +x "$SCRIPTS_DIR/rotate-portrait.sh" "$SCRIPTS_DIR/rotate-landscape.sh" "$SCRIPTS_DIR/rotate-boot.sh"
chown "$CURRENT_USER:$CURRENT_USER" "$SCRIPTS_DIR/rotate-portrait.sh" "$SCRIPTS_DIR/rotate-landscape.sh" "$SCRIPTS_DIR/rotate-boot.sh"

print_success "Rotation scripts created in $SCRIPTS_DIR"
print_info "Display rotation is handled via xrandr (software rotation)"

#==============================================================================
# 6. CREATE SYSTEMD SERVICE FOR FLASK SERVER
#==============================================================================
print_header "Creating Systemd Service"

cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Stats Display Flask Server
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
Environment="PYTHONUNBUFFERED=1"
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/var/run/lightdm/$CURRENT_USER/:0"
Environment="HOME=$USER_HOME"
ExecStartPre=/bin/sleep 15
ExecStartPre=-/bin/bash $SCRIPTS_DIR/rotate-boot.sh
ExecStart=$APP_DIR/start_optimized.sh
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
# 9. CONFIGURE LIGHTDM AUTO-LOGIN
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

# PATCH: Force LightDM to actually be the system's active display manager.
# On distros like Radxa's KDE image (which default to SDDM), simply
# installing the lightdm package and writing its config does nothing -
# SDDM stays in control and keeps showing its own login screen, so the
# autologin-into-openbox config above is silently never used. This makes
# LightDM the one systemd actually starts.
print_info "Ensuring LightDM is the active display manager (was likely SDDM)..."
echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager
systemctl disable sddm.service 2>/dev/null || true
systemctl disable gdm.service 2>/dev/null || true
systemctl disable gdm3.service 2>/dev/null || true
systemctl enable lightdm.service
print_success "LightDM set as active display manager for user: $CURRENT_USER"

#==============================================================================
# 10. OPTIMIZE FLASK SERVER FOR PI ZERO
#==============================================================================
print_header "Optimizing Flask Server"

# Create optimized Python startup script
cat > "$APP_DIR/start_optimized.sh" << 'EOF'
#!/bin/bash
# Set Python to use less memory
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

# Reduce Flask worker threads
exec python3 -u stats_display.py
EOF

chmod +x "$APP_DIR/start_optimized.sh"
chown "$CURRENT_USER:$CURRENT_USER" "$APP_DIR/start_optimized.sh"
print_success "Flask server optimized for low memory"

#==============================================================================
# 11. CREATE HELPER SCRIPTS
#==============================================================================
print_header "Creating Helper Scripts"

# Restart script
cat > "$SCRIPTS_DIR/restart-display.sh" << EOF
#!/bin/bash
sudo systemctl restart ${SERVICE_NAME}.service
killall chromium firefox-esr falkon 2>/dev/null
sleep 2
echo "Stats display service restarted"
echo "Browser will auto-launch on next login or reboot"
EOF
chmod +x "$SCRIPTS_DIR/restart-display.sh"

# Stop script
cat > "$SCRIPTS_DIR/stop-display.sh" << EOF
#!/bin/bash
sudo systemctl stop ${SERVICE_NAME}.service
killall chromium firefox-esr falkon 2>/dev/null
echo "Stats display stopped"
EOF
chmod +x "$SCRIPTS_DIR/stop-display.sh"

# Status script
cat > "$SCRIPTS_DIR/status-display.sh" << EOF
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
chmod +x "$SCRIPTS_DIR/status-display.sh"

chown "$CURRENT_USER:$CURRENT_USER" "$SCRIPTS_DIR"/*.sh
print_success "Helper scripts created in $SCRIPTS_DIR"

#==============================================================================
# 12. CONFIGURE SUDO PERMISSIONS FOR SETTINGS PAGE
#==============================================================================
print_header "Configuring Sudo Permissions for Settings Page"

# Create sudoers file for stats display settings.
# NOTE: cp/rm are no longer needed here - orientation changes now just
# rewrite a state file the app already owns, instead of patching the
# systemd unit at runtime. Only reboot/shutdown from the settings page
# still need elevated privileges.
cat > /tmp/stats-display-settings << EOF
# Allow $CURRENT_USER to reboot/shutdown from the stats display settings page
$CURRENT_USER ALL=(ALL) NOPASSWD: /sbin/shutdown, /sbin/reboot
EOF

# Install sudoers file with proper permissions
cp /tmp/stats-display-settings /etc/sudoers.d/stats-display-settings
chmod 0440 /etc/sudoers.d/stats-display-settings
rm /tmp/stats-display-settings

# Verify sudoers file is valid
if visudo -c -f /etc/sudoers.d/stats-display-settings &>/dev/null; then
    print_success "Sudo permissions configured for settings page"
    print_info "User '$CURRENT_USER' can now use web interface to reboot"
else
    print_warning "Sudoers file validation failed - reboot button may not work"
    rm /etc/sudoers.d/stats-display-settings
fi

#==============================================================================
# 13. CREATE UNINSTALLER
#==============================================================================
print_header "Creating Uninstaller"

# Deliberately placed at $USER_HOME (next to, not inside, $APP_ROOT). The
# uninstaller does `rm -rf "$APP_ROOT"`, so if it lived inside that same
# tree it could delete itself mid-run.
UNINSTALL_SCRIPT="$USER_HOME/uninstall-stats-display.sh"

cat > "$UNINSTALL_SCRIPT" << 'UNINSTALL_EOF'
#!/bin/bash
#==============================================================================
# Raspberry Pi Stats Display Uninstaller
# Removes everything install.sh creates: the consolidated ~/stats-display
# tree, plus the system-level files that had to live in OS-mandated
# locations (systemd unit, sudoers rule, LightDM autologin, openbox
# autostart).
#==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() { echo -e "${BLUE}========================================${NC}"; echo -e "${BLUE}$1${NC}"; echo -e "${BLUE}========================================${NC}"; }
print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_success() { echo -e "${GREEN}[OK]${NC} $1"; }

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Please run this script with sudo"
    exit 1
fi

SERVICE_NAME="stats-display"
CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME=$(getent passwd "$CURRENT_USER" | cut -d: -f6)
APP_ROOT="$USER_HOME/stats-display"

print_header "Stats Display Uninstaller"
read -p "This will remove the stats display and all its files. Continue? (y/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# 1. Stop and remove the systemd service
print_header "Removing systemd service"
systemctl stop ${SERVICE_NAME}.service 2>/dev/null || true
systemctl disable ${SERVICE_NAME}.service 2>/dev/null || true
rm -f /etc/systemd/system/${SERVICE_NAME}.service
systemctl daemon-reload
print_success "Service removed"

# 2. Remove the sudoers rule
print_header "Removing sudoers rule"
rm -f /etc/sudoers.d/stats-display-settings
print_success "Sudoers rule removed"

# 3. Undo LightDM autologin config
print_header "Reverting LightDM auto-login"
rm -f /etc/lightdm/lightdm.conf.d/50-autologin.conf
if [ -f /etc/lightdm/lightdm.conf.backup ]; then
    cp /etc/lightdm/lightdm.conf.backup /etc/lightdm/lightdm.conf
    print_success "Restored original lightdm.conf from backup"
else
    print_warning "No lightdm.conf.backup found - leaving lightdm.conf as-is"
fi

# 4. Remove openbox autostart
print_header "Removing openbox autostart"
rm -f "$USER_HOME/.config/openbox/autostart"
print_success "Openbox autostart removed"

# 5. Remove the consolidated app directory
print_header "Removing app files"
if [ -d "$APP_ROOT" ]; then
    read -p "Remove custom game art in $APP_ROOT/game_art too? (y/N): " REMOVE_ART
    if [[ ! "$REMOVE_ART" =~ ^[Yy]$ ]] && [ -d "$APP_ROOT/game_art" ]; then
        mkdir -p "$USER_HOME/game_art_backup"
        cp -r "$APP_ROOT/game_art/." "$USER_HOME/game_art_backup/" 2>/dev/null || true
        print_info "Backed up game_art to $USER_HOME/game_art_backup"
    fi
    rm -rf "$APP_ROOT"
    print_success "Removed $APP_ROOT"
else
    print_warning "$APP_ROOT not found - nothing to remove"
fi

# 6. Clean up legacy locations from older installs (pre-consolidation),
# in case this uninstaller is run against an install that predates the
# single-directory layout.
print_header "Checking for legacy files from older installs"
[ -d /opt/stats-display ] && { rm -rf /opt/stats-display; print_info "Removed legacy /opt/stats-display"; }
[ -f "$USER_HOME/restart-display.sh" ] && { rm -f "$USER_HOME/restart-display.sh"; print_info "Removed legacy ~/restart-display.sh"; }
[ -f "$USER_HOME/stop-display.sh" ] && { rm -f "$USER_HOME/stop-display.sh"; print_info "Removed legacy ~/stop-display.sh"; }
[ -f "$USER_HOME/status-display.sh" ] && { rm -f "$USER_HOME/status-display.sh"; print_info "Removed legacy ~/status-display.sh"; }

if [ -d "$USER_HOME/game_art" ]; then
    print_warning "Legacy ~/game_art still exists - leaving it in place (not removed automatically, may contain your custom art)"
fi

print_header "Uninstall Complete"
print_success "Stats display has been removed. Reboot recommended: sudo reboot"

# Remove self last
rm -f "$USER_HOME/uninstall-stats-display.sh" 2>/dev/null || true
UNINSTALL_EOF

chmod +x "$UNINSTALL_SCRIPT"
chown "$CURRENT_USER:$CURRENT_USER" "$UNINSTALL_SCRIPT"
print_success "Uninstaller created at $UNINSTALL_SCRIPT"

#==============================================================================
# 14. START THE SERVICE
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
echo -e "${GREEN}Everything lives under:${NC} $APP_ROOT"
echo "  app/      stats_display.py, start_optimized.sh"
echo "  scripts/  rotation + restart/stop/status scripts"
echo "  state/    orientation.txt"
echo "  game_art/ custom game artwork"
echo ""
echo -e "${GREEN}Access Points:${NC}"
echo "  Main Display:   http://${LOCAL_IP}:5000"
echo "  Settings Page:  http://${LOCAL_IP}:5000/settings"
echo ""
echo -e "${GREEN}Quick Commands:${NC}"
echo "  Restart display: $SCRIPTS_DIR/restart-display.sh"
echo "  Stop display:    $SCRIPTS_DIR/stop-display.sh"
echo "  Check status:    $SCRIPTS_DIR/status-display.sh"
echo "  Uninstall:       sudo $UNINSTALL_SCRIPT"
echo ""
echo -e "${YELLOW}Next Step:${NC}"
echo -e "  Reboot to start auto-display: ${GREEN}sudo reboot${NC}"
echo ""
print_success "Setup complete!"
