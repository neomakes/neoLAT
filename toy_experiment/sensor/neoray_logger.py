
import time
import subprocess
import threading
import psutil
import datetime
import json
import re
import os
import plistlib
from collections import deque

class NeoRay:
    def __init__(self, interval=0.2, output_file="neoray_log.jsonl", max_samples=300):
        self.interval = interval
        
        # Determine the log directory based on current date
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # toy_experiment
        log_dir = os.path.join(base_dir, "logs", today_str)
        os.makedirs(log_dir, exist_ok=True)
        
        # Support both absolute paths (from user) and basenames
        filename = os.path.basename(output_file)
        self.output_file = os.path.join(log_dir, filename)
        
        self.running = False
        self.lock = threading.Lock()
        
        # Data Buffers (Latest snapshots)
        self.power_data = {} 
        self.vm_data = {}    
        
        # Live Ring Buffer for Dashboard
        self.ring_buffer = deque(maxlen=max_samples)
        self.ring_lock = threading.Lock()
        
        # Threads
        self.threads = []
        self.pm_process = None
        
        # Powermetrics Parser Regex
        self.re_power = re.compile(r"Combined Power \(CPU \+ GPU \+ ANE\): (\d+) mW")
        self.re_cpu = re.compile(r"CPU Power: (\d+) mW")
        self.re_gpu = re.compile(r"GPU Power: (\d+) mW")
        self.re_ane = re.compile(r"ANE Power: (\d+) mW")
        
        self.target_pid = self._find_target_pid()
        self.target_proc = None
        if self.target_pid:
            print(f"[NeoRay] locked on PID {self.target_pid}")
            try:
                self.target_proc = psutil.Process(self.target_pid)
            except: pass
        else:
            print("[NeoRay] Warning: Target process not found at startup")

    def _find_target_pid(self):
        # Prioritize runner, fall back to server
        target_runner = None
        target_serve = None
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # cmdline is a list [argv0, argv1, ...]. Join it carefully.
                cmd_list = proc.info['cmdline'] or []
                cmd_str = " ".join(cmd_list)
                
                # Check for runner (most important)
                # Matches: /opt/homebrew/.../ollama runner --model ...
                if "ollama" in cmd_str and "runner" in cmd_str:
                    target_runner = proc.pid
                    break # Found the runner, stop searching
                
                # Check for server as fallback
                if "ollama" in cmd_str and "serve" in cmd_str:
                    target_serve = proc.pid
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        return target_runner if target_runner else target_serve

    def _monitor_powermetrics(self):
        # Requires Sudo. Using XML format for robustness on M4 Pro.
        if os.geteuid() == 0:
            cmd = ["powermetrics"]
        else:
            cmd = ["sudo", "powermetrics"]
            
        cmd.extend([
            "-f", "plist", # Force plist/XML output
            "-i", str(int(self.interval * 1000)),
            "--samplers", "cpu_power,gpu_power,thermal", 
            "--show-extra-power-info" 
        ])
        
        try:
            self.pm_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
            )
        except PermissionError:
            print("[NeoRay] Error: Sudo required for powermetrics")
            return
        except Exception as e:
            print(f"[NeoRay] Error launching powermetrics: {e}")
            return

        buffer = b""
        
        while self.running:
            if self.pm_process.poll() is not None:
                print("[NeoRay] powermetrics exited unexpectedly")
                break
                
            chunk = self.pm_process.stdout.read(4096)
            if not chunk: 
                break
            
            buffer += chunk
            
            while b"</plist>" in buffer:
                end_idx = buffer.find(b"</plist>") + len(b"</plist>")
                potential_xml = buffer[:end_idx]
                buffer = buffer[end_idx:]
                
                # Robust cleanup: find start of XML
                start_idx = potential_xml.find(b"<plist")
                if start_idx == -1:
                    start_idx = potential_xml.find(b"<?xml")
                
                if start_idx != -1:
                    xml_data = potential_xml[start_idx:].strip().replace(b'\x00', b'')
                    try:
                        data = plistlib.loads(xml_data)
                        self._process_xml_sample(data)
                    except Exception as e:
                         # print(f"[NeoRay] XML Parse Error: {e}", flush=True)
                         pass
                else:
                    pass

        # Cleanup handled in stop(), but just in case loop exits naturally
        if self.pm_process:
            self.pm_process.terminate()

    def _process_xml_sample(self, data):
        """Extracts metrics from parsed plist data."""
        sample = {}
        
        # Power (M4 Pro plist uses combined_power/cpu_power in mW directly)
        proc = data.get("processor", {})
        
        # Power (M4 Pro plist uses combined_power/cpu_power in mW directly)
        proc = data.get("processor", {})
        
        # Try processor dict first, then root data
        def get_pow(key, alt_key=None):
            val = proc.get(key)
            if val is None: val = data.get(key)
            if val is None and alt_key: val = proc.get(alt_key)
            if val is None and alt_key: val = data.get(alt_key)
            return int(val) if val is not None else 0

        # Note: combined_power is already mW in plist. package_watts is W.
        # We try both for compatibility.
        
        # Combined
        if "combined_power" in proc or "combined_power" in data:
            sample["combined_pow_mw"] = get_pow("combined_power")
        else:
            sample["combined_pow_mw"] = int(get_pow("package_watts") * 1000)
            
        # CPU
        if "cpu_power" in proc or "cpu_power" in data:
            sample["cpu_pow_mw"] = get_pow("cpu_power")
        else:
            sample["cpu_pow_mw"] = int(get_pow("cpu_watts") * 1000)

        # GPU
        if "gpu_power" in proc or "gpu_power" in data:
             sample["gpu_pow_mw"] = get_pow("gpu_power")
        else:
             sample["gpu_pow_mw"] = int(get_pow("gpu_watts") * 1000)

        # ANE
        if "ane_power" in proc or "ane_power" in data:
            sample["ane_pow_mw"] = get_pow("ane_power")
        else:
            sample["ane_pow_mw"] = int(get_pow("ane_watts") * 1000)
        
        # Thermal
        sample["thermal"] = data.get("thermal_pressure", "Nominal")

        # Clusters (M4 Pro)
        # Structure: processor -> clusters -> [ {name: "E-Cluster", idle_ratio: 0.x}, ... ]
        clusters = {}
        if "clusters" in proc:
            for c in proc["clusters"]:
                name = c.get("name", "Unknown")
                idle = c.get("idle_ratio", 1.0)
                clusters[name] = {"idle_ratio": idle}
        sample["clusters"] = clusters

        # DRAM Bandwidth (if available)
        # M4 Pro likely doesn't expose this via powermetrics public sampler yet
        # But we check anyway. Check for 'dram_bandwidth_Byte/s' or similar
        # Based on somatic_poc.py findings, it wasn't there.
        
        with self.lock:
            self.power_data = sample

    def _monitor_vmstat(self):
        last_sample = {}
        last_ts = 0
        
        while self.running:
            try:
                out = subprocess.check_output(["vm_stat"], text=True)
                sample = {}
                for line in out.splitlines():
                    if "Pageouts" in line: sample["pageouts"] = int(line.split(":")[1].strip().strip('.'))
                    if "Pageins" in line: sample["pageins"] = int(line.split(":")[1].strip().strip('.'))
                    if "COW-faults" in line: sample["cow_faults"] = int(line.split(":")[1].strip().strip('.'))
                    # "Translation faults": 68393476.
                    if "Translation faults" in line: sample["faults"] = int(line.split(":")[1].strip().strip('.'))
                    # "Pages stored in compressor": 273549.
                    if "Pages stored in compressor" in line: sample["compressed_pages"] = int(line.split(":")[1].strip().strip('.'))

                # Memory Pressure: 0=Normal, 1=Warning, 2=Urgent, 3=Critical
                try:
                    mp_out = subprocess.check_output(["sysctl", "vm.memory_pressure"], text=True)
                    sample["memory_pressure"] = int(mp_out.split(":")[1].strip())
                except: sample["memory_pressure"] = 0
                
                now = time.time()
                rates = {}
                
                if last_sample and last_ts > 0:
                    dt = now - last_ts
                    if dt > 0:
                        rates["pageins_s"] = round((sample.get("pageins", 0) - last_sample.get("pageins", 0)) / dt, 1)
                        rates["pageouts_s"] = round((sample.get("pageouts", 0) - last_sample.get("pageouts", 0)) / dt, 1)
                        rates["cow_faults_s"] = round((sample.get("cow_faults", 0) - last_sample.get("cow_faults", 0)) / dt, 1)
                
                # Add absolute values for Dashboard
                # Compressed Pages to MB (assuming 16KB page size for Apple Silicon, usually 16384 bytes)
                # vm_stat output says: "Mach Virtual Memory Statistics: (page size of 16384 bytes)" usually on M-series.
                # Let's verify page size dynamically if possible, or assume 16KB (standard for M1/M2/M3/M4).
                page_size = 16384 # M-series standard
                
                if "compressed_pages" in sample:
                    # compressed_pages * 16KB / 1024 / 1024 = MB
                    compressed_mb = (sample["compressed_pages"] * page_size) / (1024**2)
                    sample["compressed_mb"] = round(compressed_mb, 0)
                else:
                    sample["compressed_mb"] = 0

                if last_sample and last_ts > 0:
                    dt = now - last_ts
                    if dt > 0:
                        rates["pageins_s"] = round((sample.get("pageins", 0) - last_sample.get("pageins", 0)) / dt, 1)
                        rates["pageouts_s"] = round((sample.get("pageouts", 0) - last_sample.get("pageouts", 0)) / dt, 1)
                        rates["cow_faults_s"] = round((sample.get("cow_faults", 0) - last_sample.get("cow_faults", 0)) / dt, 1)
                        rates["faults_s"] = round((sample.get("faults", 0) - last_sample.get("faults", 0)) / dt, 1)

                # Persist absolute values in rates dict for passing to main loop (hacky but effective)
                rates["compressed_mb"] = sample.get("compressed_mb", 0)

                rates["memory_pressure"] = sample.get("memory_pressure", 0)

                last_sample = sample
                last_ts = now
                
                with self.lock:
                    self.vm_data = rates
            except: pass
            time.sleep(self.interval)

    def _aggregation_loop(self):
        print(f"[NeoRay] Logging to {self.output_file}...")
        try:
            with open(self.output_file, "a") as f:
                while self.running:
                    start_ts = time.time()
                    
                    # 0. Retrieve Latest Snapshots (moved up for dependency)
                    with self.lock:
                        p_sample = self.power_data.copy()
                        v_sample = self.vm_data.copy()

                    # 1. Process Metrics (psutil) - Persisted Object
                    proc_sample = {"cpu_pct": 0, "rss_gb": 0}
                    if not self.target_pid:
                        # Runner wasn't present at startup — keep scanning
                        self.target_pid = self._find_target_pid()
                        if self.target_pid:
                            print(f"[NeoRay] Locked on PID {self.target_pid} (late discovery)")
                            try:
                                self.target_proc = psutil.Process(self.target_pid)
                            except: pass
                    if self.target_pid:
                        try:
                            if not self.target_proc or self.target_proc.pid != self.target_pid:
                                self.target_proc = psutil.Process(self.target_pid)
                            
                            with self.target_proc.oneshot():
                                proc_sample["cpu_pct"] = self.target_proc.cpu_percent(interval=None) 
                                proc_sample["rss_gb"] = round(self.target_proc.memory_info().rss / (1024**3), 3)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            self.target_pid = self._find_target_pid()
                            self.target_proc = None
                    
                    # 1b. System Memory (UMA)
                    mem = psutil.virtual_memory()
                    swap = psutil.swap_memory()
                    
                    # MacOS specific fields (available in psutil)
                    # active, inactive, wired. compressed might be missing in standard psutil
                    
                    sys_mem = {
                        "ram_total_gb": round(mem.total / (1024**3), 2),
                        "ram_used_gb": round(mem.used / (1024**3), 2),
                        "ram_available_gb": round(mem.available / (1024**3), 2),
                        "ram_percent": mem.percent,
                        "swap_used_gb": round(swap.used / (1024**3), 2),
                        # Extended fields for Cache Proxy Card
                        "vm_active_mb": round((getattr(mem, 'active', 0)) / (1024**2), 0),
                        "vm_inactive_mb": round((getattr(mem, 'inactive', 0)) / (1024**2), 0),
                        "vm_wired_mb": round((getattr(mem, 'wired', 0)) / (1024**2), 0),
                        "vm_compressed_mb": v_sample.get("compressed_mb", 0) 
                    }

                    # 3. Combine
                    record = {
                        "timestamp": int(start_ts * 1e9),
                        "process": proc_sample,
                        "power": p_sample,
                        "vm": v_sample,
                        # Flattened System Memory for Dashboard
                        "ram_total_gb": sys_mem["ram_total_gb"],
                        "ram_used_gb": sys_mem["ram_used_gb"],
                        "ram_available_gb": sys_mem["ram_available_gb"],
                        "ram_percent": sys_mem["ram_percent"],
                        "swap_used_gb": sys_mem["swap_used_gb"],
                        # Compatibility keys
                        "cpu_power_mw": p_sample.get("cpu_pow_mw", 0),
                        "gpu_power_mw": p_sample.get("gpu_pow_mw", 0),
                        "ane_power_mw": p_sample.get("ane_pow_mw", 0),
                        "combined_power_mw": p_sample.get("combined_pow_mw", 0),
                        "thermal_pressure": p_sample.get("thermal", "Nominal"),
                        "clusters": p_sample.get("clusters", {}),
                        
                        # Cache Proxy Extra Fields
                        "vm_active_mb": sys_mem["vm_active_mb"],
                        "vm_inactive_mb": sys_mem["vm_inactive_mb"],
                        "vm_compressed_mb": sys_mem["vm_compressed_mb"],
                        
                        "page_faults_s": v_sample.get("faults_s", 0), # L1/L2 miss proxy (Translation faults)
                        "pageins_s": v_sample.get("pageins_s", 0),
                        "pageouts_s": v_sample.get("pageouts_s", 0),
                        "cow_faults_s": v_sample.get("cow_faults_s", 0),
                        "memory_pressure": v_sample.get("memory_pressure", 0),
                        "dram_bandwidth_gbs": None # M4 Pro doesn't expose this yet via powermetrics default samplers
                    }
                    
                    # 4. Persistence
                    f.write(json.dumps(record) + "\n")
                    f.flush()
                    
                    # 5. Live View
                    with self.ring_lock:
                        self.ring_buffer.append(record)
                    
                    elapsed = time.time() - start_ts
                    sleep_time = max(0, self.interval - elapsed)
                    time.sleep(sleep_time)

        except Exception as e:
            print(f"[NeoRay] Aggregation error: {e}")

    def start(self):
        if self.running: return
        self.running = True
        
        # Spawn all threads
        self.threads = [
            threading.Thread(target=self._monitor_powermetrics, daemon=True),
            threading.Thread(target=self._monitor_vmstat, daemon=True),
            threading.Thread(target=self._aggregation_loop, daemon=True)
        ]
        
        for t in self.threads:
            t.start()

        # Warm-up: prime cpu_percent so the first interval returns a real delta
        if self.target_proc:
            try:
                self.target_proc.cpu_percent(interval=None)
            except: pass
            
    def set_interval(self, interval_s: float):
        """Dynamically update sampling interval by restarting powermetrics."""
        self.interval = interval_s
        if self.pm_process:
            try:
                self.pm_process.terminate()
                self.pm_process.wait(timeout=1)
            except:
                try: self.pm_process.kill()
                except: pass
            self.pm_process = None
        # Restart powermetrics thread with new interval
        t = threading.Thread(target=self._monitor_powermetrics, daemon=True)
        t.start()
        self.threads.append(t)
        print(f"[NeoRay] Interval updated to {interval_s*1000:.0f}ms")

    def stop(self):
        self.running = False
        if self.pm_process:
            try:
                self.pm_process.terminate()
                self.pm_process.wait(timeout=1)
            except:
                try:
                    self.pm_process.kill()
                except: pass
        print("[NeoRay] Monitor stopped")

    def get_data(self, since_ns=0):
        with self.ring_lock:
            if since_ns == 0:
                return list(self.ring_buffer)
            return [s for s in self.ring_buffer if s["timestamp"] > since_ns]

if __name__ == "__main__":
    xr = NeoRay()
    xr.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        xr.stop()
        print("\n[NeoRay] Stopped.")
