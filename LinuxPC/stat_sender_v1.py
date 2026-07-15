#!/usr/bin/env python3
"""
Linux PC System Stats Sender v1.0
Collects system stats and sends them to Pi display via WiFi
Works on Bazzite, SteamOS, and other Linux systems
Optimized with caching and improved efficiency
"""

import json
import time
import subprocess
import requests
from pathlib import Path
import re

# Configuration - load from config.json (created by install.sh)
import json as _json
import sys as _sys
_config_path = Path(__file__).parent / 'config.json'
_config = {}
if _config_path.exists():
    try:
        with open(_config_path) as _f:
            _config = _json.load(_f)
    except Exception as _e:
        print(f"ERROR: Could not read config.json: {_e}")
        _sys.exit(1)
else:
    print(f"ERROR: config.json not found at {_config_path}")
    print("Please run the installer (install.sh) to set up your configuration.")
    _sys.exit(1)

PI_IP = _config.get("pi_ip", "").strip()
if not PI_IP:
    print("ERROR: No Pi IP address found in config.json.")
    print("Please run the installer (install.sh) and enter your Raspberry Pi's IP address.")
    _sys.exit(1)

PREFERRED_ORIENTATION = _config.get("orientation", None)  # None = don't push, let Pi keep its setting
PI_URL = f"http://{PI_IP}:5000/stats"
PI_ORIENTATION_URL = f"http://{PI_IP}:5000/api/settings/default_orientation"
UPDATE_INTERVAL = 1  # seconds
GAME_CACHE_DURATION = 5  # seconds

# Hardware name cache (doesn't change during runtime)
_cached_cpu_name = None
_cached_gpu_name = None

# CPU energy tracking
_last_cpu_energy = None
_last_cpu_energy_time = None

# Game cache (prevents flickering)
_cached_game_name = None
_cached_game_time = 0
_cached_game_appid = None

# Steam paths cache
_steam_paths = None


# ============================================================
# HARDWARE INFO (Cached - only runs once)
# ============================================================

def get_cpu_name():
    """Get CPU name (cached after first call)"""
    global _cached_cpu_name
    if _cached_cpu_name:
        return _cached_cpu_name
    
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if 'model name' in line:
                    cpu_name = line.split(':', 1)[1].strip()
                    # Clean up the name
                    cpu_name = re.sub(r'\(R\)|\(TM\)|\(tm\)', '', cpu_name)
                    cpu_name = re.sub(r'\d+-Core\s+Processor|\d+-Core', '', cpu_name, flags=re.IGNORECASE)
                    cpu_name = re.sub(r'with.*Graphics|CPU\s*@.*|Processor', '', cpu_name, flags=re.IGNORECASE)
                    cpu_name = ' '.join(cpu_name.split())
                    
                    # Brand formatting
                    if 'AMD' in cpu_name:
                        cpu_name = 'AMD ' + cpu_name.replace('AMD ', '')
                    elif 'Intel' in cpu_name:
                        cpu_name = 'Intel ' + cpu_name.replace('Intel ', '').replace('Core ', '')
                    
                    _cached_cpu_name = cpu_name
                    return cpu_name
    except Exception as e:
        print(f"Warning: Could not read CPU name: {e}")
    
    _cached_cpu_name = "Unknown CPU"
    return _cached_cpu_name


def get_gpu_name():
    """Get GPU name (cached after first call)"""
    global _cached_gpu_name
    if _cached_gpu_name:
        return _cached_gpu_name
    
    try:
        result = subprocess.run(['lspci'], capture_output=True, text=True, timeout=2)
        for line in result.stdout.split('\n'):
            if any(x in line for x in ['VGA', 'Display', '3D']):
                gpu_name = line.split(':', 1)[-1].strip()
                
                # Clean up vendor names
                gpu_name = gpu_name.replace('Advanced Micro Devices, Inc.', 'AMD')
                gpu_name = gpu_name.replace('[AMD/ATI]', '')
                gpu_name = gpu_name.replace('NVIDIA Corporation', 'NVIDIA')
                gpu_name = gpu_name.replace('Intel Corporation', 'Intel')
                gpu_name = re.sub(r'\(rev \w+\)|\[.*?\]', '', gpu_name)
                gpu_name = ' '.join(gpu_name.split())
                
                # AMD chip to marketing name mapping
                amd_map = {
                    # RDNA 4 (RX 9000)
                    'Navi 48 XT': 'RX 9070 XT 16GB', 'Navi 48 XL': 'RX 9070 XT 12GB',
                    'Navi 48': 'RX 9070 XT',
                    'Navi 44 XT': 'RX 9060 XT 16GB', 'Navi 44 XL': 'RX 9060 XT 8GB',
                    'Navi 44': 'RX 9060 XT',
                    # RDNA 3 (RX 7000)
                    'Navi 31 XT': 'RX 7900 XTX', 'Navi 31 XL': 'RX 7900 XT',
                    'Navi 31': 'RX 7900 XTX',
                    'Navi 32 XT': 'RX 7800 XT', 'Navi 32': 'RX 7800 XT',
                    'Navi 33 XT': 'RX 7600 XT', 'Navi 33 XL': 'RX 7600',
                    'Navi 33': 'RX 7600 XT',
                    # RDNA 2 (RX 6000)
                    'Navi 21 XT': 'RX 6900 XT', 'Navi 21 XL': 'RX 6800 XT',
                    'Navi 21': 'RX 6900 XT / 6800 XT / 6800',
                    'Navi 22 XT': 'RX 6750 XT', 'Navi 22 XL': 'RX 6700 XT',
                    'Navi 22': 'RX 6700 XT',
                    'Navi 23 XT': 'RX 6600 XT', 'Navi 23 XL': 'RX 6600',
                    'Navi 23': 'RX 6600 XT / 6600',
                    # RDNA 1 (RX 5000)
                    'Navi 10': 'RX 5700 XT / 5700',
                    'Navi 12': 'RX 5500 XT / 5500',
                    'Navi 14': 'RX 5500 / 5300',
                    # Vega
                    'Vega 10': 'RX Vega 64 / 56',
                    'Vega 12': 'RX Vega M',
                    'Vega 20': 'VII',
                    # Polaris (RX 400-500)
                    'Polaris 10': 'RX 580 / 480', 'Polaris 20': 'RX 590 / 580',
                    'Polaris 11': 'RX 560 / 460', 'Polaris 12': 'RX 550',
                    'Ellesmere': 'RX 480 / 580', 'Baffin': 'RX 460 / 560',
                    'Lexa': 'RX 550',
                }
                
                for chip, marketing in amd_map.items():
                    if chip in gpu_name:
                        _cached_gpu_name = f"AMD {marketing}"
                        return _cached_gpu_name
                
                _cached_gpu_name = gpu_name
                return gpu_name
    except Exception as e:
        print(f"Warning: Could not read GPU name: {e}")
    
    _cached_gpu_name = "Unknown GPU"
    return _cached_gpu_name


# ============================================================
# CPU STATS
# ============================================================

_last_cpu_total = None
_last_cpu_idle = None


def get_cpu_usage():
    """Get CPU usage percentage from /proc/stat deltas (no subprocess spawn).

    Needs two samples to compute a delta, so the very first call returns
    0.0; every call after that is a real reading based on the time elapsed
    since the previous call.
    """
    global _last_cpu_total, _last_cpu_idle
    try:
        with open('/proc/stat', 'r') as f:
            line = f.readline()
        if line.startswith('cpu '):
            fields = [int(x) for x in line.split()[1:]]
            total = sum(fields)
            idle = fields[3]  # idle is the 4th field

            if _last_cpu_total is not None:
                total_delta = total - _last_cpu_total
                idle_delta = idle - _last_cpu_idle
                _last_cpu_total, _last_cpu_idle = total, idle
                if total_delta > 0:
                    return round(100 * (1 - idle_delta / total_delta), 1)
                return 0.0

            _last_cpu_total, _last_cpu_idle = total, idle
    except Exception as e:
        print(f"Warning: Could not read CPU usage: {e}")

    return 0.0


def get_cpu_temp():
    """Get CPU temperature from hwmon sensors"""
    try:
        for hwmon_path in Path('/sys/class/hwmon').glob('hwmon*'):
            name_file = hwmon_path / 'name'
            if not name_file.exists():
                continue
            
            name = name_file.read_text().strip()
            if name in ['k10temp', 'zenpower', 'coretemp']:
                # Try to find Package temp first
                for temp_file in hwmon_path.glob('temp*_input'):
                    label_file = temp_file.parent / temp_file.name.replace('_input', '_label')
                    if label_file.exists() and 'Package' in label_file.read_text():
                        return round(int(temp_file.read_text()) / 1000, 1)
                
                # Fallback to temp1_input
                temp_file = hwmon_path / 'temp1_input'
                if temp_file.exists():
                    return round(int(temp_file.read_text()) / 1000, 1)
    except Exception as e:
        print(f"Warning: Could not read CPU temp: {e}")
    
    return 0.0


def get_cpu_freq():
    """Get current CPU frequency in MHz"""
    try:
        # Try using cpuinfo_cur_freq first (more reliable)
        freq_file = Path('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq')
        if freq_file.exists():
            return round(int(freq_file.read_text()) / 1000)
        
        # Fallback to /proc/cpuinfo
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if 'cpu MHz' in line:
                    return round(float(line.split(':', 1)[1].strip()))
    except Exception as e:
        print(f"Warning: Could not read CPU frequency: {e}")
    
    return 0


def get_cpu_power():
    """Get CPU power consumption in watts.
    
    Tries multiple sources in order:
    1. AMD zenergy/hwmon power files
    2. RAPL energy counters (may be permission denied on SteamOS/immutable distros)
    3. Returns None if unavailable (caller should display N/A, not 0W)
    """
    global _last_cpu_energy, _last_cpu_energy_time

    try:
        # AMD zenergy or hwmon power input
        for hwmon_path in Path('/sys/class/hwmon').glob('hwmon*'):
            name_file = hwmon_path / 'name'
            if not name_file.exists():
                continue
            name = name_file.read_text().strip()
            if name == 'amdgpu':
                continue  # that's the GPU sensor, not CPU
            for pfile in ['power1_input', 'power1_average']:
                p = hwmon_path / pfile
                if p.exists():
                    try:
                        val = int(p.read_text().strip())
                        if val > 0:
                            return round(val / 1_000_000, 1)
                    except Exception:
                        pass

        # RAPL energy counter (intel-rapl interface, used by AMD too)
        # The installer sets up /etc/tmpfiles.d/rapl-read.conf to make this
        # file world-readable on every boot, so no sudo needed.
        rapl_energy = Path('/sys/devices/virtual/powercap/intel-rapl/intel-rapl:0/energy_uj')
        if rapl_energy.exists():
            try:
                now = time.time()
                energy = int(rapl_energy.read_text().strip())

                if _last_cpu_energy is not None and _last_cpu_energy_time is not None:
                    time_delta = now - _last_cpu_energy_time
                    energy_delta = energy - _last_cpu_energy
                    if time_delta > 0 and energy_delta >= 0:
                        power_w = (energy_delta / 1_000_000) / time_delta
                        if 0 < power_w < 500:
                            _last_cpu_energy = energy
                            _last_cpu_energy_time = now
                            return round(power_w, 1)
                _last_cpu_energy = energy
                _last_cpu_energy_time = now
            except PermissionError:
                # RAPL not made readable yet - run the installer to fix this
                pass
            except Exception:
                pass

    except Exception as e:
        print(f"Warning: Could not read CPU power: {e}")

    return None  # Caller should show N/A, not 0W
def get_gpu_stats():
    """Get GPU stats (usage, temp, freq, power, VRAM)
    
    Handles both discrete AMD GPUs and APUs (Steam Deck Van Gogh/Aerith).
    On APUs, visible VRAM (mem_info_vis_vram_*) is used instead of total
    shared system memory which can report falsely large values.
    Frequency comes from hwmon freq1_input (Hz) rather than pp_dpm_sclk
    which has inconsistent formatting across driver versions.
    """
    stats = {"usage": 0, "temp": 0.0, "frequency": 0, "power": 0.0, "vram_used": 0, "vram_total": 0, "vram_free": 0}
    
    try:
        # AMD GPU (discrete or APU)
        for hwmon_path in Path('/sys/class/hwmon').glob('hwmon*'):
            name_file = hwmon_path / 'name'
            if not name_file.exists():
                continue
            
            name = name_file.read_text().strip()
            if name not in ['amdgpu', 'amdgpu-pci']:
                continue

            # hwmon5/device resolves to the PCI device path, NOT the drm path.
            # gpu_busy_percent, mem_info_*, pp_dpm_sclk all live under the drm
            # card device. Find the drm card whose device symlink resolves to
            # the same PCI path as this hwmon.
            hwmon_pci = (hwmon_path / 'device').resolve()
            gpu_card = None
            for card_dev in Path('/sys/class/drm').glob('card*/device'):
                if card_dev.resolve() == hwmon_pci:
                    gpu_card = card_dev
                    break
            if gpu_card is None:
                card_paths = list(Path('/sys/class/drm').glob('card*/device'))
                gpu_card = card_paths[0] if card_paths else Path('/sys/class/drm/card0/device')

            # GPU usage
            usage_file = gpu_card / 'gpu_busy_percent'
            if usage_file.exists():
                stats['usage'] = int(usage_file.read_text().strip())

            # GPU temperature - use temp1 (edge/junction)
            for temp_name in ['temp1_input', 'temp2_input']:
                temp_file = hwmon_path / temp_name
                if temp_file.exists():
                    val = int(temp_file.read_text().strip())
                    if val > 0:
                        stats['temp'] = round(val / 1000, 1)
                        break

            # GPU frequency - hwmon freq1_input is in Hz, convert to MHz
            # More reliable than pp_dpm_sclk which has variable formatting
            freq_file = hwmon_path / 'freq1_input'
            if freq_file.exists():
                hz = int(freq_file.read_text().strip())
                stats['frequency'] = hz // 1_000_000  # Hz -> MHz
            else:
                # Fallback: parse pp_dpm_sclk for the active (*) entry
                sclk_file = gpu_card / 'pp_dpm_sclk'
                if sclk_file.exists():
                    for line in sclk_file.read_text().splitlines():
                        if '*' in line:
                            match = re.search(r'(\d+)Mhz', line, re.IGNORECASE)
                            if match:
                                stats['frequency'] = int(match.group(1))
                            break

            # GPU power
            power_file = hwmon_path / 'power1_average'
            if power_file.exists():
                stats['power'] = round(int(power_file.read_text().strip()) / 1_000_000, 1)

            # VRAM - always use full card VRAM (mem_info_vram_*)
            vram_used_file = gpu_card / 'mem_info_vram_used'
            vram_total_file = gpu_card / 'mem_info_vram_total'
            if vram_used_file.exists() and vram_total_file.exists():
                stats['vram_used'] = int(vram_used_file.read_text().strip()) // (1024 * 1024)
                stats['vram_total'] = int(vram_total_file.read_text().strip()) // (1024 * 1024)
                stats['vram_free'] = stats['vram_total'] - stats['vram_used']

            return stats

        # NVIDIA GPU fallback
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu,clocks.gr,power.draw,memory.used,memory.total',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            vals = [v.strip() for v in result.stdout.split(',')]
            stats['usage'] = int(float(vals[0]))
            stats['temp'] = float(vals[1])
            stats['frequency'] = int(float(vals[2]))
            stats['power'] = float(vals[3])
            stats['vram_used'] = int(float(vals[4]))
            stats['vram_total'] = int(float(vals[5]))
            stats['vram_free'] = stats['vram_total'] - stats['vram_used']

    except Exception as e:
        print(f"Warning: Could not read GPU stats: {e}")
    
    return stats


# ============================================================
# RAM STATS
# ============================================================

def get_memory_stats():
    """Get memory usage stats with RAM info"""
    try:
        mem_total = mem_avail = 0
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if 'MemTotal' in line:
                    mem_total = int(line.split()[1]) / (1024 * 1024)
                elif 'MemAvailable' in line:
                    mem_avail = int(line.split()[1]) / (1024 * 1024)
        
        mem_used = mem_total - mem_avail
        percent = (mem_used / mem_total * 100) if mem_total > 0 else 0
        
        # Try to get RAM speed and type from dmidecode (without sudo)
        ram_info = {"type": "Unknown", "speed": "Unknown"}
        try:
            # Try without sudo first
            result = subprocess.run(['dmidecode', '-t', 'memory'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for i, line in enumerate(lines):
                    if 'Type:' in line and 'Error' not in line:
                        ram_type = line.split(':', 1)[1].strip()
                        if ram_type not in ['Unknown', 'Other', '']:
                            ram_info['type'] = ram_type
                    if 'Speed:' in line and 'Unknown' not in line:
                        speed = line.split(':', 1)[1].strip()
                        if speed and speed != 'Unknown':
                            ram_info['speed'] = speed
                            break
        except Exception:
            # dmidecode not available or requires root - that's OK, continue without RAM type/speed
            pass
        
        return {
            "used": round(mem_used, 1),
            "total": round(mem_total, 1),
            "percent": round(percent, 1),
            "type": ram_info['type'],
            "speed": ram_info['speed']
        }
    except Exception as e:
        print(f"Warning: Could not read memory stats: {e}")
        return {"used": 0, "total": 0, "percent": 0, "type": "Unknown", "speed": "Unknown"}


# ============================================================
# DISK STATS
# ============================================================

_cached_disk_stats = []
_cached_disk_time = 0
DISK_CACHE_DURATION = 10  # seconds - disk usage doesn't need per-second freshness


def get_disk_stats():
    """Get physical disk statistics (cached; refreshed every DISK_CACHE_DURATION
    seconds since it shells out to lsblk + one df call per mounted partition)."""
    global _cached_disk_stats, _cached_disk_time
    now = time.time()
    if now - _cached_disk_time < DISK_CACHE_DURATION:
        return _cached_disk_stats

    _cached_disk_stats = _collect_disk_stats()
    _cached_disk_time = now
    return _cached_disk_stats


def _collect_disk_stats():
    """Get physical disk statistics by aggregating all their partitions"""
    try:
        disks = {}  # Use dict to aggregate partitions by physical disk
        
        # Get all block devices including partitions
        result = subprocess.run(['lsblk', '-b', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT', '-n'],
                              capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            
            # First pass: identify physical disks
            physical_disks = {}
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    # Strip tree characters (└─, ├─, etc.) from device names
                    name = parts[0].strip().lstrip('└├─│ ')
                    size_bytes = int(parts[1])
                    dev_type = parts[2]
                    
                    # Skip zram and swap
                    if name.startswith('zram') or name.startswith('swap'):
                        continue
                    
                    # Track physical disks
                    if dev_type == 'disk':
                        physical_disks[name] = {
                            'name': name,
                            'total_bytes': size_bytes,
                            'used_bytes': 0,
                            'total_gb': round(size_bytes / (1024**3), 1),
                            'used_gb': 0,
                            'percent': 0,
                            'partitions_seen': set()  # Track which partitions we've counted
                        }
            
            # Second pass: aggregate partition usage for each disk
            for line in lines:
                parts = line.split(maxsplit=3)
                if len(parts) >= 4:
                    # Strip tree characters from device name
                    name = parts[0].strip().lstrip('└├─│ ')
                    dev_type = parts[2]
                    mountpoint = parts[3].strip()
                    
                    # Skip if not a partition or not mounted
                    if dev_type != 'part' or not mountpoint or mountpoint == '':
                        continue
                    
                    # Find parent disk with better matching
                    parent_disk = None
                    for disk_name in physical_disks.keys():
                        if name.startswith(disk_name):
                            remainder = name[len(disk_name):]
                            if remainder and (remainder[0].isdigit() or remainder[0] == 'p'):
                                parent_disk = disk_name
                                break
                    
                    if not parent_disk:
                        continue
                    
                    # Check if we've already counted this partition
                    # (Bazzite has bind mounts - same partition mounted multiple times)
                    if name in physical_disks[parent_disk]['partitions_seen']:
                        continue
                    
                    # Mark partition as seen
                    physical_disks[parent_disk]['partitions_seen'].add(name)
                    
                    # Get usage for this partition (only once)
                    try:
                        df_result = subprocess.run(['df', '-B1', mountpoint],
                                                 capture_output=True, text=True, timeout=1)
                        if df_result.returncode == 0:
                            df_lines = df_result.stdout.strip().split('\n')
                            if len(df_lines) > 1:
                                df_parts = df_lines[1].split()
                                if len(df_parts) >= 3:
                                    partition_used = int(df_parts[2])
                                    physical_disks[parent_disk]['used_bytes'] += partition_used
                    except Exception:
                        pass
            
            # Calculate percentages and convert to GB
            for disk_name, disk in physical_disks.items():
                disk['used_gb'] = round(disk['used_bytes'] / (1024**3), 1)
                if disk['total_bytes'] > 0:
                    disk['percent'] = round((disk['used_bytes'] / disk['total_bytes']) * 100, 1)
                else:
                    disk['percent'] = 0
                
                # Remove tracking data from final output
                disk.pop('partitions_seen', None)
                
                # Only include disks in final output
                disks[disk_name] = {
                    'device': f"/dev/{disk['name']}",
                    'name': disk['name'],
                    'total_gb': disk['total_gb'],
                    'used_gb': disk['used_gb'],
                    'percent': disk['percent']
                }
        
        return list(disks.values())
    except Exception as e:
        print(f"Warning: Could not read disk stats: {e}")
        return []


# ============================================================
# FPS
# ============================================================

def get_fps_from_mangohud():
    """Get FPS from MangoHud - reads /tmp/fps.txt written by fps_logger.sh,
    with fallback to reading MangoHud CSVs directly (SteamOS writes to
    ~/.local/share/MangoHud/, other distros write to $HOME)"""
    try:
        # Primary: fps_logger.sh writes here
        fps_file = Path('/tmp/fps.txt')
        if fps_file.exists() and (time.time() - fps_file.stat().st_mtime < 3):
            fps_str = fps_file.read_text().strip()
            if fps_str.isdigit():
                return int(fps_str)
    except Exception:
        pass

    # Fallback: read MangoHud CSV directly
    # SteamOS puts them in ~/.local/share/MangoHud/, Bazzite/others in $HOME
    import glob
    search_dirs = [
        Path.home() / '.local/share/MangoHud',
        Path.home(),
    ]
    pattern = '*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_[0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv'
    try:
        for search_dir in search_dirs:
            csv_files = sorted(search_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            if csv_files:
                latest = csv_files[0]
                if time.time() - latest.stat().st_mtime < 3:
                    lines = latest.read_text().splitlines()
                    for line in reversed(lines):
                        if line and not line.startswith('fps'):
                            fps_str = line.split(',')[0].strip()
                            try:
                                return int(float(fps_str))
                            except ValueError:
                                pass
                break
    except Exception:
        pass

    return 0


def get_fps_from_gamescope():
    """Get FPS from Gamescope stats file
    
    Requires game launch option:
    gamescope --stats-path /tmp/gamescope-stats -- %command%
    """
    try:
        stats_file = Path('/tmp/gamescope-stats')
        if not stats_file.exists():
            return 0
        
        # Check if file is recent (updated within last 3 seconds)
        if (time.time() - stats_file.stat().st_mtime) > 3:
            return 0
        
        with open(stats_file, 'r') as f:
            content = f.read()
            
            # Gamescope stats format varies, try multiple patterns
            # Pattern 1: "fps: 60.5" or "FPS: 60.5"
            fps_match = re.search(r'fps:\s*(\d+(?:\.\d+)?)', content, re.IGNORECASE)
            if fps_match:
                return int(float(fps_match.group(1)))
            
            # Pattern 2: Just a number on a line labeled fps
            for line in content.split('\n'):
                line = line.strip().lower()
                if line.startswith('fps'):
                    # Extract first number found
                    num_match = re.search(r'(\d+(?:\.\d+)?)', line)
                    if num_match:
                        return int(float(num_match.group(1)))
    except Exception:
        pass
    
    return 0


def get_fps():
    """Get FPS from multiple sources (MangoHud, Gamescope, etc.)
    
    Priority:
    1. MangoHud CSV files (works everywhere with MangoHud enabled)
    2. Gamescope stats file (requires launch option)
    """
    # Try MangoHud first (most reliable, works on Bazzite/Linux/SteamOS)
    fps = get_fps_from_mangohud()
    if fps > 0:
        return fps
    
    # Try Gamescope as fallback (without MangoHud)
    fps = get_fps_from_gamescope()
    if fps > 0:
        return fps
    
    return 0


# ============================================================
# GAME DETECTION
# ============================================================

def update_game_cache(name, appid):
    """Update the game cache with new values"""
    global _cached_game_name, _cached_game_time, _cached_game_appid
    _cached_game_name = name
    _cached_game_time = time.time()
    _cached_game_appid = appid


def get_steam_paths():
    """Get Steam installation paths (cached)"""
    global _steam_paths
    if _steam_paths is not None:
        return _steam_paths
    
    _steam_paths = []
    for path in [
        Path.home() / '.steam/steam/steamapps',
        Path.home() / '.local/share/Steam/steamapps',
    ]:
        if path.exists():
            _steam_paths.append(path)
    
    return _steam_paths


def get_current_game():
    """Detect current game with caching to prevent flickering"""
    global _cached_game_name, _cached_game_time, _cached_game_appid
    
    current_time = time.time()
    game_info = {"name": "Desktop", "appid": None}
    
    # Method 1: Check Steam running games
    # One pgrep call finds every running steam_app_<id> process at once,
    # instead of spawning a separate pgrep per installed game manifest
    # (which could be 100+ subprocess calls a second on a big library).
    try:
        result = subprocess.run(
            ['pgrep', '-af', 'steam_app_'],
            capture_output=True, text=True, timeout=1
        )
        running_appids = set(re.findall(r'steam_app_(\d+)', result.stdout)) if result.returncode == 0 else set()

        if running_appids:
            for steam_path in get_steam_paths():
                for manifest in steam_path.glob('appmanifest_*.acf'):
                    appid = manifest.stem.split('_')[1]
                    if appid not in running_appids:
                        continue
                    # Parse game name from manifest
                    try:
                        content = manifest.read_text(encoding='utf-8', errors='ignore')
                        name_match = re.search(r'"name"\s+"([^"]+)"', content)
                        if name_match:
                            game_name = name_match.group(1)
                            update_game_cache(game_name, appid)
                            return {"name": game_name, "appid": appid}
                    except Exception:
                        pass
    except Exception as e:
        print(f"Warning: Steam game detection failed: {e}")
    
    # Method 2: Check for SteamLaunch process
    try:
        result = subprocess.run(
            ['pgrep', '-af', 'SteamLaunch'],
            capture_output=True, text=True, timeout=1
        )
        
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split('\n'):
                if 'SteamLaunch' in line:
                    # Extract AppID
                    appid_match = re.search(r'AppId[=/](\d+)', line)
                    appid = appid_match.group(1) if appid_match else None
                    
                    # Extract game name from executable
                    parts = line.split()
                    for part in parts:
                        if '.exe' in part or '.x86_64' in part:
                            game_name = part.split('/')[-1].replace('.exe', '').replace('.x86_64', '')
                            game_name = game_name[:50]  # Limit length
                            update_game_cache(game_name, appid)
                            return {"name": game_name, "appid": appid}
    except Exception as e:
        print(f"Warning: SteamLaunch detection failed: {e}")
    
    # Method 3: Gamescope detection
    try:
        result = subprocess.run(
            ['pgrep', 'gamescope'],
            capture_output=True, text=True, timeout=1
        )
        if result.returncode == 0:
            # Use cached game if available and recent
            if _cached_game_name and (current_time - _cached_game_time) < GAME_CACHE_DURATION:
                return {"name": _cached_game_name, "appid": _cached_game_appid}
            return {"name": "SteamOS", "appid": None}
    except Exception:
        pass
    
    # Method 4: GameMode detection
    try:
        result = subprocess.run(
            ['gamemoded', '--status'],
            capture_output=True, text=True, timeout=1
        )
        if 'gamemode is active' in result.stdout.lower():
            # Use cached game if available and recent
            if _cached_game_name and (current_time - _cached_game_time) < GAME_CACHE_DURATION:
                return {"name": _cached_game_name, "appid": _cached_game_appid}
            return {"name": "Gaming (Active)", "appid": None}
    except Exception:
        pass
    
    # Use cache if still valid
    if _cached_game_name and (current_time - _cached_game_time) < GAME_CACHE_DURATION:
        return {"name": _cached_game_name, "appid": _cached_game_appid}
    
    # Clear expired cache
    if _cached_game_name and (current_time - _cached_game_time) >= GAME_CACHE_DURATION:
        _cached_game_name = None
        _cached_game_appid = None
    
    return game_info


# ============================================================
# MAIN FUNCTIONS
# ============================================================

def collect_stats():
    """Collect all system stats"""
    game_info = get_current_game()
    
    return {
        "cpu": {
            "usage": get_cpu_usage(),
            "temp": get_cpu_temp(),
            "frequency": get_cpu_freq(),
            "power": get_cpu_power(),
            "name": get_cpu_name()
        },
        "gpu": {
            **get_gpu_stats(),
            "name": get_gpu_name()
        },
        "ram": get_memory_stats(),
        "disks": get_disk_stats(),
        "fps": get_fps(),
        "game": game_info["name"],
        "appid": game_info["appid"],
        "timestamp": int(time.time())
    }


def send_stats(stats):
    """Send stats to Pi display"""
    try:
        requests.post(PI_URL, json=stats, timeout=1)
        return True
    except requests.exceptions.RequestException:
        return False


def push_orientation_to_pi():
    """Push preferred orientation to Pi on startup if configured"""
    if not PREFERRED_ORIENTATION:
        return
    try:
        resp = requests.post(
            PI_ORIENTATION_URL,
            json={"orientation": PREFERRED_ORIENTATION},
            timeout=3
        )
        if resp.status_code == 200:
            print(f"✓ Pi orientation set to: {PREFERRED_ORIENTATION}")
        else:
            print(f"⚠ Could not set Pi orientation (status {resp.status_code}) - will retry on next start")
    except Exception as e:
        print(f"⚠ Could not reach Pi to set orientation: {e}")


def main():
    """Main loop"""
    
    print(f"Starting Linux PC stats sender v1.0...")
    print(f"Target: {PI_URL}")
    print(f"Update interval: {UPDATE_INTERVAL}s")
    print(f"Game cache duration: {GAME_CACHE_DURATION}s")
    print(f"CPU: {get_cpu_name()}")
    print(f"GPU: {get_gpu_name()}")
    print()

    # Push orientation preference to Pi before starting the send loop
    push_orientation_to_pi()

    consecutive_failures = 0
    
    while True:
        try:
            stats = collect_stats()
            success = send_stats(stats)
            
            if success:
                consecutive_failures = 0
                print(f"✓ {stats['game'][:20]:20} | "
                      f"CPU: {stats['cpu']['usage']:4.1f}% {stats['cpu']['temp']:4.1f}°C | "
                      f"GPU: {stats['gpu']['usage']:3}% {stats['gpu']['temp']:4.1f}°C | "
                      f"RAM: {stats['ram']['percent']:4.1f}% | "
                      f"FPS: {stats['fps']:3}")
            else:
                consecutive_failures += 1
                if consecutive_failures % 10 == 1:
                    print(f"✗ Failed to send stats (Pi unreachable, {consecutive_failures} failures)")
            
            time.sleep(UPDATE_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n✓ Shutting down gracefully...")
            break
        except Exception as e:
            print(f"✗ Error: {e}")
            time.sleep(UPDATE_INTERVAL)


if __name__ == "__main__":
    main()
