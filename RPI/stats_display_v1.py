#!/usr/bin/env python3
"""
Pi Stats Display Server v2.0 - Optimized & Enhanced
Modern stats display with multiple themes and orientation support
Supports custom game art from local folder
"""

from flask import Flask, request, jsonify, render_template_string, send_from_directory
from datetime import datetime
from pathlib import Path
import socket
import requests
from functools import lru_cache
import time

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
DEFAULT_THEME = "dark"  # Options: dark, light, matrix, retro, nord, dracula, bw, steam
DEFAULT_ORIENTATION = "portrait"  # Options: portrait (480x1920), landscape (1920x480)
CUSTOM_ART_FOLDER = Path.home() / "game_art"  # Folder for custom game artwork
UPDATE_INTERVAL_MS = 500  # Client polling interval in milliseconds

# Steam API Configuration
STEAM_API_BASE = "https://api.steampowered.com"
STEAMDB_API_BASE = "https://steamdb.info/api"
GAME_NAME_CACHE_DURATION = 3600  # Cache game names for 1 hour
PLAYER_COUNT_CACHE_DURATION = 60  # Cache player counts for 1 minute

# Create custom art folder if it doesn't exist
CUSTOM_ART_FOLDER.mkdir(exist_ok=True)

# Game name and player count caches
_game_name_cache = {}  # {appid: (name, timestamp)}
_player_count_cache = {}  # {appid: (data, timestamp)}

# Store latest stats
latest_stats = {
    "cpu": {"usage": 0, "temp": 0.0, "frequency": 0, "power": 0.0, "name": "CPU"},
    "gpu": {"usage": 0, "temp": 0.0, "frequency": 0, "power": 0.0, 
            "vram_used": 0, "vram_total": 0, "name": "GPU"},
    "ram": {"used": 0.0, "total": 0.0, "percent": 0.0},
    "fps": 0,
    "game": "Waiting for data...",
    "appid": None,
    "game_official_name": None,  # Official name from Steam
    "player_count": None,  # Current player count
    "player_peak_24h": None,  # 24h peak
    "timestamp": 0,
    "last_update": None
}

# Supported image formats for custom art
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

# ============================================================
# HTML/CSS/JS TEMPLATE (Minified for efficiency)
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>System Stats</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #000; --bg-secondary: #1a1a1a; --bg-tertiary: #2a2a2a;
            --text-primary: #fff; --text-secondary: #888; --text-muted: #666;
            --accent-cpu: #00ff88; --accent-gpu: #ff0088; --accent-ram: #00d4ff;
            --accent-vram: #ff00ff; --accent-fps: #ffd700;
            --border-color: #2a2a2a; --border-hover: #3a3a3a; --shadow: rgba(0, 0, 0, 0.5);
            --status-online: #00ff88; --status-offline: #ff4444;
        }
        
        body.theme-light {
            --bg-primary: #f5f5f5; --bg-secondary: #fff; --bg-tertiary: #e8e8e8;
            --text-primary: #1a1a1a; --text-secondary: #666; --text-muted: #999;
            --accent-cpu: #0066cc; --accent-gpu: #cc0066; --accent-ram: #00aacc;
            --accent-vram: #cc00cc; --accent-fps: #ff9900;
            --border-color: #ddd; --border-hover: #bbb; --shadow: rgba(0, 0, 0, 0.1);
            --status-online: #00aa00; --status-offline: #cc0000;
        }
        
        body.theme-matrix {
            --bg-primary: #0d0208; --bg-secondary: #1a1313; --bg-tertiary: #252020;
            --text-primary: #00ff41; --text-secondary: #008f11; --text-muted: #006600;
            --accent-cpu: #00ff41; --accent-gpu: #00ff41; --accent-ram: #00ff41;
            --accent-vram: #00ff41; --accent-fps: #00ff41;
            --border-color: #003b00; --border-hover: #005500; --shadow: rgba(0, 255, 65, 0.2);
            --status-online: #00ff41; --status-offline: #ff0000;
        }
        
        body.theme-retro {
            --bg-primary: #2b1b17; --bg-secondary: #3c2f2f; --bg-tertiary: #4a3939;
            --text-primary: #f4d58d; --text-secondary: #bf8b67; --text-muted: #8b6347;
            --accent-cpu: #e63946; --accent-gpu: #f77f00; --accent-ram: #06ffa5;
            --accent-vram: #8338ec; --accent-fps: #ffbe0b;
            --border-color: #8b4513; --border-hover: #a0522d; --shadow: rgba(0, 0, 0, 0.6);
            --status-online: #06ffa5; --status-offline: #e63946;
        }
        
        body.theme-nord {
            --bg-primary: #2e3440; --bg-secondary: #3b4252; --bg-tertiary: #434c5e;
            --text-primary: #eceff4; --text-secondary: #d8dee9; --text-muted: #4c566a;
            --accent-cpu: #88c0d0; --accent-gpu: #bf616a; --accent-ram: #5e81ac;
            --accent-vram: #b48ead; --accent-fps: #ebcb8b;
            --border-color: #4c566a; --border-hover: #5e81ac; --shadow: rgba(0, 0, 0, 0.3);
            --status-online: #a3be8c; --status-offline: #bf616a;
        }
        
        body.theme-dracula {
            --bg-primary: #282a36; --bg-secondary: #44475a; --bg-tertiary: #6272a4;
            --text-primary: #f8f8f2; --text-secondary: #bd93f9; --text-muted: #6272a4;
            --accent-cpu: #50fa7b; --accent-gpu: #ff79c6; --accent-ram: #8be9fd;
            --accent-vram: #bd93f9; --accent-fps: #f1fa8c;
            --border-color: #44475a; --border-hover: #6272a4; --shadow: rgba(0, 0, 0, 0.4);
            --status-online: #50fa7b; --status-offline: #ff5555;
        }
        
        body.theme-bw {
            --bg-primary: #000; --bg-secondary: #1a1a1a; --bg-tertiary: #333;
            --text-primary: #fff; --text-secondary: #aaa; --text-muted: #777;
            --accent-cpu: #fff; --accent-gpu: #ccc; --accent-ram: #bbb;
            --accent-vram: #aaa; --accent-fps: #eee;
            --border-color: #444; --border-hover: #666; --shadow: rgba(255, 255, 255, 0.1);
            --status-online: #fff; --status-offline: #888;
        }
        
        body.theme-steam {
            --bg-primary: #1b2838; --bg-secondary: #171a21; --bg-tertiary: #2a475e;
            --text-primary: #c7d5e0; --text-secondary: #8f98a0; --text-muted: #67707a;
            --accent-cpu: #66c0f4; --accent-gpu: #8bc53f; --accent-ram: #ffcc00;
            --accent-vram: #c13584; --accent-fps: #ff6b00;
            --border-color: #3d4e5f; --border-hover: #66c0f4; --shadow: rgba(0, 0, 0, 0.5);
            --status-online: #8bc53f; --status-offline: #d94b4b;
        }
        
        body {
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', 'Noto Color Emoji', sans-serif;
            overflow: hidden;
            transition: background 0.3s ease, color 0.3s ease;
        }
        
        body.orientation-portrait {
            width: 480px;
            height: 1920px;
        }
        
        body.orientation-portrait .container {
            display: flex;
            flex-direction: column;
            height: 100%;
            padding: 15px 15px 30px 15px; /* Reduced padding for more space */
            gap: 10px;
        }
        
        body.orientation-portrait .game-card {
            flex-shrink: 0;
            padding: 18px;
            margin-bottom: 0;
        }
        
        body.orientation-portrait .game-art-container {
            height: 420px; /* Increased from 380px */
        }
        
        body.orientation-portrait .game-title {
            font-size: 22px; /* Increased from 21px */
            margin-bottom: 12px;
        }
        
        body.orientation-portrait .fps-value {
            font-size: 52px; /* Increased from 48px */
        }
        
        body.orientation-portrait .fps-label {
            font-size: 18px; /* Increased from 16px */
        }
        
        body.orientation-portrait .game-card .fps-card {
            margin-top: 12px;
            margin-bottom: 0;
            padding: 14px;
        }
        
        body.orientation-portrait .stat-card {
            flex: 1;
            margin-bottom: 0;
            padding: 18px;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }
        
        body.orientation-portrait .stat-header {
            margin-bottom: 12px;
        }
        
        body.orientation-portrait .stat-title {
            font-size: 20px; /* Increased from 18px */
        }
        
        body.orientation-portrait .stat-value {
            font-size: 20px; /* Increased from 18px */
        }
        
        body.orientation-portrait .circular-gauge {
            width: 150px; /* Increased from 130px */
            height: 150px;
        }
        
        body.orientation-portrait .gauge-main {
            font-size: 40px; /* Increased from 34px */
        }
        
        body.orientation-portrait .gauge-unit {
            font-size: 16px; /* Increased from 14px */
        }
        
        body.orientation-portrait .gauge-bg {
            stroke-width: 14; /* Increased from 13 */
        }
        
        body.orientation-portrait .gauge-progress {
            stroke-width: 14;
        }
        
        body.orientation-portrait .detail-label {
            font-size: 17px; /* Increased from 15px */
        }
        
        body.orientation-portrait .detail-value {
            font-size: 19px; /* Increased from 17px */
        }
        
        body.orientation-portrait .progress-bar-bg {
            height: 9px; /* Increased from 8px */
        }
        
        body.orientation-portrait .gauge-container {
            gap: 12px;
            justify-content: center;
            align-items: center;
        }
        
        body.orientation-portrait .stat-details {
            gap: 8px;
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        
        body.orientation-portrait .detail-row {
            margin-bottom: 6px;
        }
        
        body.orientation-landscape {
            width: 1920px;
            height: 480px;
        }
        
        body.orientation-landscape .container {
            display: grid;
            grid-template-columns: 400px 1fr 1fr 1fr 1fr; /* Game card wider: 400px from 360px */
            grid-template-rows: 1fr;
            gap: 10px; /* Reduced gap for more card space */
            padding: 10px 10px 10px 16px; /* Reduced padding, keep left bezel space */
            height: 100%;
        }
        
        body.orientation-landscape .game-card {
            grid-column: 1;
            grid-row: 1;
            margin-bottom: 0;
            display: flex;
            flex-direction: column;
            padding: 12px;
        }
        
        body.orientation-landscape .game-art-container {
            flex: 3;
            height: auto;
            margin-bottom: 8px;
        }
        
        body.orientation-landscape .game-title {
            font-size: 18px; /* Increased from 16px */
            margin-bottom: 8px;
        }
        
        body.orientation-landscape .game-card .fps-card {
            margin-bottom: 0;
            padding: 10px 15px;
            border: none;
            background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
            border: 2px solid var(--accent-fps);
        }
        
        body.orientation-landscape .game-card .fps-display {
            flex-direction: row;
            padding: 0;
            gap: 10px;
            justify-content: center;
        }
        
        body.orientation-landscape .game-card .fps-value {
            font-size: 44px; /* Increased from 40px */
        }
        
        body.orientation-landscape .game-card .fps-label {
            font-size: 16px; /* Increased from 14px */
            align-self: center;
        }
        
        body.orientation-landscape .stat-card:nth-of-type(2) { grid-column: 2; grid-row: 1; }
        body.orientation-landscape .stat-card:nth-of-type(3) { grid-column: 3; grid-row: 1; }
        body.orientation-landscape .stat-card:nth-of-type(4) { grid-column: 4; grid-row: 1; }
        body.orientation-landscape .stat-card:nth-of-type(5) { grid-column: 5; grid-row: 1; }
        
        body.orientation-landscape .stat-card {
            margin-bottom: 0;
            padding: 12px; /* Reduced from 15px for more content space */
            display: flex;
            flex-direction: column;
        }
        
        body.orientation-landscape .stat-header { margin-bottom: 12px; }
        body.orientation-landscape .stat-title { font-size: 18px; } /* Increased from 16px */
        body.orientation-landscape .stat-value { font-size: 16px; } /* Increased from 14px */
        
        body.orientation-landscape .gauge-container {
            flex-direction: column;
            gap: 12px;
            flex: 1;
            align-items: center;
            justify-content: center;
            padding-top: 8px;
        }
        
        body.orientation-landscape .circular-gauge { width: 170px; height: 170px; } /* Increased from 150px */
        body.orientation-landscape .gauge-main { font-size: 38px; } /* Increased from 32px */
        body.orientation-landscape .gauge-unit { font-size: 16px; } /* Increased from 14px */
        body.orientation-landscape .gauge-bg { stroke-width: 13; } /* Increased from 12 */
        body.orientation-landscape .gauge-progress { stroke-width: 13; }
        body.orientation-landscape .stat-details { gap: 8px; flex: 1; width: 100%; padding-top: 8px; justify-content: center; }
        body.orientation-landscape .detail-label { font-size: 15px; } /* Increased from 14px */
        body.orientation-landscape .detail-value { font-size: 17px; } /* Increased from 16px */
        body.orientation-landscape .progress-bar-bg { height: 11px; } /* Increased from 10px */
        body.orientation-landscape .status { position: fixed; bottom: 5px; right: 10px; font-size: 11px; padding: 6px 12px; }
        
        .clickable-gauge {
            cursor: pointer;
            transition: transform 0.2s ease;
        }
        
        .clickable-gauge:hover {
            transform: scale(1.05);
        }
        
        .clickable-gauge:active {
            transform: scale(0.98);
        }
        
        /* Disk and network color classes for settings panel */
        
        .disk-color { 
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .disk-stroke { stroke: #ff9500; }
        .disk-bg { background: #ff9500; }
        
        .network-color { 
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .stat-card {
            background: var(--bg-secondary);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 20px;
            border: 1px solid var(--border-color);
            transition: all 0.3s ease;
        }
        
        .stat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .stat-title {
            font-size: 16px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-secondary);
        }
        
        .stat-value {
            font-size: 18px;
            font-weight: 700;
        }
        
        .gauge-container {
            display: flex;
            align-items: center;
            gap: 25px;
        }
        
        .circular-gauge {
            position: relative;
            width: 120px;
            height: 120px;
            flex-shrink: 0;
        }
        
        .gauge-bg {
            fill: none;
            stroke: var(--bg-tertiary);
            stroke-width: 12;
        }
        
        .gauge-progress {
            fill: none;
            stroke-width: 12;
            stroke-linecap: round;
            transition: stroke-dashoffset 0.5s ease, stroke 0.3s ease;
        }
        
        .gauge-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
        }
        
        .gauge-main {
            font-size: 32px;
            font-weight: 700;
            line-height: 1;
        }
        
        .gauge-unit {
            font-size: 14px;
            color: var(--text-secondary);
            font-weight: 500;
        }
        
        .stat-details {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 12px;
            overflow: hidden; /* Prevent content from overflowing card */
            min-height: 0; /* Allow flex shrinking */
        }
        
        .detail-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .detail-row:last-child {
            margin-bottom: 0 !important;
        }
        
        .detail-label {
            font-size: 14px;
            color: var(--text-secondary);
        }
        
        .detail-value {
            font-size: 16px;
            font-weight: 600;
        }
        
        .progress-bar-bg {
            width: 100%;
            height: 8px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }
        
        .progress-bar-fill {
            height: 100%;
            transition: width 0.5s ease, background 0.3s ease;
            border-radius: 4px;
        }
        
        .cpu-color { color: var(--accent-cpu); }
        .cpu-stroke { stroke: var(--accent-cpu); }
        .cpu-bg { background: var(--accent-cpu); }
        
        .gpu-color { color: var(--accent-gpu); }
        .gpu-stroke { stroke: var(--accent-gpu); }
        .gpu-bg { background: var(--accent-gpu); }
        
        .ram-color { color: var(--accent-ram); }
        .ram-stroke { stroke: var(--accent-ram); }
        .ram-bg { background: var(--accent-ram); }
        
        .vram-color { color: var(--accent-vram); }
        .vram-stroke { stroke: var(--accent-vram); }
        .vram-bg { background: var(--accent-vram); }
        
        .fps-card {
            background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
            border: 2px solid var(--accent-fps);
            margin-bottom: 15px;
        }
        
        .fps-display {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 12px;
        }
        
        .fps-value {
            font-size: 48px;
            font-weight: 800;
            color: var(--accent-fps);
            line-height: 1;
            text-shadow: 0 0 20px var(--shadow);
        }
        
        .fps-label {
            font-size: 16px;
            color: var(--accent-fps);
            font-weight: 600;
            letter-spacing: 2px;
        }
        
        .game-card {
            background: var(--bg-secondary);
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid var(--border-color);
            text-align: center;
            position: relative;
            overflow: hidden;
            min-height: 150px;
        }
        
        .game-art-container {
            position: relative;
            width: 100%;
            height: 400px;
            margin-bottom: 15px;
            border-radius: 10px;
            overflow: hidden;
            background: var(--bg-tertiary);
        }
        
        .game-art {
            width: 100%;
            height: 100%;
            object-fit: cover;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .game-art.loaded {
            opacity: 1;
        }
        
        .game-art-placeholder {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 120px;
            color: var(--text-secondary);
            font-family: 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif;
        }
        
        .game-art-placeholder.desktop-mode {
            font-size: 140px;
        }
        
        .game-title {
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 5px;
        }
        
        .game-subtitle {
            font-size: 13px;
            color: var(--text-secondary);
            text-align: center;
            margin-bottom: 8px;
            font-style: italic;
            opacity: 0.8;
        }
        
        .player-stats {
            display: flex;
            justify-content: space-around;
            margin: 8px 0 12px 0;
            padding: 12px;
            background: var(--bg-tertiary);
            border-radius: 8px;
            font-size: 14px;
        }
        
        .player-stat {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
        }
        
        .player-stat-label {
            color: var(--text-secondary);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        
        .player-stat-value {
            color: var(--accent-fps);
            font-weight: 700;
            font-size: 24px;
        }
        
        .status {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 10px 20px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
            color: var(--status-offline);
        }
        
        .status.online {
            color: var(--status-online);
        }
        
        .settings-toggle {
            position: fixed;
            top: 20px;
            right: 20px;
            width: 50px;
            height: 50px;
            background: var(--bg-secondary);
            border: 2px solid var(--border-color);
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            z-index: 1000;
            transition: all 0.3s ease;
        }
        
        .settings-toggle:hover {
            background: var(--bg-tertiary);
            transform: rotate(90deg);
        }
        
        .settings-panel {
            position: fixed;
            background: var(--bg-secondary);
            border: 2px solid var(--border-color);
            transition: all 0.3s ease;
            z-index: 999;
            overflow-y: auto;
        }
        
        /* Portrait: Right side panel (tall) */
        body.orientation-portrait .settings-panel {
            top: 0;
            right: -350px;
            width: 350px;
            height: 100%;
            border-left: 2px solid var(--border-color);
            border-right: none;
            border-top: none;
            border-bottom: none;
            padding: 80px 20px 20px;
        }
        
        body.orientation-portrait .settings-panel.open {
            right: 0;
        }
        
        /* Landscape: Top dropdown (wide) */
        body.orientation-landscape .settings-panel {
            top: -100%;
            left: 0;
            right: 0;
            width: 100%;
            height: auto;
            max-height: 90%;
            border-top: none;
            border-left: none;
            border-right: none;
            border-bottom: 2px solid var(--border-color);
            padding: 60px 20px 20px;
        }
        
        body.orientation-landscape .settings-panel.open {
            top: 0;
        }
        
        /* Landscape: Multi-column layout for sections */
        body.orientation-landscape .settings-panel .settings-content {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            max-width: 1800px;
            margin: 0 auto;
        }
        
        .settings-section {
            margin-bottom: 30px;
        }
        
        .settings-section h3 {
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-secondary);
            margin-bottom: 15px;
        }
        
        /* Clickable theme header */
        .settings-section h3.clickable-header {
            padding: 15px;
            background: var(--bg-tertiary);
            border: 2px solid var(--border-color);
            border-radius: 10px;
            margin-bottom: 15px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-weight: 600;
            user-select: none;
        }
        
        .settings-section h3.clickable-header:hover {
            border-color: var(--border-hover);
            transform: translateX(-3px);
        }
        
        .settings-section h3.clickable-header:active {
            transform: scale(0.98);
        }
        
        .theme-option, .orientation-option {
            padding: 15px;
            background: var(--bg-tertiary);
            border: 2px solid var(--border-color);
            border-radius: 10px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-weight: 600;
        }
        
        .theme-option:hover, .orientation-option:hover {
            transform: translateX(-5px);
            border-color: var(--border-hover);
        }
        
        .theme-option.active, .orientation-option.active {
            border-color: var(--border-hover);
            background: var(--bg-primary);
        }
    </style>
</head>
<body class="orientation-portrait theme-dark">
    <div class="settings-toggle" onclick="toggleSettings()">⚙️</div>
    
    <div class="settings-panel" id="settingsPanel">
        <div class="settings-content">
        <div class="settings-section">
            <h3 class="clickable-header" onclick="toggleNetworkInfo()" style="display: flex; justify-content: space-between; align-items: center;">
                🌐 Network Info
                <span id="network-arrow" style="transition: transform 0.2s;">▼</span>
            </h3>
            <div id="network-info-submenu" style="display: none; margin-top: 10px;">
                <div class="theme-option" style="cursor: default; display: flex; justify-content: space-between;">
                    <span>IP Address:</span>
                    <span id="settings-ip" style="color: var(--accent-cpu); font-weight: 600;">Loading...</span>
                </div>
                <div class="theme-option" style="cursor: default; display: flex; justify-content: space-between;">
                    <span>Link Type:</span>
                    <span id="settings-link-type" style="color: var(--text-primary); font-weight: 600;">-</span>
                </div>
                <div class="theme-option" style="cursor: default; display: flex; justify-content: space-between;">
                    <span>Link Speed:</span>
                    <span id="settings-link-speed" style="color: var(--text-primary); font-weight: 600;">-</span>
                </div>
                <div class="theme-option" style="cursor: default; display: flex; justify-content: space-between;">
                    <span>Download:</span>
                    <span id="settings-download" style="color: var(--accent-ram); font-weight: 600;">0 MB/s</span>
                </div>
                <div class="theme-option" style="cursor: default; display: flex; justify-content: space-between;">
                    <span>Upload:</span>
                    <span id="settings-upload" style="color: var(--accent-vram); font-weight: 600;">0 MB/s</span>
                </div>
                <div class="theme-option" style="cursor: default; display: flex; justify-content: space-between;">
                    <span>Latency:</span>
                    <span id="settings-latency" style="color: var(--text-primary); font-weight: 600;">- ms</span>
                </div>
                <div class="theme-option" style="cursor: default; display: flex; justify-content: space-between;">
                    <span>Total Down:</span>
                    <span id="settings-total-down" style="color: var(--text-secondary); font-weight: 600;">0 GB</span>
                </div>
                <div class="theme-option" style="cursor: default; display: flex; justify-content: space-between;">
                    <span>Total Up:</span>
                    <span id="settings-total-up" style="color: var(--text-secondary); font-weight: 600;">0 GB</span>
                </div>
            </div>
        </div>
        
        <div class="settings-section">
            <h3 class="clickable-header" onclick="toggleDiskInfo()" style="display: flex; justify-content: space-between; align-items: center;">
                💾 Disk Info
                <span id="disk-arrow" style="transition: transform 0.2s;">▼</span>
            </h3>
            <div id="disk-info-submenu" style="display: none; margin-top: 10px;">
                <div id="settings-disk-list">
                    <div class="theme-option" style="cursor: default; color: var(--text-secondary);">No disk data yet...</div>
                </div>
            </div>
        </div>
        
        <div class="settings-section">
            <h3 class="clickable-header" onclick="toggleThemeSubmenu()" style="display: flex; justify-content: space-between; align-items: center;">
                Theme Options
                <span id="theme-arrow" style="transition: transform 0.2s;">▼</span>
            </h3>
            <div id="theme-submenu" style="display: none; margin-top: 10px;">
                <div class="theme-option active" data-theme="dark" onclick="selectTheme('dark')">🌃 Dark / Cyberpunk</div>
                <div class="theme-option" data-theme="light" onclick="selectTheme('light')">☀️ Light</div>
                <div class="theme-option" data-theme="matrix" onclick="selectTheme('matrix')">🟩 Matrix</div>
                <div class="theme-option" data-theme="retro" onclick="selectTheme('retro')">🎮 Retro</div>
                <div class="theme-option" data-theme="nord" onclick="selectTheme('nord')">❄️ Nord</div>
                <div class="theme-option" data-theme="dracula" onclick="selectTheme('dracula')">🧛 Dracula</div>
                <div class="theme-option" data-theme="bw" onclick="selectTheme('bw')">⬛ Black & White</div>
                <div class="theme-option" data-theme="steam" onclick="selectTheme('steam')">🎮 Steam</div>
            </div>
        </div>
        
        <div class="settings-section">
            <h3>Display Rotation</h3>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 10px;">📱 Rotates display and touch input instantly</div>
            <div class="orientation-option" data-physical="portrait" onclick="changePhysicalOrientation('portrait')">
                📱 Portrait Mode
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 5px;">480×1920 vertical layout</div>
            </div>
            <div class="orientation-option" data-physical="landscape" onclick="changePhysicalOrientation('landscape')">
                🖥️ Landscape Mode
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 5px;">1920×480 horizontal layout</div>
            </div>
        </div>
        
        <div class="settings-section">
            <h3>Gauge Display</h3>
            <div class="orientation-option active" data-gauge="usage" onclick="setGaugeMode('usage')">📊 Show Usage %</div>
            <div class="orientation-option" data-gauge="temp" onclick="setGaugeMode('temp')">🌡️ Show Temperature</div>
        </div>
        </div> <!-- Close settings-content -->
    </div> <!-- Close settings-panel -->
    
    <div class="container">
        <div class="game-card">
            <div class="game-art-container">
                <img id="game-art" class="game-art" src="" alt="Game Art">
                <div id="game-art-placeholder" class="game-art-placeholder">🎮</div>
            </div>
            <div class="game-title" id="game">{{ stats.game }}</div>
            <div class="game-subtitle" id="game-subtitle" style="display: none;">Detected: <span id="detected-name"></span></div>
            <div class="player-stats" id="player-stats" style="display: none;">
                <div class="player-stat">
                    <span class="player-stat-label">Playing Now</span>
                    <span class="player-stat-value" id="current-players">-</span>
                </div>
                <div class="player-stat">
                    <span class="player-stat-label">24h Peak</span>
                    <span class="player-stat-value" id="peak-players">-</span>
                </div>
            </div>
            <div class="stat-card fps-card">
                <div class="fps-display">
                    <div class="fps-value" id="fps-value">{{ stats.fps }}</div>
                    <div class="fps-label">FPS</div>
                </div>
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-header">
                <span class="stat-title gpu-color">GPU</span>
                <span class="stat-value gpu-color" id="gpu-model">{{ stats.gpu.name }}</span>
            </div>
            <div class="gauge-container">
                <div class="circular-gauge clickable-gauge" onclick="toggleGaugeMode('gpu')" title="Click to toggle between Usage and Temperature">
                    <svg viewBox="0 0 120 120">
                        <circle class="gauge-bg" cx="60" cy="60" r="52"/>
                        <circle class="gauge-progress gpu-stroke" cx="60" cy="60" r="52"
                                id="gpu-circle" stroke-dasharray="326.7" stroke-dashoffset="326.7"
                                transform="rotate(-90 60 60)"/>
                    </svg>
                    <div class="gauge-text">
                        <div class="gauge-main gpu-color" id="gpu-gauge-value">{{ stats.gpu.usage }}%</div>
                        <div class="gauge-unit" id="gpu-gauge-label">Usage</div>
                    </div>
                </div>
                <div class="stat-details">
                    <div class="detail-row" id="gpu-detail-usage">
                        <span class="detail-label">Usage</span>
                        <span class="detail-value gpu-color"><span id="gpu-usage-text">{{ stats.gpu.usage }}</span>%</span>
                    </div>
                    <div class="detail-row" id="gpu-detail-temp" style="display: none;">
                        <span class="detail-label">Temperature</span>
                        <span class="detail-value gpu-color"><span id="gpu-temp">{{ stats.gpu.temp }}</span>°C</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Frequency</span>
                        <span class="detail-value"><span id="gpu-freq">{{ stats.gpu.frequency }}</span> MHz</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Power</span>
                        <span class="detail-value"><span id="gpu-power">{{ stats.gpu.power }}</span> W</span>
                    </div>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill gpu-bg" id="gpu-bar" style="width: {{ stats.gpu.usage }}%"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-header">
                <span class="stat-title cpu-color">CPU</span>
                <span class="stat-value cpu-color" id="cpu-model">{{ stats.cpu.name }}</span>
            </div>
            <div class="gauge-container">
                <div class="circular-gauge clickable-gauge" onclick="toggleGaugeMode('cpu')" title="Click to toggle between Usage and Temperature">
                    <svg viewBox="0 0 120 120">
                        <circle class="gauge-bg" cx="60" cy="60" r="52"/>
                        <circle class="gauge-progress cpu-stroke" cx="60" cy="60" r="52"
                                id="cpu-circle" stroke-dasharray="326.7" stroke-dashoffset="326.7"
                                transform="rotate(-90 60 60)"/>
                    </svg>
                    <div class="gauge-text">
                        <div class="gauge-main cpu-color" id="cpu-gauge-value">{{ stats.cpu.usage }}%</div>
                        <div class="gauge-unit" id="cpu-gauge-label">Usage</div>
                    </div>
                </div>
                <div class="stat-details">
                    <div class="detail-row" id="cpu-detail-usage">
                        <span class="detail-label">Usage</span>
                        <span class="detail-value cpu-color"><span id="cpu-usage-text">{{ stats.cpu.usage }}</span>%</span>
                    </div>
                    <div class="detail-row" id="cpu-detail-temp" style="display: none;">
                        <span class="detail-label">Temperature</span>
                        <span class="detail-value cpu-color"><span id="cpu-temp">{{ stats.cpu.temp }}</span>°C</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Frequency</span>
                        <span class="detail-value"><span id="cpu-freq">{{ stats.cpu.frequency }}</span> MHz</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Power</span>
                        <span class="detail-value"><span id="cpu-power">{{ stats.cpu.power }}</span> W</span>
                    </div>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill cpu-bg" id="cpu-bar" style="width: {{ stats.cpu.usage }}%"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-header">
                <span class="stat-title ram-color">RAM</span>
                <span class="stat-value ram-color" id="ram-info" style="font-size: 12px;"></span>
            </div>
            <div class="gauge-container">
                <div class="circular-gauge">
                    <svg viewBox="0 0 120 120">
                        <circle class="gauge-bg" cx="60" cy="60" r="52"/>
                        <circle class="gauge-progress ram-stroke" cx="60" cy="60" r="52"
                                id="ram-circle" stroke-dasharray="326.7" stroke-dashoffset="326.7"
                                transform="rotate(-90 60 60)"/>
                    </svg>
                    <div class="gauge-text">
                        <div class="gauge-main ram-color" id="ram-percent-gauge">{{ stats.ram.percent }}%</div>
                    </div>
                </div>
                <div class="stat-details">
                    <div class="detail-row">
                        <span class="detail-label">Used</span>
                        <span class="detail-value ram-color"><span id="ram-used">{{ stats.ram.used }}</span> GB</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Free</span>
                        <span class="detail-value"><span id="ram-free">{{ stats.ram.total - stats.ram.used }}</span> GB</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Total</span>
                        <span class="detail-value"><span id="ram-total">{{ stats.ram.total }}</span> GB</span>
                    </div>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill ram-bg" id="ram-bar" style="width: {{ stats.ram.percent }}%"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-header">
                <span class="stat-title vram-color">GPU VRAM</span>
            </div>
            <div class="gauge-container">
                <div class="circular-gauge">
                    <svg viewBox="0 0 120 120">
                        <circle class="gauge-bg" cx="60" cy="60" r="52"/>
                        <circle class="gauge-progress vram-stroke" cx="60" cy="60" r="52"
                                id="vram-circle" stroke-dasharray="326.7" stroke-dashoffset="326.7"
                                transform="rotate(-90 60 60)"/>
                    </svg>
                    <div class="gauge-text">
                        <div class="gauge-main vram-color" id="vram-percent-gauge">0%</div>
                    </div>
                </div>
                <div class="stat-details">
                    <div class="detail-row">
                        <span class="detail-label">Used</span>
                        <span class="detail-value vram-color"><span id="vram-used">0</span> GB</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Free</span>
                        <span class="detail-value"><span id="vram-free">0</span> GB</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Total</span>
                        <span class="detail-value"><span id="vram-total">0</span> GB</span>
                    </div>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill vram-bg" id="vram-bar" style="width: 0%"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="status online" id="status">● <span id="last-update">{{ stats.last_update or 'Never' }}</span></div>
    </div>
    
    <script>
        const CIRCUMFERENCE = 326.7;
        const UPDATE_INTERVAL = {{ update_interval }};
        
        // Load preferences
        const savedTheme = localStorage.getItem('theme') || '{{ default_theme }}';
        const savedOrientation = localStorage.getItem('orientation') || '{{ default_orientation }}';
        const savedGaugeMode = localStorage.getItem('gaugeMode') || 'usage';
        
        // Track current values for each gauge
        let cpuCurrentUsage = 0;
        let cpuCurrentTemp = 0;
        let gpuCurrentUsage = 0;
        let gpuCurrentTemp = 0;
        
        // Apply preferences
        document.body.className = `orientation-${savedOrientation} theme-${savedTheme}`;
        document.querySelector(`[data-theme="${savedTheme}"]`)?.classList.add('active');
        document.querySelector(`[data-physical="${savedOrientation}"]`)?.classList.add('active');
        document.querySelector(`[data-gauge="${savedGaugeMode}"]`)?.classList.add('active');
        
        function toggleSettings() {
            document.getElementById('settingsPanel').classList.toggle('open');
        }
        
        function toggleThemeSubmenu() {
            const submenu = document.getElementById('theme-submenu');
            const arrow = document.getElementById('theme-arrow');
            
            if (submenu.style.display === 'none' || submenu.style.display === '') {
                submenu.style.display = 'block';
                arrow.style.transform = 'rotate(180deg)';
            } else {
                submenu.style.display = 'none';
                arrow.style.transform = 'rotate(0deg)';
            }
        }
        
        function toggleNetworkInfo() {
            const submenu = document.getElementById('network-info-submenu');
            const arrow = document.getElementById('network-arrow');
            
            if (submenu.style.display === 'none' || submenu.style.display === '') {
                submenu.style.display = 'block';
                arrow.style.transform = 'rotate(180deg)';
            } else {
                submenu.style.display = 'none';
                arrow.style.transform = 'rotate(0deg)';
            }
        }
        
        function toggleDiskInfo() {
            const submenu = document.getElementById('disk-info-submenu');
            const arrow = document.getElementById('disk-arrow');
            
            if (submenu.style.display === 'none' || submenu.style.display === '') {
                submenu.style.display = 'block';
                arrow.style.transform = 'rotate(180deg)';
            } else {
                submenu.style.display = 'none';
                arrow.style.transform = 'rotate(0deg)';
            }
        }
        
        function selectTheme(theme) {
            // Change the theme
            changeTheme(theme);
            
            // Close the submenu after selection
            document.getElementById('theme-submenu').style.display = 'none';
            document.getElementById('theme-arrow').style.transform = 'rotate(0deg)';
        }
        
        function changeTheme(theme) {
            document.querySelectorAll('.theme-option').forEach(opt => opt.classList.remove('active'));
            document.querySelector(`[data-theme="${theme}"]`).classList.add('active');
            
            const orientation = document.body.className.split(' ')[0];
            document.body.className = `${orientation} theme-${theme}`;
            localStorage.setItem('theme', theme);
        }
        
        function changeOrientation(orientation) {
            // Update physical rotation buttons (which now control both physical and software orientation)
            document.querySelectorAll('[data-physical]').forEach(opt => opt.classList.remove('active'));
            document.querySelector(`[data-physical="${orientation}"]`)?.classList.add('active');
            
            const theme = document.body.className.split(' ')[1];
            document.body.className = `orientation-${orientation} ${theme}`;
            localStorage.setItem('orientation', orientation);
        }
        
        function setGaugeMode(mode) {
            document.querySelectorAll('[data-gauge]').forEach(opt => opt.classList.remove('active'));
            document.querySelector(`[data-gauge="${mode}"]`)?.classList.add('active');
            localStorage.setItem('gaugeMode', mode);
            
            // Update both CPU and GPU gauges
            if (mode === 'usage') {
                // Gauge shows Usage, detail shows Temperature
                updateGaugeDisplay('cpu', cpuCurrentUsage, '%', 'Usage');
                updateGaugeDisplay('gpu', gpuCurrentUsage, '%', 'Usage');
                showDetailRow('cpu-detail-temp', 'cpu-detail-usage');
                showDetailRow('gpu-detail-temp', 'gpu-detail-usage');
            } else {
                // Gauge shows Temperature, detail shows Usage
                updateGaugeDisplay('cpu', cpuCurrentTemp, '°C', 'Temp');
                updateGaugeDisplay('gpu', gpuCurrentTemp, '°C', 'Temp');
                showDetailRow('cpu-detail-usage', 'cpu-detail-temp');
                showDetailRow('gpu-detail-usage', 'gpu-detail-temp');
            }
        }
        
        function toggleGaugeMode(type) {
            const currentMode = localStorage.getItem('gaugeMode') || 'usage';
            const newMode = currentMode === 'usage' ? 'temp' : 'usage';
            
            // Update localStorage and settings panel
            localStorage.setItem('gaugeMode', newMode);
            document.querySelectorAll('[data-gauge]').forEach(opt => opt.classList.remove('active'));
            document.querySelector(`[data-gauge="${newMode}"]`)?.classList.add('active');
            
            // Update BOTH gauges together
            if (newMode === 'usage') {
                // Gauge shows Usage, detail shows Temperature
                updateGaugeDisplay('cpu', cpuCurrentUsage, '%', 'Usage');
                updateGaugeDisplay('gpu', gpuCurrentUsage, '%', 'Usage');
                showDetailRow('cpu-detail-temp', 'cpu-detail-usage');
                showDetailRow('gpu-detail-temp', 'gpu-detail-usage');
            } else {
                // Gauge shows Temperature, detail shows Usage
                updateGaugeDisplay('cpu', cpuCurrentTemp, '°C', 'Temp');
                updateGaugeDisplay('gpu', gpuCurrentTemp, '°C', 'Temp');
                showDetailRow('cpu-detail-usage', 'cpu-detail-temp');
                showDetailRow('gpu-detail-usage', 'gpu-detail-temp');
            }
        }
        
        function updateGaugeDisplay(type, value, unit, label) {
            const gaugeValue = document.getElementById(`${type}-gauge-value`);
            const gaugeLabel = document.getElementById(`${type}-gauge-label`);
            const circle = document.getElementById(`${type}-circle`);
            
            // For temperature, convert to percentage (assuming 0-100°C range)
            const percentage = unit === '°C' ? Math.min(value, 100) : value;
            
            gaugeValue.textContent = value + unit;
            gaugeLabel.textContent = label;
            
            // Update circular gauge
            const offset = CIRCUMFERENCE - (percentage / 100 * CIRCUMFERENCE);
            circle.style.strokeDashoffset = offset;
        }
        
        function showDetailRow(showId, hideId) {
            document.getElementById(showId).style.display = 'flex';
            document.getElementById(hideId).style.display = 'none';
        }
        
        async function changePhysicalOrientation(orientation) {
            try {
                // Update orientation
                const response = await fetch('/api/settings/orientation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ orientation })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // Update the display layout to match immediately
                    changeOrientation(orientation);
                    
                    // Close settings panel
                    document.getElementById('settingsPanel').classList.remove('open');
                } else {
                    alert('Failed to change orientation: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
        
        // Load IP address for settings panel
        async function loadNetworkInfo() {
            try {
                const response = await fetch('/api/settings/orientation');
                const data = await response.json();
                // Extract IP from window location as fallback
                const ip = window.location.hostname;
                document.getElementById('settings-ip').textContent = ip;
            } catch (error) {
                document.getElementById('settings-ip').textContent = window.location.hostname;
            }
        }
        
        // Update storage data from Bazzite stats
        function updateDiskSettings(disks) {
            const diskList = document.getElementById('settings-disk-list');
            
            if (disks && disks.length > 0) {
                diskList.innerHTML = disks.map(disk => `
                    <div class="theme-option" style="cursor: default; margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <span style="font-weight: 600;">${disk.name.toUpperCase()}</span>
                            <span style="color: var(--accent-vram); font-weight: 600;">${disk.percent}%</span>
                        </div>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">
                            ${disk.used_gb} GB / ${disk.total_gb} GB used
                        </div>
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill" style="width: ${disk.percent}%; background: var(--accent-vram);"></div>
                        </div>
                    </div>
                `).join('');
            } else {
                diskList.innerHTML = '<div class="theme-option" style="cursor: default; color: var(--text-secondary);">No disk data yet...</div>';
            }
        }
        
        // Update network settings panel
        function updateNetworkSettings(network) {
            if (network) {
                document.getElementById('settings-download').textContent = (network.download_speed || 0).toFixed(2) + ' MB/s';
                document.getElementById('settings-upload').textContent = (network.upload_speed || 0).toFixed(2) + ' MB/s';
                document.getElementById('settings-latency').textContent = network.latency_ms ? network.latency_ms.toFixed(1) + ' ms' : '- ms';
                document.getElementById('settings-total-down').textContent = (network.total_download_gb || 0).toFixed(2) + ' GB';
                document.getElementById('settings-total-up').textContent = (network.total_upload_gb || 0).toFixed(2) + ' GB';
                
                // Update link type and speed
                const linkType = network.link_type || 'Unknown';
                document.getElementById('settings-link-type').textContent = linkType;
                
                if (network.link_speed_mbps) {
                    if (network.link_type === 'WiFi' && network.wifi_tx_speed && network.wifi_rx_speed) {
                        document.getElementById('settings-link-speed').textContent = `↓${network.wifi_rx_speed} / ↑${network.wifi_tx_speed} Mbps`;
                    } else if (network.link_speed_mbps >= 10000) {
                        document.getElementById('settings-link-speed').textContent = '10 Gbps';
                    } else if (network.link_speed_mbps >= 5000) {
                        document.getElementById('settings-link-speed').textContent = '5 Gbps';
                    } else if (network.link_speed_mbps >= 2500) {
                        document.getElementById('settings-link-speed').textContent = '2.5 Gbps';
                    } else if (network.link_speed_mbps >= 1000) {
                        document.getElementById('settings-link-speed').textContent = '1 Gbps';
                    } else if (network.link_speed_mbps >= 100) {
                        document.getElementById('settings-link-speed').textContent = '100 Mbps';
                    } else {
                        document.getElementById('settings-link-speed').textContent = network.link_speed_mbps + ' Mbps';
                    }
                } else {
                    document.getElementById('settings-link-speed').textContent = '-';
                }
            }
        }
        
        // Legacy functions (no longer used - kept for compatibility)
        async function updateStorage() {
            try {
                const response = await fetch('/api/storage');
                const data = await response.json();
                const diskList = document.getElementById('disk-list');
                
                if (data.disks && data.disks.length > 0) {
                    diskList.innerHTML = data.disks.map(disk => `
                        <div style="margin-bottom: 15px;">
                            <div class="detail-row" style="margin-bottom: 5px;">
                                <span class="detail-label">${disk.mountpoint}</span>
                                <span class="detail-value disk-color">${disk.percent}%</span>
                            </div>
                            <div style="font-size: 11px; color: #888; margin-bottom: 5px;">
                                ${disk.used_gb} GB / ${disk.total_gb} GB (${disk.free_gb} GB free)
                            </div>
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill disk-bg" style="width: ${disk.percent}%"></div>
                            </div>
                        </div>
                    `).join('');
                } else {
                    diskList.innerHTML = '<div class="detail-label">No disks found</div>';
                }
            } catch (error) {
                console.error('Failed to fetch storage:', error);
            }
        }
        
        // Track network stats for speed calculation
        let lastNetworkData = null;
        let lastNetworkTime = Date.now();
        
        // Update network data
        async function updateNetwork() {
            try {
                const response = await fetch('/api/network');
                const data = await response.json();
                const currentTime = Date.now();
                
                if (lastNetworkData) {
                    const timeDiff = (currentTime - lastNetworkTime) / 1000; // seconds
                    const downloadSpeed = ((data.bytes_recv - lastNetworkData.bytes_recv) / timeDiff / 1024 / 1024).toFixed(2);
                    const uploadSpeed = ((data.bytes_sent - lastNetworkData.bytes_sent) / timeDiff / 1024 / 1024).toFixed(2);
                    
                    document.getElementById('net-download').textContent = downloadSpeed;
                    document.getElementById('net-upload').textContent = uploadSpeed;
                    document.getElementById('net-latency').textContent = data.latency_ms ? data.latency_ms.toFixed(1) : '-';
                    document.getElementById('net-total-down').textContent = (data.bytes_recv / 1024 / 1024 / 1024).toFixed(2);
                    document.getElementById('net-total-up').textContent = (data.bytes_sent / 1024 / 1024 / 1024).toFixed(2);
                }
                
                lastNetworkData = data;
                lastNetworkTime = currentTime;
            } catch (error) {
                console.error('Failed to fetch network:', error);
            }
        }
        
        function updateGauge(circleId, percentage) {
            const circle = document.getElementById(circleId);
            const offset = CIRCUMFERENCE - (percentage / 100 * CIRCUMFERENCE);
            circle.style.strokeDashoffset = offset;
        }
        
        function formatNumber(num) {
            if (num === null || num === undefined) return '-';
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1) + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'K';
            }
            return num.toString();
        }
        
        async function updateGameArt(appid, gameTitle) {
            const gameArt = document.getElementById('game-art');
            const placeholder = document.getElementById('game-art-placeholder');
            
            // Valid Steam AppID check (needed for both custom and Steam art)
            const isValidAppId = appid && appid !== 'null' && appid !== null && 
                                 !isNaN(appid) && appid > 0 && appid < 100000000;
            
            // Priority 1: Check custom art by AppID (most reliable)
            if (isValidAppId) {
                try {
                    const response = await fetch(`/api/custom_art_by_appid/${appid}`);
                    const data = await response.json();
                    
                    if (data.exists) {
                        // Don't reload if already showing same image (prevents GIF restart)
                        if (gameArt.src !== window.location.origin + data.url) {
                            gameArt.src = data.url;
                            gameArt.classList.add('loaded');
                            placeholder.style.display = 'none';
                        }
                        return;
                    }
                } catch (e) {
                    // Continue to next option
                }
            }
            
            // Priority 2: Check custom art by game name
            if (gameTitle && gameTitle !== 'Desktop' && gameTitle !== 'Waiting for data...') {
                try {
                    const response = await fetch(`/api/custom_art/${encodeURIComponent(gameTitle)}`);
                    const data = await response.json();
                    
                    if (data.exists) {
                        // Don't reload if already showing same image (prevents GIF restart)
                        if (gameArt.src !== window.location.origin + data.url) {
                            gameArt.src = data.url;
                            gameArt.classList.add('loaded');
                            placeholder.style.display = 'none';
                        }
                        return;
                    }
                } catch (e) {
                    // Continue to Steam art
                }
            }
            
            // Priority 3: Fetch from Steam if AppID is valid
            
            if (isValidAppId) {
                const artUrl = `https://steamcdn-a.akamaihd.net/steam/apps/${appid}/library_600x900.jpg`;
                const testImg = new Image();
                let imageLoaded = false;
                
                const timeout = setTimeout(() => {
                    if (!imageLoaded) {
                        gameArt.classList.remove('loaded');
                        placeholder.style.display = 'block';
                        updatePlaceholderIcon(gameTitle);
                    }
                }, 2000);
                
                testImg.onload = function() {
                    imageLoaded = true;
                    clearTimeout(timeout);
                    gameArt.src = artUrl;
                    gameArt.classList.add('loaded');
                    placeholder.style.display = 'none';
                };
                
                testImg.onerror = function() {
                    imageLoaded = true;
                    clearTimeout(timeout);
                    
                    // Try header fallback
                    const headerUrl = `https://steamcdn-a.akamaihd.net/steam/apps/${appid}/header.jpg`;
                    const headerImg = new Image();
                    
                    const headerTimeout = setTimeout(() => {
                        gameArt.classList.remove('loaded');
                        placeholder.style.display = 'block';
                        updatePlaceholderIcon(gameTitle);
                    }, 1000);
                    
                    headerImg.onload = function() {
                        clearTimeout(headerTimeout);
                        gameArt.src = headerUrl;
                        gameArt.classList.add('loaded');
                        placeholder.style.display = 'none';
                    };
                    
                    headerImg.onerror = function() {
                        clearTimeout(headerTimeout);
                        gameArt.classList.remove('loaded');
                        placeholder.style.display = 'block';
                        updatePlaceholderIcon(gameTitle);
                    };
                    
                    headerImg.src = headerUrl;
                };
                
                testImg.src = artUrl;
            } else {
                gameArt.classList.remove('loaded');
                placeholder.style.display = 'block';
                updatePlaceholderIcon(gameTitle);
            }
        }
        
        function updatePlaceholderIcon(gameTitle) {
            const placeholder = document.getElementById('game-art-placeholder');
            const titleLower = (gameTitle || '').toLowerCase();
            
            if (titleLower.includes('desktop')) {
                placeholder.textContent = '🖥️';
                placeholder.classList.add('desktop-mode');
            } else if (titleLower.includes('steamos')) {
                placeholder.textContent = '🎮';
                placeholder.classList.add('desktop-mode');
            } else {
                placeholder.textContent = '🎮';
                placeholder.classList.remove('desktop-mode');
            }
        }
        
        // Auto-refresh
        setInterval(async function() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                
                // Game & FPS
                // Use official name if available, otherwise use detected name
                const displayName = stats.game_official_name || stats.game;
                document.getElementById('game').textContent = displayName;
                
                // Hide subtitle completely when we have an official name from Steam API
                // Only show detected name if API didn't return an official name
                const subtitle = document.getElementById('game-subtitle');
                subtitle.style.display = 'none';  // Always hide - we don't need to show detected name
                
                // Update player counts if available (always visible to prevent layout shift)
                const playerStats = document.getElementById('player-stats');
                const currentPlayers = document.getElementById('current-players');
                const peakPlayers = document.getElementById('peak-players');
                
                // Always show player stats section to prevent layout shifts
                playerStats.style.display = 'flex';
                
                if (stats.player_count !== null && stats.player_count !== undefined) {
                    currentPlayers.textContent = formatNumber(stats.player_count);
                    peakPlayers.textContent = stats.player_peak_24h !== null && stats.player_peak_24h !== undefined 
                        ? formatNumber(stats.player_peak_24h) : '-';
                } else {
                    // Show placeholder when data not available
                    currentPlayers.textContent = '-';
                    peakPlayers.textContent = '-';
                }
                
                document.getElementById('fps-value').textContent = stats.fps;
                await updateGameArt(stats.appid, displayName);
                
                // Store current values
                cpuCurrentUsage = stats.cpu.usage;
                cpuCurrentTemp = parseFloat(stats.cpu.temp);
                gpuCurrentUsage = stats.gpu.usage;
                gpuCurrentTemp = parseFloat(stats.gpu.temp);
                
                // Get current gauge mode
                const gaugeMode = localStorage.getItem('gaugeMode') || 'usage';
                
                // CPU
                document.getElementById('cpu-model').textContent = stats.cpu.name;
                document.getElementById('cpu-usage-text').textContent = stats.cpu.usage;
                document.getElementById('cpu-temp').textContent = stats.cpu.temp;
                document.getElementById('cpu-freq').textContent = stats.cpu.frequency;
                document.getElementById('cpu-power').textContent = stats.cpu.power;
                document.getElementById('cpu-bar').style.width = stats.cpu.usage + '%';
                
                // Update CPU gauge based on mode
                if (gaugeMode === 'temp') {
                    updateGaugeDisplay('cpu', cpuCurrentTemp, '°C', 'Temp');
                } else {
                    updateGaugeDisplay('cpu', cpuCurrentUsage, '%', 'Usage');
                }
                
                // GPU
                document.getElementById('gpu-model').textContent = stats.gpu.name;
                document.getElementById('gpu-usage-text').textContent = stats.gpu.usage;
                document.getElementById('gpu-temp').textContent = stats.gpu.temp;
                document.getElementById('gpu-freq').textContent = stats.gpu.frequency;
                document.getElementById('gpu-power').textContent = stats.gpu.power;
                document.getElementById('gpu-bar').style.width = stats.gpu.usage + '%';
                
                // Update GPU gauge based on mode
                if (gaugeMode === 'temp') {
                    updateGaugeDisplay('gpu', gpuCurrentTemp, '°C', 'Temp');
                } else {
                    updateGaugeDisplay('gpu', gpuCurrentUsage, '%', 'Usage');
                }
                
                // RAM
                updateGauge('ram-circle', stats.ram.percent);
                const ramFree = (stats.ram.total - stats.ram.used).toFixed(1);
                document.getElementById('ram-used').textContent = stats.ram.used;
                document.getElementById('ram-free').textContent = ramFree;
                document.getElementById('ram-total').textContent = stats.ram.total;
                document.getElementById('ram-percent-gauge').textContent = stats.ram.percent + '%';
                document.getElementById('ram-bar').style.width = stats.ram.percent + '%';
                
                // RAM info (type and speed)
                if (stats.ram.type && stats.ram.speed) {
                    const ramInfo = stats.ram.type !== 'Unknown' ? `${stats.ram.type} ${stats.ram.speed}` : '';
                    document.getElementById('ram-info').textContent = ramInfo;
                }
                
                // VRAM
                const vramUsedGB = (stats.gpu.vram_used / 1024).toFixed(1);
                const vramTotalGB = (stats.gpu.vram_total / 1024).toFixed(1);
                const vramFreeGB = ((stats.gpu.vram_total - stats.gpu.vram_used) / 1024).toFixed(1);
                const vramPercent = stats.gpu.vram_total > 0 
                    ? ((stats.gpu.vram_used / stats.gpu.vram_total) * 100).toFixed(1) : 0;
                
                updateGauge('vram-circle', vramPercent);
                document.getElementById('vram-used').textContent = vramUsedGB;
                document.getElementById('vram-free').textContent = vramFreeGB;
                document.getElementById('vram-total').textContent = vramTotalGB;
                document.getElementById('vram-percent-gauge').textContent = vramPercent + '%';
                document.getElementById('vram-bar').style.width = vramPercent + '%';
                
                // Status
                document.getElementById('last-update').textContent = stats.last_update || 'Never';
                document.getElementById('status').classList.add('online');
                
                // Update settings panel with network/disk data
                if (stats.network) {
                    updateNetworkSettings(stats.network);
                }
                if (stats.disks) {
                    updateDiskSettings(stats.disks);
                }
                
            } catch (error) {
                document.getElementById('status').classList.remove('online');
                document.getElementById('status').textContent = '● OFFLINE';
            }
        }, UPDATE_INTERVAL);
        
        // Initialize on page load
        window.addEventListener('DOMContentLoaded', function() {
            // Load network info
            loadNetworkInfo();
            
            // Initialize gauge mode display
            const gaugeMode = localStorage.getItem('gaugeMode') || 'usage';
            if (gaugeMode === 'temp') {
                // Gauge shows Temp, detail shows Usage
                showDetailRow('cpu-detail-usage', 'cpu-detail-temp');
                showDetailRow('gpu-detail-usage', 'gpu-detail-temp');
            } else {
                // Gauge shows Usage, detail shows Temp
                showDetailRow('cpu-detail-temp', 'cpu-detail-usage');
                showDetailRow('gpu-detail-temp', 'gpu-detail-usage');
            }
        });
    </script>
</body>
</html>
"""

# ============================================================
# STEAM API FUNCTIONS
# ============================================================

def get_game_name_from_steam(appid):
    """Fetch official game name from Steam Store API with caching"""
    global _game_name_cache
    
    if not appid or appid == 'null' or appid is None:
        return None
    
    try:
        appid = str(appid)
        current_time = time.time()
        
        # Check cache first
        if appid in _game_name_cache:
            cached_name, cache_time = _game_name_cache[appid]
            if current_time - cache_time < GAME_NAME_CACHE_DURATION:
                return cached_name
        
        # Fetch from Steam API
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if appid in data and data[appid].get('success'):
                game_name = data[appid]['data'].get('name')
                if game_name:
                    # Cache the result
                    _game_name_cache[appid] = (game_name, current_time)
                    return game_name
        
        return None
    except Exception as e:
        print(f"Warning: Failed to fetch game name for AppID {appid}: {e}")
        return None


def get_player_counts(appid):
    """Fetch current player count from Steam API and 24h peak from SteamCharts with caching"""
    global _player_count_cache
    
    if not appid or appid == 'null' or appid is None:
        return None, None
    
    try:
        appid = str(appid)
        current_time = time.time()
        
        # Check cache first
        if appid in _player_count_cache:
            cached_data, cache_time = _player_count_cache[appid]
            if current_time - cache_time < PLAYER_COUNT_CACHE_DURATION:
                return cached_data.get('current'), cached_data.get('peak_24h')
        
        # Fetch current players from Steam API
        url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}"
        response = requests.get(url, timeout=5)
        
        current_players = None
        peak_24h = None
        
        if response.status_code == 200:
            data = response.json()
            if data.get('response', {}).get('result') == 1:
                current_players = data['response'].get('player_count')
        
        # Fetch 24h peak from SteamCharts API
        try:
            charts_url = f"https://steamcharts.com/app/{appid}/chart-data.json"
            charts_response = requests.get(charts_url, timeout=5)
            
            if charts_response.status_code == 200:
                charts_data = charts_response.json()
                # SteamCharts returns array of [timestamp, player_count] pairs
                # Get the last 24 hours of data and find the peak
                if charts_data and len(charts_data) > 0:
                    # Get data from last 24 hours (timestamps are in milliseconds)
                    last_24h_timestamp = (current_time - 86400) * 1000
                    recent_data = [point for point in charts_data if point[0] >= last_24h_timestamp]
                    
                    if recent_data:
                        # Find peak from last 24h
                        peak_24h = max(point[1] for point in recent_data if point[1] is not None)
        except Exception as e:
            print(f"Warning: Could not fetch SteamCharts data for AppID {appid}: {e}")
            # If SteamCharts fails, try to estimate from current count
            # This is a rough estimate - peak is usually higher than current
            if current_players and current_players > 1000:
                peak_24h = int(current_players * 1.3)  # Estimate 30% higher
        
        # Cache the result
        cache_data = {
            'current': current_players,
            'peak_24h': peak_24h
        }
        _player_count_cache[appid] = (cache_data, current_time)
        
        return current_players, peak_24h
        
    except Exception as e:
        print(f"Warning: Failed to fetch player counts for AppID {appid}: {e}")
        return None, None


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    """Serve the stats display page"""
    response = app.make_response(render_template_string(
        HTML_TEMPLATE,
        stats=latest_stats,
        default_theme=DEFAULT_THEME,
        default_orientation=DEFAULT_ORIENTATION,
        update_interval=UPDATE_INTERVAL_MS
    ))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/stats', methods=['POST'])
def receive_stats():
    """Receive stats from Bazzite and enrich with Steam data"""
    global latest_stats
    try:
        data = request.get_json()
        if data:
            latest_stats = data
            latest_stats['last_update'] = datetime.now().strftime('%H:%M:%S')
            
            # Enrich with Steam data if we have an AppID
            appid = data.get('appid')
            if appid and appid != 'null' and appid is not None:
                # Fetch official game name
                official_name = get_game_name_from_steam(appid)
                if official_name:
                    latest_stats['game_official_name'] = official_name
                
                # Fetch player counts
                current_players, peak_24h = get_player_counts(appid)
                latest_stats['player_count'] = current_players
                latest_stats['player_peak_24h'] = peak_24h
            else:
                latest_stats['game_official_name'] = None
                latest_stats['player_count'] = None
                latest_stats['player_peak_24h'] = None
            
            return jsonify({"status": "success"}), 200
        return jsonify({"status": "error", "message": "No data received"}), 400
    except Exception as e:
        print(f"Error in receive_stats: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API endpoint for the display to poll current stats"""
    return jsonify(latest_stats)


@app.route('/api/time', methods=['GET'])
def get_time():
    """API endpoint to get server time"""
    now = datetime.now()
    return jsonify({
        "timestamp": now.timestamp(),
        "formatted_time": now.strftime('%I:%M %p'),
        "formatted_date": now.strftime('%A, %B %d, %Y')
    })


@app.route('/api/storage', methods=['GET'])
def get_storage():
    """API endpoint to get mounted disk information"""
    import psutil
    try:
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total_gb': round(usage.total / (1024**3), 1),
                    'used_gb': round(usage.used / (1024**3), 1),
                    'free_gb': round(usage.free / (1024**3), 1),
                    'percent': usage.percent
                })
            except (PermissionError, OSError):
                continue
        return jsonify({'disks': disks})
    except Exception as e:
        return jsonify({'error': str(e), 'disks': []}), 500


@app.route('/api/network', methods=['GET'])
def get_network():
    """API endpoint to get network statistics"""
    import psutil
    import subprocess
    try:
        net_io = psutil.net_io_counters()
        
        # Get ping latency to gateway
        latency = None
        try:
            result = subprocess.run(['ping', '-c', '1', '-W', '1', '8.8.8.8'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'time=' in line:
                        latency = float(line.split('time=')[1].split()[0])
                        break
        except:
            pass
        
        return jsonify({
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv,
            'latency_ms': latency
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/custom_art_by_appid/<appid>')
def get_custom_art_by_appid(appid):
    """Check if custom art exists for a game by Steam AppID"""
    try:
        # Validate AppID
        app_id_int = int(appid)
        if app_id_int <= 0 or app_id_int >= 100000000:
            return jsonify({"exists": False})
        
        # Look for files named with the AppID
        for ext in IMAGE_EXTENSIONS:
            art_file = CUSTOM_ART_FOLDER / f"{appid}{ext}"
            if art_file.exists():
                return jsonify({"exists": True, "url": f"/custom_art/{appid}{ext}"})
        
        return jsonify({"exists": False})
    except (ValueError, Exception):
        return jsonify({"exists": False})


@app.route('/api/custom_art/<game_name>')
def get_custom_art(game_name):
    """Check if custom art exists for a game (case-insensitive)"""
    # Sanitize game name
    safe_name = "".join(c for c in game_name if c.isalnum() or c in (' ', '-', '_')).strip()
    
    # Try exact match first
    for ext in IMAGE_EXTENSIONS:
        art_file = CUSTOM_ART_FOLDER / f"{safe_name}{ext}"
        if art_file.exists():
            return jsonify({"exists": True, "url": f"/custom_art/{safe_name}{ext}"})
    
    # Try case-insensitive match
    try:
        for file in CUSTOM_ART_FOLDER.iterdir():
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS:
                if file.stem.lower() == safe_name.lower():
                    return jsonify({"exists": True, "url": f"/custom_art/{file.name}"})
    except Exception as e:
        print(f"Warning: Error checking custom art: {e}")
    
    return jsonify({"exists": False})


@app.route('/custom_art/<filename>')
def serve_custom_art(filename):
    """Serve custom game art files"""
    return send_from_directory(CUSTOM_ART_FOLDER, filename)


@app.route('/api/settings/orientation', methods=['GET'])
def get_orientation_setting():
    """Get current orientation setting from boot config"""
    import subprocess
    try:
        # Check boot config for display_rotate value
        config_file = None
        if Path('/boot/firmware/config.txt').exists():
            config_file = '/boot/firmware/config.txt'
        elif Path('/boot/config.txt').exists():
            config_file = '/boot/config.txt'
        
        if config_file:
            with open(config_file, 'r') as f:
                for line in f:
                    if line.strip().startswith('display_rotate='):
                        rotation = int(line.split('=')[1].strip())
                        orientation = 'landscape' if rotation == 1 else 'portrait'
                        return jsonify({
                            'orientation': orientation,
                            'rotation': rotation,
                            'config_file': config_file
                        })
        
        # Default if not set
        return jsonify({
            'orientation': DEFAULT_ORIENTATION,
            'rotation': 0,
            'config_file': config_file or 'not found'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/orientation', methods=['POST'])
def set_orientation():
    """Set orientation using xrandr rotation scripts"""
    import subprocess
    try:
        data = request.get_json()
        orientation = data.get('orientation', 'portrait')
        
        # Get user home directory and scripts folder
        user_home = Path.home()
        scripts_dir = user_home / 'stats-display'
        
        # Determine which rotation script to use
        if orientation == 'landscape':
            rotation_script = scripts_dir / 'rotate-landscape.sh'
        else:
            rotation_script = scripts_dir / 'rotate-portrait.sh'
        
        if not rotation_script.exists():
            return jsonify({'error': f'Rotation script not found: {rotation_script}'}), 404
        
        # Run the rotation script immediately
        result = subprocess.run(
            ['bash', str(rotation_script)],
            env={'DISPLAY': ':0'},
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode != 0:
            return jsonify({
                'error': f'Rotation script failed: {result.stderr}',
                'success': False
            }), 500
        
        # Update the systemd service to use the correct rotation script on next boot
        try:
            service_file = Path('/etc/systemd/system/stats-display.service')
            if service_file.exists():
                with open(service_file, 'r') as f:
                    service_content = f.read()
                
                # Replace the ExecStartPre line with the new rotation script (boot version)
                if orientation == 'landscape':
                    new_content = service_content.replace(
                        'stats-display/rotate-portrait-boot.sh',
                        'stats-display/rotate-landscape-boot.sh'
                    )
                    # Also handle old format without -boot
                    new_content = new_content.replace(
                        'stats-display/rotate-portrait.sh',
                        'stats-display/rotate-landscape-boot.sh'
                    )
                else:
                    new_content = service_content.replace(
                        'stats-display/rotate-landscape-boot.sh',
                        'stats-display/rotate-portrait-boot.sh'
                    )
                    # Also handle old format without -boot
                    new_content = new_content.replace(
                        'stats-display/rotate-landscape.sh',
                        'stats-display/rotate-portrait-boot.sh'
                    )
                
                # Write to temp file first
                temp_file = '/tmp/stats-display.service.tmp'
                with open(temp_file, 'w') as f:
                    f.write(new_content)
                
                # Copy with sudo
                subprocess.run(['sudo', 'cp', temp_file, str(service_file)], check=True)
                subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
                subprocess.run(['sudo', 'rm', temp_file], check=True)
        except Exception as e:
            print(f"Warning: Could not update service file: {e}")
            # Non-fatal - rotation still worked
        
        return jsonify({
            'success': True,
            'orientation': orientation,
            'message': f'Display rotated to {orientation}. Changes will persist on reboot.',
            'reboot_required': False
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Rotation script timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/reboot', methods=['POST'])
def reboot_system():
    """Reboot the Raspberry Pi"""
    import subprocess
    try:
        # Use 'now' for immediate reboot
        subprocess.Popen(['sudo', 'reboot'])
        return jsonify({
            'success': True,
            'message': 'Rebooting now...'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/settings')
def settings_page():
    """Settings page for orientation and display config"""
    import socket
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
    except:
        ip_address = "Unknown"
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Settings - Stats Display</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0a0a0a;
            color: #fff;
            padding: 40px 20px;
            min-height: 100vh;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        h1 {
            font-size: 32px;
            margin-bottom: 10px;
        }
        .subtitle {
            color: #888;
            margin-bottom: 40px;
        }
        .card {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 20px;
        }
        .card h2 {
            font-size: 20px;
            margin-bottom: 20px;
            color: #00ff88;
        }
        .orientation-buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 20px;
        }
        .btn {
            padding: 15px 25px;
            font-size: 16px;
            font-weight: 600;
            border: 2px solid #333;
            border-radius: 8px;
            background: #2a2a2a;
            color: #fff;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn:hover {
            background: #3a3a3a;
            border-color: #00ff88;
        }
        .btn.active {
            background: #00ff88;
            color: #000;
            border-color: #00ff88;
        }
        .btn-primary {
            background: #00ff88;
            color: #000;
            border-color: #00ff88;
        }
        .btn-primary:hover {
            background: #00dd77;
        }
        .btn-danger {
            background: #ff0044;
            color: #fff;
            border-color: #ff0044;
        }
        .btn-danger:hover {
            background: #dd0033;
        }
        .info {
            background: #2a2a0a;
            border: 1px solid #554400;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            font-size: 14px;
            line-height: 1.6;
        }
        .info strong {
            color: #ffaa00;
        }
        .status {
            margin-top: 15px;
            padding: 12px;
            border-radius: 6px;
            font-size: 14px;
            text-align: center;
        }
        .status.success {
            background: #0a3a0a;
            border: 1px solid #00ff88;
            color: #00ff88;
        }
        .status.error {
            background: #3a0a0a;
            border: 1px solid #ff0044;
            color: #ff0044;
        }
        .current-status {
            display: flex;
            justify-content: space-between;
            padding: 15px;
            background: #0a0a0a;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 14px;
        }
        .back-link {
            display: inline-block;
            color: #00ff88;
            text-decoration: none;
            margin-bottom: 20px;
            font-size: 16px;
        }
        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Back to Stats Display</a>
        
        <h1>Display Settings</h1>
        <p class="subtitle">Configure orientation and display rotation</p>
        
        <div class="card">
            <h2>Network Information</h2>
            <div class="current-status">
                <span>IP Address:</span>
                <span style="color: #00ff88; font-weight: 600;">{{ ip_address }}</span>
            </div>
            <div class="current-status">
                <span>Stats Display:</span>
                <span><a href="/" style="color: #00ff88;">http://{{ ip_address }}:5000</a></span>
            </div>
        </div>
        
        <div class="card">
            <h2>Current Configuration</h2>
            <div class="current-status">
                <span>Orientation:</span>
                <span id="current-orientation">Loading...</span>
            </div>
            <div class="current-status">
                <span>Physical Rotation:</span>
                <span id="current-rotation">Loading...</span>
            </div>
        </div>
        
        <div class="card">
            <h2>Change Orientation</h2>
            <div class="orientation-buttons">
                <button class="btn" id="btn-portrait" onclick="setOrientation('portrait')">
                    📱 Portrait<br><small style="font-weight:normal">480×1920</small>
                </button>
                <button class="btn" id="btn-landscape" onclick="setOrientation('landscape')">
                    🖥️ Landscape<br><small style="font-weight:normal">1920×480</small>
                </button>
            </div>
            
            <div class="info">
                <strong>⚠️ Note:</strong> Changing orientation will:
                <ul style="margin-top:10px; margin-left:20px;">
                    <li>Immediately update the stats display layout</li>
                    <li>Update boot config for physical display rotation</li>
                    <li><strong>Require a reboot</strong> for physical rotation to take effect</li>
                </ul>
            </div>
            
            <div id="status-message"></div>
            
            <button class="btn btn-danger" id="btn-reboot" onclick="rebootSystem()" style="width:100%; margin-top:20px; display:none;">
                🔄 Reboot Now
            </button>
        </div>
    </div>
    
    <script>
        let currentOrientation = 'portrait';
        
        async function loadCurrentSettings() {
            try {
                const response = await fetch('/api/settings/orientation');
                const data = await response.json();
                
                currentOrientation = data.orientation;
                document.getElementById('current-orientation').textContent = 
                    data.orientation.charAt(0).toUpperCase() + data.orientation.slice(1);
                document.getElementById('current-rotation').textContent = 
                    data.rotation + '° (' + (data.rotation === 1 ? 'Landscape' : 'Portrait') + ')';
                
                // Update button states
                document.getElementById('btn-portrait').classList.toggle('active', data.orientation === 'portrait');
                document.getElementById('btn-landscape').classList.toggle('active', data.orientation === 'landscape');
            } catch (error) {
                console.error('Failed to load settings:', error);
            }
        }
        
        async function setOrientation(orientation) {
            const statusDiv = document.getElementById('status-message');
            const rebootBtn = document.getElementById('btn-reboot');
            
            try {
                statusDiv.className = 'status';
                statusDiv.textContent = 'Updating orientation...';
                
                const response = await fetch('/api/settings/orientation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ orientation })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    statusDiv.className = 'status success';
                    statusDiv.innerHTML = '✓ ' + data.message;
                    rebootBtn.style.display = 'block';
                    
                    // Update button states
                    document.getElementById('btn-portrait').classList.toggle('active', orientation === 'portrait');
                    document.getElementById('btn-landscape').classList.toggle('active', orientation === 'landscape');
                    
                    // Reload main page with new orientation
                    window.opener?.location.reload();
                } else {
                    statusDiv.className = 'status error';
                    statusDiv.textContent = '✗ Error: ' + (data.error || 'Unknown error');
                }
            } catch (error) {
                statusDiv.className = 'status error';
                statusDiv.textContent = '✗ Failed to update: ' + error.message;
            }
        }
        
        async function rebootSystem() {
            if (!confirm('Are you sure you want to reboot the Raspberry Pi?')) {
                return;
            }
            
            const statusDiv = document.getElementById('status-message');
            
            try {
                const response = await fetch('/api/settings/reboot', {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                statusDiv.className = 'status success';
                statusDiv.textContent = data.message;
                
                // Countdown
                let seconds = 3;
                const interval = setInterval(() => {
                    seconds--;
                    if (seconds > 0) {
                        statusDiv.textContent = 'Rebooting in ' + seconds + ' seconds...';
                    } else {
                        clearInterval(interval);
                        statusDiv.textContent = 'System is rebooting...';
                    }
                }, 1000);
                
            } catch (error) {
                statusDiv.className = 'status error';
                statusDiv.textContent = '✗ Failed to reboot: ' + error.message;
            }
        }
        
        // Load settings on page load
        loadCurrentSettings();
    </script>
</body>
</html>
    """)


# ============================================================
# MAIN
# ============================================================

def main():
    """Start the Flask server"""
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    except Exception:
        ip = "unknown"
    
    print("=" * 60)
    print("Pi Stats Display Server v2.0")
    print("=" * 60)
    print(f"Hostname: {hostname}")
    print(f"IP Address: {ip}")
    print(f"Access: http://{ip}:5000")
    print("=" * 60)
    print("CONFIGURATION:")
    print(f"  • Theme: {DEFAULT_THEME}")
    print(f"  • Orientation: {DEFAULT_ORIENTATION}")
    print(f"  • Update Interval: {UPDATE_INTERVAL_MS}ms")
    print(f"  • Custom Art: {CUSTOM_ART_FOLDER}")
    print("=" * 60)
    print("FEATURES:")
    print("  • 8 themes with localStorage persistence")
    print("  • Portrait/Landscape orientation support")
    print("  • Custom game art (place in game_art folder)")
    print("  • Steam library art fallback")
    print("  • Real-time stats with 500ms polling")
    print("=" * 60)
    print("CUSTOM ART:")
    print(f"  Location: {CUSTOM_ART_FOLDER}")
    print("  Formats: .jpg, .jpeg, .png, .webp, .gif")
    print("  Priority: AppID → Game Name → Steam")
    print("  Example (AppID): '1091500.jpg' (Cyberpunk 2077)")
    print("  Example (Name): 'Cyberpunk 2077.jpg'")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
