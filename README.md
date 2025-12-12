# Linux PC Stats Display  

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-3%2B-red.svg)
![Linux](https://img.shields.io/badge/Linux-Compatible-green.svg)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/pyrocac)

Real-time system stats from your Linux gaming PC displayed on a Raspberry Pi touchscreen.

![Custom Game Art Example](examples/CustomRidge.png)

Works on Bazzite, SteamOS, and other Linux distributions.

## Features

- **8 Color Themes** - Dark/Cyberpunk, Light, Matrix, Retro, Nord, Dracula, Black & White, Steam
- **Dual Orientation** - Portrait (480×1920) or Landscape (1920×480) with instant switching
- **Custom Game Art** - Display your own game artwork (JPG, PNG, WEBP, GIF animations)
- **Real-time Stats** - CPU, GPU, RAM, VRAM, FPS, temperatures, frequencies, power usage
- **Steam Integration** - Game names, player counts, artwork
- **Touch Controls** - Settings panel with themes, orientation, network info
- **Auto-start** - Boots directly into stats display

### Screenshots

| Portrait - Black & White Theme | Portrait - Light Theme | Portrait - Cyberpunk Theme |
|:------------------------------:|:-------------------------:|:--------------------------:|
| ![Portrait BW](examples/BlackWhiteTheme.png) | ![Light](examples/LightTheme.png) | ![Cyberpunk](examples/CyberPunkTheme.png) |

**Settings Panel:**

- Theme selection (8 themes)
- Display rotation (Portrait/Landscape with touch calibration)
- Gauge display mode (Usage % or Temperature)
- Network information
- Disk information

## What You Need

- **Linux Gaming PC** - Bazzite, SteamOS, Ubuntu, Fedora, Arch, etc.
- **Raspberry Pi 3 or newer** - Pi 4/5 recommended for best performance
- **Touchscreen Display** - 480×1920 or 1920×480 (landscape capable)
- **Both on the same network**

## Quick Install

### 1. Install on Raspberry Pi

```bash
unzip RPI_Stats_Display.zip
cd RPI_Stats_Display/RPI
chmod +x install.sh
sudo ./install.sh
```

The installer will:
- Install Firefox ESR browser
- Configure display rotation
- Create rotation scripts in `~/stats-display/`
- Set up systemd service for auto-start
- Ask for orientation preference (Portrait or Landscape)

After install:
```bash
sudo reboot
```

The stats display will auto-start on boot.

### 2. Install on Linux PC

```bash
unzip RPI_Stats_Display.zip
cd RPI_Stats_Display/LinuxPC
chmod +x install.sh
./install.sh
```

Enter your Raspberry Pi's IP address when prompted.

The installer will:
- Set up MangoHud FPS logger
- Configure auto CSV cleanup
- Install stats sender service
- Start sending stats to the Pi

## Usage

### Main Display

After installation, the stats display automatically appears on the Pi screen showing:


## Custom Game Art

Place custom game artwork in `~/game_art/` on the Raspberry Pi.

**File naming options:**

**By Steam AppID (most reliable):**
```
1091500.jpg          # Cyberpunk 2077
2357570.png          # Elden Ring
271590.webp          # Grand Theft Auto V
```

**By game name:**
```
Cyberpunk 2077.jpg
Elden Ring.png
Grand Theft Auto V.gif
```

**Supported formats:**
- `.jpg` / `.jpeg`
- `.png`
- `.webp`
- `.gif` (animated GIFs work!)

**Tips:**
- Use Steam AppID for reliability
- 600×900 aspect ratio recommended (Steam library format)
- Files are cached - faster than Steam CDN

## FPS Detection

Add to your Steam game launch options:

**MangoHud (Recommended):**
```
mangohud %command%
```

MangoHud logs FPS to CSV files which the stats sender reads and transmits to the Pi.

**Gamescope (Alternative):**
```
gamescope --stats-path /tmp/gamescope-stats -- %command%
```


## Troubleshooting

### Display not showing stats

```bash
# Check service status
sudo systemctl status stats-display.service

# View logs
sudo journalctl -u stats-display.service -n 50

# Restart service
sudo systemctl restart stats-display.service
```

### Orientation change fails

The system uses `xrandr` for instant rotation. If issues occur:

```bash
# Test rotation manually
cd ~/stats-display
./rotate-landscape.sh  # or ./rotate-portrait.sh

# Check if X server is running
echo $DISPLAY  # Should show :0

# Test touch calibration
xinput list  # Find your touch device
xinput map-to-output <device-id> HDMI-1
```

### Touch input not working

Touch calibration happens automatically during rotation. If it doesn't work:

```bash
# Find touch device ID
xinput list | grep -i touch

# Map to output (replace 7 with your device ID)
DISPLAY=:0 xinput map-to-output 7 HDMI-1
```

### Stats not updating from PC

```bash
# Check sender service on Linux PC
systemctl --user status stats-sender.service

# View sender logs
journalctl --user -u stats-sender.service -f

# Restart sender
systemctl --user restart stats-sender.service

# Test network connection
ping <RASPBERRY_PI_IP>
```

### Firefox kiosk mode not starting

```bash
# Check browser autostart
ls -la ~/.config/autostart/

# Manually start Firefox kiosk
firefox-esr --kiosk --private-window http://localhost:5000 &
```

## Advanced Configuration

### Changing the Pi IP Address

On the Linux PC, edit the stats sender configuration:

```bash
nano ~/linux-stats/stat_sender.py
```

Update the `PI_IP` variable, then restart:

```bash
systemctl --user restart stats-sender.service
```

## Uninstall

### Raspberry Pi

```bash
# Stop and disable service
sudo systemctl stop stats-display.service
sudo systemctl disable stats-display.service

# Remove files
sudo rm -rf /opt/stats-display
sudo rm -rf ~/stats-display
sudo rm /etc/systemd/system/stats-display.service
sudo rm ~/.config/autostart/stats-display-browser.desktop

# Reload systemd
sudo systemctl daemon-reload
```

### Linux PC

```bash
~/linux-stats/uninstall.sh
```

Or manually:

```bash
# Stop and disable services
systemctl --user stop stats-sender.service fps-logger.service csv-cleanup.service
systemctl --user disable stats-sender.service fps-logger.service csv-cleanup.service

# Remove files
rm -rf ~/linux-stats
rm ~/.config/systemd/user/stats-sender.service
rm ~/.config/systemd/user/fps-logger.service
rm ~/.config/systemd/user/csv-cleanup.service

# Reload systemd
systemctl --user daemon-reload
```

## Compatibility

### Tested Linux Distributions (Gaming PC)
- Bazzite

### Raspberry Pi Models

- **Minimum:** Raspberry Pi 3 / 3+
- **Recommended:** Raspberry Pi 4
- **Best:** Raspberry Pi 5

**Note:** Pi Zero and Pi Zero 2W are not recommended due to performance limitations with the web interface.

### Display Requirements

- Resolution: 480×1920 (portrait) or 1920×480 (landscape capable)
- Touch input support (optional but recommended)

## Support

If you find this project useful, consider buying me a coffee! ☕

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/pyrocac)

## License

This project is licensed under [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](LICENSE).

**This means:**
- ✅ Free for personal use
- ✅ Free for educational use
- ✅ You can modify and share (with credit)
- ❌ Cannot be sold or used commercially
- ❌ Modified versions must use the same license

For commercial use, please contact: https://ko-fi.com/pyrocac 
