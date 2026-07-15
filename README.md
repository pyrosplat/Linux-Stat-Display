# Linux PC Stats Display

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-3%2B-red.svg)](https://www.raspberrypi.org/)
[![Linux](https://img.shields.io/badge/Linux-Compatible-green.svg)](https://en.wikipedia.org/wiki/Linux)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/pyrocac)

Real-time system stats from your Linux gaming PC, displayed on a Raspberry Pi touchscreen. Works on Bazzite, SteamOS, and other Linux distributions.

![Custom Game Art Example](Examples/CustomRidge.png)

## Features

- **8 themes** - Dark/Cyberpunk, Light, Matrix, Retro, Nord, Dracula, Black & White, Steam
- **Portrait or landscape** (480×1920 / 1920×480), instant switching, no reboot needed
- **Custom game art** - JPG, PNG, WEBP, animated GIF
- **Live stats** - CPU/GPU/RAM/VRAM, FPS, temps, frequencies, power draw
- **Steam integration** - game name, player count, artwork
- **Touch settings panel** - themes, orientation, disk info
- **Auto-start on boot**

| Portrait - B&W | Portrait - Light | Portrait - Cyberpunk |
|---|---|---|
| ![](Examples/BlackWhiteTheme.png) | ![](Examples/LightTheme.png) | ![](Examples/CyberPunkTheme.png) |

## What you need

- A Linux gaming PC running Bazzite or SteamOS
- A Raspberry Pi 3 or newer (4/5 recommended)
- A touchscreen: 480×1920 or 1920×480 - [the display used in this project](https://amzn.to/3YiP0RT)
- Both devices on the same network
- Optional: [3D-printed bezel for the Fractal Ridge case](https://www.printables.com/model/1246939-fractal-design-ridge-lcd-case-mod)

## Install

**On the Raspberry Pi:**
```bash
curl -fsSL https://raw.githubusercontent.com/pyrosplat/Linux-Stat-Display/main/RPI/install.sh -o /tmp/rpi-install.sh && sudo bash /tmp/rpi-install.sh
```

**On the Linux gaming PC:**
```bash
curl -fsSL https://raw.githubusercontent.com/pyrosplat/Linux-Stat-Display/main/LinuxPC/install.sh -o /tmp/pc-install.sh && bash /tmp/pc-install.sh
```
You'll be asked for the Pi's IP address and your preferred orientation. That's it - the display comes up automatically.

Everything the Pi side installs lives in one place: `~/stats-display/` (app, rotation scripts, state, game art). An uninstaller is created automatically at `~/uninstall-stats-display.sh`.

## Custom game art

Drop artwork into `~/stats-display/game_art/` on the Pi, named either by Steam AppID (`1091500.jpg`) or game name (`Cyberpunk 2077.jpg`). `.jpg`, `.png`, `.webp`, and animated `.gif` are all supported. 600×900 (Steam library ratio) looks best.

## FPS detection

Add to your Steam launch options:
```
mangohud %command%
```

Adding the launch option alone isn't enough - MangoHud only writes the FPS log file (the CSV this project reads) while logging is actively toggled on, so you also need a way to start/stop it in-game:

- **Keyboard:** the default toggle is `Left Shift + F2`. Press it once after the game launches to start logging (press again to stop).
- **Controller (Steam Input):** bind the same toggle to a controller input so you don't need a keyboard at the couch/desk. In the in-game Steam overlay, go to **Controller Settings → Configure Controller Layout**, add a new binding, and set the action to **Toggle Performance Overlay/Logging** (or bind it manually to the `Left Shift + F2` keyboard combo under **Keyboard/Mouse bindings**). Holding a spare button like **Select/Back** is a common choice so it can't be triggered accidentally.

If FPS is showing as `0` on the stats display, this is almost always the reason - check that logging was actually toggled on for the current play session.

## Uninstall

**Raspberry Pi:**
```bash
sudo ~/uninstall-stats-display.sh
```

**Linux PC:**
```bash
~/linux-stats/uninstall.sh
```

## Troubleshooting

| Problem | Check |
|---|---|
| Display not showing stats | `sudo systemctl status stats-display.service` and `sudo journalctl -u stats-display.service -n 50` |
| FPS showing as 0 | Logging wasn't toggled on for this session - press `Left Shift + F2` (or your bound controller input) in-game. See [FPS detection](#fps-detection). |
| Orientation change fails | `cd ~/stats-display/scripts && ./rotate-landscape.sh` (or `rotate-portrait.sh`) to test manually |
| Touch not working | `xinput list`, then `DISPLAY=:0 xinput map-to-output <device-id> HDMI-1` |
| Stats not arriving from PC | `systemctl --user status stats-sender.service` and `journalctl --user -u stats-sender.service -f`, then `ping <pi-ip>` |
| Browser not launching | `ls ~/.config/openbox/autostart`, or start manually: `firefox-esr --kiosk --private-window http://localhost:5000 &` |

## Changing the Pi's IP later

```bash
nano ~/linux-stats/config.json   # update "pi_ip"
systemctl --user restart stats-sender.service
```

## Compatibility

Tested on Bazzite. Raspberry Pi 3 minimum, 4 recommended, 5 best. Pi Zero/Zero 2W are not recommended (too slow for the web UI).

## License

[CC BY-NC-SA 4.0](LICENSE) - free for personal and educational use, modify and share with credit, no commercial use. For commercial licensing: [ko-fi.com/pyrocac](https://ko-fi.com/pyrocac)

## Support

If this project is useful to you, consider [buying me a coffee](https://ko-fi.com/pyrocac). ☕
