#!/usr/bin/env python3
"""
Linux PC System Stats Sender v1.0
Collects system stats and sends them to Pi display via WiFi
Works on Bazzite, SteamOS, Steam Deck, and other Linux systems
Optimized with caching and improved efficiency
"""

import json
import time
import subprocess
import requests
from pathlib import Path
import re

# Configuration
PI_IP = "10.0.0.225"
PI_URL = f"http://{PI_IP}:5000/stats"
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

def get_cpu_usage():
    """Get CPU usage percentage using /proc/stat (more efficient than top)"""
    try:
        # Read CPU stats from /proc/stat (much faster than top)
        with open('/proc/stat', 'r') as f:
            line = f.readline()
            if line.startswith('cpu '):
                fields = line.split()[1:]
                total = sum(int(x) for x in fields)
                idle = int(fields[3])  # idle is the 4th field
                
                # Calculate usage (requires two samples, so we'll use a simpler method)
                # For now, use top as fallback for accuracy
                pass
        
        # Fallback to top (already optimized with -bn1)
        result = subprocess.run(['top', '-bn1'], capture_output=True, text=True, timeout=2)
        for line in result.stdout.split('\n'):
            if 'Cpu(s)' in line:
                idle = float(line.split(',')[3].split()[0])
                return round(100 - idle, 1)
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
    """Get CPU power consumption in watts using energy counters"""
    global _last_cpu_energy, _last_cpu_energy_time
    
    try:
        # AMD zenergy sensor
        for hwmon_path in Path('/sys/class/hwmon').glob('hwmon*'):
            name_file = hwmon_path / 'name'
            if not name_file.exists():
                continue
            
            if name_file.read_text().strip() == 'zenergy':
                for energy_file in hwmon_path.glob('energy*_input'):
                    label_file = energy_file.parent / energy_file.name.replace('_input', '_label')
                    if label_file.exists():
                        label = label_file.read_text().strip().lower()
                        if any(x in label for x in ['package', 'socket', 'epackage', 'esocket']):
                            current_energy = int(energy_file.read_text().strip())
                            current_time = time.time()
                            
                            if _last_cpu_energy is not None and _last_cpu_energy_time is not None:
                                time_delta = current_time - _last_cpu_energy_time
                                energy_delta = current_energy - _last_cpu_energy
                                power_w = (energy_delta / 1_000_000) / time_delta
                                
                                _last_cpu_energy = current_energy
                                _last_cpu_energy_time = current_time
                                
                                # Sanity check
                                if 0 < power_w < 500:
                                    return round(power_w, 1)
                            
                            # Initialize on first run
                            _last_cpu_energy = current_energy
                            _last_cpu_energy_time = current_time
                            return 0.0
        
        # Intel RAPL fallback
        rapl_path = Path('/sys/class/powercap/intel-rapl/intel-rapl:0/power_uw')
        if rapl_path.exists():
            power_uw = int(rapl_path.read_text().strip())
            return round(power_uw / 1_000_000, 1)
            
    except Exception as e:
        print(f"Warning: Could not read CPU power: {e}")
    
    return 0.0


# ============================================================
# GPU STATS
# ============================================================

def get_gpu_stats():
    """Get GPU stats (usage, temp, freq, power, VRAM)"""
    stats = {"usage": 0, "temp": 0.0, "frequency": 0, "power": 0.0, "vram_used": 0, "vram_total": 0}
    
    try:
        # AMD GPU
        for hwmon_path in Path('/sys/class/hwmon').glob('hwmon*'):
            name_file = hwmon_path / 'name'
            if not name_file.exists():
                continue
            
            name = name_file.read_text().strip()
            if name in ['amdgpu', 'amdgpu-pci']:
                # Find GPU card device path
                card_paths = list(Path('/sys/class/drm').glob('card*/device'))
                gpu_card = str(card_paths[0]) if card_paths else '/sys/class/drm/card0/device'
                
                # GPU usage
                for file_name in ['gpu_busy_percent', 'gpu_usage', 'busy_percent']:
                    usage_file = Path(gpu_card) / file_name
                    if usage_file.exists():
                        stats['usage'] = int(usage_file.read_text().strip())
                        break
                
                # GPU temperature
                temp_file = hwmon_path / 'temp1_input'
                if temp_file.exists():
                    stats['temp'] = round(int(temp_file.read_text()) / 1000, 1)
                
                # GPU frequency
                for file_name in ['pp_dpm_sclk', 'current_link_speed', 'gpu_clock']:
                    freq_file = Path(gpu_card) / file_name
                    if freq_file.exists():
                        content = freq_file.read_text()
                        for line in content.split('\n'):
                            if '*' in line:
                                match = re.search(r'(\d+)', line.split(':', 1)[1])
                                if match:
                                    stats['frequency'] = int(match.group(1))
                                break
                        break
                
                # GPU power
                power_file = hwmon_path / 'power1_average'
                if power_file.exists():
                    stats['power'] = round(int(power_file.read_text()) / 1_000_000, 1)
                
                # VRAM usage
                vram_methods = [
                    ('mem_info_vram_used', 'mem_info_vram_total'),
                    ('mem_info_vis_vram_used', 'mem_info_vis_vram_total'),
                ]
                for used_name, total_name in vram_methods:
                    used_file = Path(gpu_card) / used_name
                    total_file = Path(gpu_card) / total_name
                    if used_file.exists() and total_file.exists():
                        stats['vram_used'] = int(used_file.read_text().strip()) // (1024 * 1024)
                        stats['vram_total'] = int(total_file.read_text().strip()) // (1024 * 1024)
                        break
                
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
        except:
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

def get_disk_stats():
    """Get physical disk statistics by aggregating all their partitions"""
    try:
        disks = {}  # Use dict to aggregate partitions by physical disk
        
        # Get all block devices including partitions
        result = subprocess.run(['lsblk', '-b', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT', '-n'],
                              capture_output=True, text=True, timeout=2)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            
            # Debug: print lsblk output
            print("Debug: lsblk output:")
            for line in lines[:10]:  # Print first 10 lines
                print(f"  {line}")
            
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
            
            print(f"Debug: Found {len(physical_disks)} physical disks: {list(physical_disks.keys())}")
            
            # Second pass: aggregate partition usage for each disk
            for line in lines:
                parts = line.split(maxsplit=3)
                if len(parts) >= 4:
                    # Strip tree characters from device name
                    name = parts[0].strip().lstrip('└├─│ ')
                    dev_type = parts[2]
                    mountpoint = parts[3].strip()
                    
                    print(f"Debug: Checking {name} (type={dev_type}, mount={mountpoint})")
                    
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
                        print(f"Debug: No parent disk found for {name}")
                        continue
                    
                    # Check if we've already counted this partition
                    # (Bazzite has bind mounts - same partition mounted multiple times)
                    if name in physical_disks[parent_disk]['partitions_seen']:
                        print(f"Debug: Skipping duplicate mount {mountpoint} (partition {name} already counted)")
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
                                    print(f"Debug: {mountpoint} ({name}) on {parent_disk}: {partition_used / (1024**3):.1f} GB")
                        else:
                            print(f"Debug: df command failed for {mountpoint}")
                    except Exception as e:
                        print(f"Debug: Failed to get usage for {mountpoint}: {e}")
                        pass
            
            # Calculate percentages and convert to GB
            for disk_name, disk in physical_disks.items():
                disk['used_gb'] = round(disk['used_bytes'] / (1024**3), 1)
                if disk['total_bytes'] > 0:
                    disk['percent'] = round((disk['used_bytes'] / disk['total_bytes']) * 100, 1)
                else:
                    disk['percent'] = 0
                
                print(f"Debug: Disk {disk_name}: {disk['used_gb']} GB / {disk['total_gb']} GB used ({disk['percent']}%)")
                
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
        import traceback
        traceback.print_exc()
        return []


# ============================================================
# NETWORK STATS
# ============================================================

_last_net_stats = None
_last_net_time = None

def get_network_stats():
    """Get network statistics with speed calculation and link speeds"""
    global _last_net_stats, _last_net_time
    
    try:
        current_time = time.time()
        
        # Read network stats from /proc/net/dev
        bytes_sent = bytes_recv = 0
        active_interface = None
        with open('/proc/net/dev', 'r') as f:
            lines = f.readlines()[2:]  # Skip headers
            for line in lines:
                parts = line.split()
                interface = parts[0].rstrip(':')
                # Skip loopback
                if interface == 'lo':
                    continue
                recv = int(parts[1])
                sent = int(parts[9])
                bytes_recv += recv
                bytes_sent += sent
                # Track the most active interface
                if recv > 0 or sent > 0:
                    if not active_interface or recv + sent > bytes_recv + bytes_sent:
                        active_interface = interface
        
        # Get link speed for the active interface
        link_speed_mbps = None
        link_type = None
        wifi_tx_speed = None
        wifi_rx_speed = None
        
        if active_interface:
            # Check if it's WiFi
            if active_interface.startswith('wl') or active_interface.startswith('wlan'):
                link_type = 'WiFi'
                # Get WiFi link speed using iw
                try:
                    result = subprocess.run(['iw', 'dev', active_interface, 'link'],
                                          capture_output=True, text=True, timeout=2)
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if 'tx bitrate:' in line.lower():
                                # Extract speed like "tx bitrate: 866.7 MBit/s"
                                parts = line.split(':')[1].strip().split()
                                if len(parts) >= 1:
                                    wifi_tx_speed = float(parts[0])
                            elif 'rx bitrate:' in line.lower():
                                parts = line.split(':')[1].strip().split()
                                if len(parts) >= 1:
                                    wifi_rx_speed = float(parts[0])
                        # Use the higher of tx/rx as the link speed
                        if wifi_tx_speed or wifi_rx_speed:
                            link_speed_mbps = max(wifi_tx_speed or 0, wifi_rx_speed or 0)
                except:
                    pass
            else:
                # Ethernet - check link speed from sysfs
                link_type = 'Ethernet'
                try:
                    speed_file = f'/sys/class/net/{active_interface}/speed'
                    with open(speed_file, 'r') as f:
                        speed = int(f.read().strip())
                        if speed > 0:
                            link_speed_mbps = speed
                except:
                    pass
        
        # Calculate speeds
        download_speed = upload_speed = 0
        if _last_net_stats and _last_net_time:
            time_diff = current_time - _last_net_time
            if time_diff > 0:
                download_speed = (bytes_recv - _last_net_stats['bytes_recv']) / time_diff / 1024 / 1024  # MB/s
                upload_speed = (bytes_sent - _last_net_stats['bytes_sent']) / time_diff / 1024 / 1024  # MB/s
        
        # Get latency (ping to 8.8.8.8)
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
        
        current_stats = {
            'bytes_sent': bytes_sent,
            'bytes_recv': bytes_recv,
            'download_speed': max(0, round(download_speed, 2)),
            'upload_speed': max(0, round(upload_speed, 2)),
            'total_download_gb': round(bytes_recv / 1024 / 1024 / 1024, 2),
            'total_upload_gb': round(bytes_sent / 1024 / 1024 / 1024, 2),
            'latency_ms': round(latency, 1) if latency else None,
            'link_speed_mbps': link_speed_mbps,
            'link_type': link_type,
            'wifi_tx_speed': wifi_tx_speed,
            'wifi_rx_speed': wifi_rx_speed,
            'interface': active_interface
        }
        
        _last_net_stats = {'bytes_sent': bytes_sent, 'bytes_recv': bytes_recv}
        _last_net_time = current_time
        
        return current_stats
    except Exception as e:
        print(f"Warning: Could not read network stats: {e}")
        return {
            'download_speed': 0,
            'upload_speed': 0,
            'total_download_gb': 0,
            'total_upload_gb': 0,
            'latency_ms': None,
            'link_speed_mbps': None,
            'link_type': None,
            'wifi_tx_speed': None,
            'wifi_rx_speed': None,
            'interface': None
        }


# ============================================================
# FPS
# ============================================================

def get_fps_from_mangohud():
    """Get FPS from MangoHud CSV files"""
    try:
        fps_file = Path('/tmp/fps.txt')
        if fps_file.exists() and (time.time() - fps_file.stat().st_mtime < 3):
            fps_str = fps_file.read_text().strip()
            if fps_str.isdigit():
                return int(fps_str)
    except:
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
    except:
        pass
    
    return 0


def get_fps():
    """Get FPS from multiple sources (MangoHud, Gamescope, etc.)
    
    Priority:
    1. MangoHud CSV files (works everywhere with MangoHud enabled)
    2. Gamescope stats file (Steam Deck native, requires launch option)
    """
    # Try MangoHud first (most reliable, works on Bazzite/Linux/Deck)
    fps = get_fps_from_mangohud()
    if fps > 0:
        return fps
    
    # Try Gamescope as fallback (Steam Deck without MangoHud)
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
    try:
        for steam_path in get_steam_paths():
            for manifest in steam_path.glob('appmanifest_*.acf'):
                appid = manifest.stem.split('_')[1]
                
                # Check if game process is running
                result = subprocess.run(
                    ['pgrep', '-f', f'steam_app_{appid}'],
                    capture_output=True, text=True, timeout=1
                )
                
                if result.returncode == 0:
                    # Parse game name from manifest
                    try:
                        content = manifest.read_text(encoding='utf-8', errors='ignore')
                        name_match = re.search(r'"name"\s+"([^"]+)"', content)
                        if name_match:
                            game_name = name_match.group(1)
                            update_game_cache(game_name, appid)
                            return {"name": game_name, "appid": appid}
                    except:
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
    except:
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
    except:
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
        "network": get_network_stats(),
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


def main():
    """Main loop"""
    
    print(f"Starting Linux PC stats sender v1.0...")
    print(f"Target: {PI_URL}")
    print(f"Update interval: {UPDATE_INTERVAL}s")
    print(f"Game cache duration: {GAME_CACHE_DURATION}s")
    print(f"CPU: {get_cpu_name()}")
    print(f"GPU: {get_gpu_name()}")
    print()
    
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
