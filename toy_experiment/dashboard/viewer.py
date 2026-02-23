#!/usr/bin/env python3
"""
NeoLAT Dashboard Server (Phase 2.1)
=====================================
Serves the real-time analysis dashboard at http://localhost:8765

Structure:
  toy_experiment/
    dashboard/   ← this file + templates/
    sensor/      ← somatic_poc.py, debug_somatic.py
    docs/        ← tutorial.md, research_report.md

Usage:
    sudo python -m toy_experiment.dashboard.viewer   # from project root
    sudo python toy_experiment/dashboard/viewer.py
"""

import http.server
import json
import os
import socketserver
import sys
import threading
import webbrowser

import signal

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from toy_experiment.sensor import verify_tech_spec, inspect_internal_metrics, test_cot

# ── Somatic monitor (optional — requires sudo for powermetrics) ───────────────
try:
    from toy_experiment.sensor.neoray_logger import NeoRay
    _monitor = NeoRay(interval=0.2, output_file="neoray_log.jsonl")
    _monitor.start()
    SOMATIC_OK = True
    print("[NeoRay] Monitor started (200ms)")
except Exception as exc:
    _monitor = None
    SOMATIC_OK = False
    print(f"[NeoRay] Unavailable: {exc}")

# ── Config ────────────────────────────────────────────────────────────────────
PORT = 8765
_TEMPLATE = os.path.join(_HERE, "templates", "dashboard.html")
_FAVICON  = os.path.join(_ROOT, "docs", "assets", "NeoLAT", "NeoLAT_favicon.png")

# ── Model data cache (populated once; /api/refresh forces re-run) ─────────────
_cache_lock = threading.Lock()
_data_cache = None


def _load_template() -> str:
    try:
        with open(_TEMPLATE, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"<h1>Template not found</h1><p>{_TEMPLATE}</p>"


def _collect_model_data() -> dict:
    print("[API] Running model analysis…")
    return {
        "tech_spec": verify_tech_spec.get_tech_spec(),
        "metrics":   inspect_internal_metrics.get_internal_metrics(),
        "cot":       test_cot.run_cot_test(),
    }


def _send_json(handler, payload: dict) -> None:
    data = json.dumps(payload).encode()
    handler.send_response(200)
    handler.send_header("Content-type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(data)


# ── Request handler ───────────────────────────────────────────────────────────
class DashboardHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        p = self.path

        # Favicon / touch icons
        if p in ("/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
            if os.path.exists(_FAVICON):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                with open(_FAVICON, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(204)
                self.end_headers()
            return

        # Dashboard HTML (hot-reload from file)
        if p == "/":
            html = _load_template().encode()
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html)

        # Cached model snapshot
        elif p == "/api/data":
            self._serve_data()

        # Force re-run of model analysis
        elif p == "/api/refresh":
            self._refresh_data()

        # Real-time somatic stream
        elif p.startswith("/api/somatic"):
            self._serve_somatic()

        # Real-time cognitive measurement (streaming TTFT)
        elif p == "/api/cognitive":
            self._serve_cognitive()

        else:
            self.send_error(404)

    def do_POST(self):
        p = self.path
        if p == "/api/config":
            self._handle_config()
        else:
            self.send_error(404)

    # ── API helpers ───────────────────────────────────────────────────────────

    def _serve_data(self):
        global _data_cache
        with _cache_lock:
            if _data_cache is None:
                try:
                    _data_cache = _collect_model_data()
                except Exception as exc:
                    _send_json(self, {"error": str(exc)})
                    return
            else:
                print("[API] Serving cached data.")
        _send_json(self, _data_cache)

    def _refresh_data(self):
        global _data_cache
        try:
            with _cache_lock:
                _data_cache = _collect_model_data()
            _send_json(self, _data_cache)
        except Exception as exc:
            _send_json(self, {"error": str(exc)})

    def _serve_somatic(self):
        # Parse ?since=<timestamp_ns> query param
        since_ns = 0
        if "?" in self.path:
            qs = self.path.split("?", 1)[1]
            for part in qs.split("&"):
                if part.startswith("since="):
                    try:
                        since_ns = int(part[6:])
                    except ValueError:
                        pass

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if _monitor and SOMATIC_OK:
            samples = _monitor.get_data(since_ns)
            def clean(s):
                # Pass through 'clusters', 'process', 'vm', 'power' dicts
                allowed_dicts = {"clusters", "process", "vm", "power"}
                return {
                    k: v for k, v in s.items() 
                    if not isinstance(v, dict) or k in allowed_dicts
                }
            self.wfile.write(json.dumps([clean(s) for s in samples]).encode())
        else:
            self.wfile.write(b"[]")

    def _serve_cognitive(self):
        """Measure TTFT and Energy/Token via streaming Ollama API."""
        import urllib.request, time as _t
        url = "http://localhost:11434/api/generate"
        body = json.dumps({"model": "llama3.2", "prompt": "Why is the sky blue?", "stream": True}).encode()
        result = {"ttft_ms": None, "tps": None, "energy_per_token_mj": None, "error": None}
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            t0 = _t.time()
            token_count = 0
            with urllib.request.urlopen(req, timeout=30) as resp:
                for raw_line in resp:
                    line = raw_line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if result["ttft_ms"] is None and chunk.get("response"):
                        result["ttft_ms"] = round((_t.time() - t0) * 1000, 1)
                    if chunk.get("response"):
                        token_count += 1
                    if chunk.get("done"):
                        elapsed = _t.time() - t0
                        result["tps"] = round(token_count / elapsed, 2) if elapsed > 0 else 0
                        # Energy per token: use latest combined power from NeoRay
                        if _monitor and SOMATIC_OK:
                            samples = _monitor.get_data()
                            if samples:
                                avg_pow = sum(s.get("combined_power_mw", 0) for s in samples[-5:]) / min(5, len(samples))
                                result["energy_per_token_mj"] = round(avg_pow / result["tps"], 2) if result["tps"] else None
                        break
        except Exception as exc:
            result["error"] = str(exc)
        _send_json(self, result)

    def _handle_config(self):
        """POST /api/config  body: {\"interval_ms\": 200|500|1000|2000|5000}"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            interval_ms = int(body.get("interval_ms", 500))
            interval_ms = max(100, min(5000, interval_ms))  # clamp 100-5000ms
            if _monitor and SOMATIC_OK:
                _monitor.set_interval(interval_ms / 1000.0)
            _send_json(self, {"ok": True, "interval_ms": interval_ms})
        except Exception as exc:
            _send_json(self, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        if "/api/somatic" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  NeoLAT Dashboard → http://localhost:{PORT}")
    if not SOMATIC_OK:
        print("  ⚠️  Run with sudo for somatic telemetry")
    print(f"  Ctrl+C to stop")
    print(f"{'='*50}\n")

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("", PORT), DashboardHandler)

    _shutdown_event = threading.Event()

    def _shutdown():
        """Shutdown monitor and HTTP server cleanly."""
        if _monitor:
            _monitor.stop()
        httpd.shutdown()   # unblocks serve_forever()
        httpd.server_close()
        print("[Shutdown] Done.")

    def signal_handler(sig, frame):
        print("\n[Shutdown] Stopping…")
        t = threading.Thread(target=_shutdown, daemon=True)
        t.start()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    webbrowser.open(f"http://localhost:{PORT}")
    try:
        httpd.serve_forever()   # blocks until httpd.shutdown() is called
    except KeyboardInterrupt:
        print("\n[Shutdown] Stopping…")
        _shutdown()

