
import subprocess
import time
import plistlib
import threading
import collections
import datetime
import os
import sys
import re

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[Warning] psutil not available. Install with: pip install psutil")

# ── vm_stat cache proxy ────────────────────────────────────────────────────────
_PAGE_SIZE = 16384  # 16 KB pages on Apple Silicon

_vm_prev = {}
_vm_prev_ts = 0.0

def _parse_vm_stat() -> dict:
    """
    Parses `vm_stat` for cache proxy metrics.
    Returns rates (per-second deltas) where possible.
    """
    global _vm_prev, _vm_prev_ts
    try:
        out = subprocess.check_output(["vm_stat"], text=True, timeout=2)
    except Exception:
        return {}

    now = time.time()
    parsed = {}
    for line in out.splitlines():
        m = re.match(r'^(.+?):\s+([\d]+)\.?$', line.strip())
        if m:
            key = m.group(1).strip().lower().replace(" ", "_").replace('"', '')
            parsed[key] = int(m.group(2))

    result = {}
    dt = now - _vm_prev_ts if _vm_prev_ts else 1.0

    # Rates (delta / dt)
    for key, label in [
        ("translation_faults",       "page_faults_s"),   # L1/L2 miss proxy
        ("pageins",                  "pageins_s"),        # SLC/LRU eviction proxy
        ("compressions",             "compressions_s"),   # Memory pressure proxy
    ]:
        curr = parsed.get(key, 0)
        prev = _vm_prev.get(key, curr)
        result[label] = round(max(0, curr - prev) / dt, 1)

    # Absolute values (pages → MB)
    page_free  = parsed.get("pages_free", 0)
    page_act   = parsed.get("pages_active", 0)
    page_inact = parsed.get("pages_inactive", 0)
    page_comp  = parsed.get("pages_stored_in_compressor", 0)
    result["vm_free_mb"]      = round(page_free  * _PAGE_SIZE / 1024**2, 1)
    result["vm_active_mb"]    = round(page_act   * _PAGE_SIZE / 1024**2, 1)
    result["vm_inactive_mb"]  = round(page_inact * _PAGE_SIZE / 1024**2, 1)
    result["vm_compressed_mb"]= round(page_comp  * _PAGE_SIZE / 1024**2, 1)

    _vm_prev = parsed
    _vm_prev_ts = now
    return result

class SomaticMonitor:
    """
    SomaticMonitor captures hardware telemetry (CPU/GPU power, frequency, etc.)
    using the macOS `powermetrics` tool.

    NOTE: This class requires the script to be run with `sudo` privileges because
    `powermetrics` requires root access.
    """

    # Ring buffer: keep last 300 samples (~75 s at 250 ms interval)
    _MAX_SAMPLES = 300

    def __init__(self, interval_ms=100):
        self.interval_ms = int(interval_ms)
        self.running = False
        self._ring = collections.deque(maxlen=self._MAX_SAMPLES)
        self._ring_lock = threading.Lock()
        self.thread = None
        self.process = None
        self.start_time = None
        self._vm_lock = threading.Lock()
        self._vm_data = {}   # latest vm_stat snapshot
        self._vm_thread = None
        
        # Process monitoring
        self._target_pid = None
        self._target_proc = None
        self._last_pid_scan = 0


    def start(self):
        """Starts the background monitoring thread."""
        if self.running:
            return
        
        # Check for sudo logic if needed, but usually we just fail if not sudo.
        if os.geteuid() != 0:
            print("Warning: SomaticMonitor requires root privileges (sudo) to run `powermetrics`.")
            print("To fix: Run this script with `sudo python ...`")
            print("Attempting to run without sudo (will likely fail)...")

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        self._vm_thread = threading.Thread(target=self._vm_poll_loop, daemon=True)
        self._vm_thread.start()
        print(f"[{datetime.datetime.now().isoformat()}] Somatic Monitor started.")

    def stop(self):
        """Stops the monitoring thread and subprocess."""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except Exception as e:
                print(f"Error stopping powermetrics: {e}")
        
        if self.thread:
            # self.thread.join(timeout=2) # Avoid blocking if thread is stuck reading
            pass
        print(f"[{datetime.datetime.now().isoformat()}] Somatic Monitor stopped.")

    def get_data(self, since_ns: int = 0) -> list:
        """Returns samples newer than since_ns (non-destructive ring buffer read)."""
        with self._ring_lock:
            if since_ns:
                return [s for s in self._ring if s["timestamp"] > since_ns]
            return list(self._ring)

    def _monitor_loop(self):
        # We use stdbuf to unbuffer output if needed, but plist format is typically chunked.
        # cmd = ["sudo", "powermetrics", "-i", str(self.interval_ms), "--format", "plist"]
        
        cmd = [
            "powermetrics",
            "-i", str(self.interval_ms),
            "--format", "plist",
            "--show-extra-power-info"
        ]

        try:
            print(f"[Somatic] Launching: {' '.join(cmd)}")
            # stderr=None lets errors print directly to terminal (no deadlock)
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=None,
                bufsize=0
            )
            
            buffer = b""
            
            while self.running and self.process.poll() is None:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    time.sleep(0.01)
                    continue
                
                buffer += chunk
                
                while b"</plist>" in buffer:
                    end_idx = buffer.find(b"</plist>") + len(b"</plist>")
                    potential_xml = buffer[:end_idx]
                    buffer = buffer[end_idx:]
                    
                    # Robust cleanup: find start of XML
                    start_idx = potential_xml.find(b"<?xml")
                    if start_idx == -1:
                        start_idx = potential_xml.find(b"<plist")
                    
                    if start_idx != -1:
                        xml_data = potential_xml[start_idx:].strip().replace(b'\x00', b'')
                        try:
                            data = plistlib.loads(xml_data)
                            self._process_sample(data)
                            if not hasattr(self, "_first_success"):
                                print(f"[Somatic] FIRST SAMPLE CAPTURED!")
                                self._first_success = True
                        except Exception as e:
                            print(f"[Somatic] Parse error: {e}")
                    else:
                        pass # Corrected from 'passss.terminate()'

        except Exception as e:
            print(f"Critical Error in SomaticMonitor: {e}")
        finally:
            if self.process:
                self.process.terminate()

    def _vm_poll_loop(self):
        """Background thread: polls vm_stat every 2s for cache proxy data."""
        while self.running:
            try:
                data = _parse_vm_stat()
                if data:
                    with self._vm_lock:
                        self._vm_data = data
            except Exception:
                pass
            time.sleep(2.0)

    def _find_target_pid(self):
        """
        Scans for the best target process to monitor.
        Priority 1: 'ollama runner' (Inference Engine - High Memory/Compute)
        Priority 2: 'ollama serve' (API Server)
        """
        now = time.time()
        if now - self._last_pid_scan < 5.0 and self._target_proc and self._target_proc.is_running():
            return

        self._last_pid_scan = now
        best_proc = None
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmd = " ".join(proc.info['cmdline'] or [])
                    if "ollama" in cmd and "runner" in cmd:
                        best_proc = proc
                        break # Found priority 1
                    if "ollama serve" in cmd and best_proc is None:
                        best_proc = proc # Keep looking for runner, but hold this as backup
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            if best_proc:
                if self._target_pid != best_proc.pid:
                    print(f"[Somatic] Locked on target process: {best_proc.pid} ({' '.join(best_proc.info['cmdline'])[:60]}...)")
                    self._target_pid = best_proc.pid
                    self._target_proc = best_proc
            else:
                self._target_pid = None
                self._target_proc = None

        except Exception as e:
            print(f"[Somatic] Error scanning processes: {e}")

    def _get_process_metrics(self):
        """Returns specific metrics for the target process."""
        if not PSUTIL_AVAILABLE: 
            return {}
        
        self._find_target_pid()
        
        if not self._target_proc:
            return {
                "process_rss_gb": 0.0,
                "process_cpu_pct": 0.0
            }

        try:
            # Re-verify running
            if not self._target_proc.is_running():
                self._target_proc = None
                return {"process_rss_gb": 0.0, "process_cpu_pct": 0.0}

            with self._target_proc.oneshot():
                mem = self._target_proc.memory_info()
                cpu = self._target_proc.cpu_percent(interval=None) # Non-blocking immediate
            
            return {
                "process_rss_gb": round(mem.rss / (1024**3), 2),
                "process_cpu_pct": cpu
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._target_proc = None
            return {"process_rss_gb": 0.0, "process_cpu_pct": 0.0}

    def _get_system_memory(self):
        """Returns system-wide memory stats using psutil."""
        if not PSUTIL_AVAILABLE:
            return {}
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return {
            "ram_total_gb":     round(vm.total / (1024**3), 2),
            "ram_used_gb":      round(vm.used  / (1024**3), 2),
            "ram_percent":      vm.percent,
            "ram_available_gb": round(vm.available / (1024**3), 2),
            "swap_used_gb":     round(sw.used / (1024**3), 2),
            "swap_percent":     sw.percent,
        }

    def _process_sample(self, data):
        """
        Extracts relevant fields and puts them into the queue.

        M4 Pro Structure (confirmed via debug):
        - All power values are inside data['processor'], NOT at top level.
        - Keys: cpu_power, gpu_power, ane_power, combined_power (all in mW)
        - Per-cluster info: data['processor']['clusters'] -> list of dicts
        """
        proc = data.get("processor", {})

        # ── Power (mW) ──────────────────────────────────────────────────────
        cpu_power     = float(proc.get("cpu_power",      0.0))
        gpu_power     = float(proc.get("gpu_power",      0.0))
        ane_power     = float(proc.get("ane_power",      0.0))
        combined_power = float(proc.get("combined_power", 0.0))

        # ── Per-Cluster Detail ───────────────────────────────────────────────
        clusters = {}
        for cluster in proc.get("clusters", []):
            name = cluster.get("name", "?")
            clusters[name] = {
                "freq_hz":    cluster.get("freq_hz", 0.0),
                "idle_ratio": cluster.get("idle_ratio", 0.0),
                "down_ratio": cluster.get("down_ratio", 0.0),
                "cpu_count":  len(cluster.get("cpus", [])),
            }

        # ── DRAM/Memory Bandwidth ────────────────────────────────────────────
        # Bandwidth is in bytes/s if present (requires --show-extra-power-info)
        dram_bw_bytes = float(proc.get("dram_bandwidth_Byte/s", 0.0))
        dram_bw_gbs   = round(dram_bw_bytes / (1024**3), 2) if dram_bw_bytes > 0 else None

        # ── Thermal ──────────────────────────────────────────────────────────
        thermal = data.get("thermal_pressure", "Nominal")

        # ── System Memory (psutil) ───────────────────────────────────────────
        # ── System Memory (psutil) ───────────────────────────────────────────
        mem = self._get_system_memory()
        proc_metrics = self._get_process_metrics()


        # ── vm_stat cache proxies ────────────────────────────────────────────
        with self._vm_lock:
            vm = dict(self._vm_data)  # snapshot

        sample = {
            "timestamp":         time.time_ns(),
            "cpu_power_mw":      cpu_power,
            "gpu_power_mw":      gpu_power,
            "ane_power_mw":      ane_power,
            "combined_power_mw": combined_power,
            "dram_bandwidth_gbs": dram_bw_gbs,
            "thermal_pressure":  thermal,
            "clusters":          clusters,
            # psutil memory
            **mem,
            **proc_metrics,
            # vm_stat cache proxies (indirect)

            # vm_stat cache proxies (indirect)
            **vm,
        }

        with self._ring_lock:
            self._ring.append(sample)

if __name__ == "__main__":
    # POC Test
    monitor = SomaticMonitor(interval_ms=100)
    monitor.start()
    try:
        for i in range(5):
            time.sleep(1)
            data = monitor.get_data()
            print(f"Second {i+1}: Captured {len(data)} samples")
            if data:
                print(f"  Sample: {data[-1]}")
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
