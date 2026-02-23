# NeoLAT Toy Experiment: Tutorial & Reference Guide

> **Run all commands from the project root:** `/Users/neo/neomakes/neolat`

---

## 🧠 Conceptual Framework: HW Resources as Cognitive Analogies

NeoLAT treats hardware metrics as a "body" for the AI — a Somatic layer that underpins all cognitive activity. Each hardware resource maps to a cognitive analog:

| HW Resource               | Cognitive Analog                                                           | Metric               | Logged By         |
| ------------------------- | -------------------------------------------------------------------------- | -------------------- | ----------------- |
| **CPU Power** (P-Cluster) | _Focused Thinking_ — deliberate, effortful reasoning                       | `cpu_power_mw` (mW)  | `powermetrics` ✅ |
| **CPU Power** (E-Cluster) | _Automatic Processing_ — background maintenance tasks                      | cluster `idle_ratio` | `powermetrics` ✅ |
| **GPU Power**             | _Parallel Visual Processing_ — simultaneous pattern matching               | `gpu_power_mw` (mW)  | `powermetrics` ✅ |
| **ANE Power**             | _Intuitive / Reflex Response_ — fast, quantized shortcuts                  | `ane_power_mw` (mW)  | `powermetrics` ✅ |
| **L1/L2 Cache**           | _Working Memory_ — the small, ultra-fast scratchpad for current thought    | (proxy via vm_stat)  | ⚠️ Indirect       |
| **SLC (L3 Cache)**        | _Short-Term Memory_ — recently used concepts held "nearby"                 | (proxy via vm_stat)  | ⚠️ Indirect       |
| **Unified Memory (UMA)**  | _Long-Term Memory_ — the full weight matrix, analogous to stored knowledge | `ram_used_gb` (GB)   | `psutil` ✅       |
| **Memory Bandwidth**      | _Reading Speed_ — how fast the brain can retrieve stored knowledge         | N/A (M4 Pro hidden)  | ❌ Hidden on M4   |
| **Thermal Pressure**      | _Cognitive Fatigue_ — system throttles under sustained load                | `thermal_pressure`   | `powermetrics` ✅ |
| **Token/s (eval_count)**  | _Thought Speed_ — how fast ideas are formed                                | `tps`                | Ollama API ✅     |
| **KV Cache (context)**    | _Attention Span_ — how much is actively held "in mind"                     | `context_size`       | Ollama API ✅     |

### 📌 Measurement Scope: Hybrid Approach

We use a **Hybrid Monitoring Strategy** to capture the full picture:

1.  **System-Wide (The Body)**: `powermetrics` captures the entire M4 Pro chip's power, thermal state, and cluster activity. We cannot isolate "only" the AI's power, just as you cannot isolate the brain's glucose usage from the body's without invasive tools.
2.  **Process-Specific (The Neural Activity)**: `psutil` tracks the specific `ollama runner` process for:
    - **RSS Memory**: The actual physical RAM holding the model weights.
    - **Process CPU%**: The instruction load. _Note: this is often low (~10%) during inference because LLMs are **Memory Bound**, waiting on data rather than crunching numbers, even while the HW cores remain "Active"._

### Indirect Cache Metrics (Why vm_stat vs kperf?)

- **vm_stat (Current)**: Tracks OS-level page faults. Good for checking OOM/Swap issues, but useless for cache performance once the model is loaded in RAM.
- **kperf (Future Goal)**: Will track CPU L1/L2 cache misses. This is the true metric for "efficiency" but requires bypassing macOS SIP (System Integrity Protection).

---

## 📂 Script Reference

| File / Module                        | Purpose                                                                                           | Key Functions / Classes                 | Target Data/Metrics (연동 대상 데이터)                                                                                                                        | Category        |
| :----------------------------------- | :------------------------------------------------------------------------------------------------ | :-------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------ | :-------------- |
| `sensor/inspect_model.py`            | Extracts model configurations from the Modelfile.                                                 | `inspect_model_config()`                | Hyperparameters (temperature, top_k), System Prompt                                                                                                           | Model Analysis  |
| `sensor/inspect_internal_metrics.py` | Queries local API to gather internal inference metrics.                                           | `get_internal_metrics()`                | `eval_count`, `eval_duration` (TPS), `context` (KV Cache size), Latency breakdown (`load_duration`, `prompt_eval_duration`)                                   | Model Analysis  |
| `sensor/test_cot.py`                 | Verifies Chain-of-Thought reasoning.                                                              | `run_cot_test()`                        | Response text, reasoning keywords ("step", "first", "then"), API duration                                                                                     | Model Analysis  |
| `sensor/verify_tech_spec.py`         | Audits hardware context, inference runtime, capabilities, and architecture details.               | `get_tech_spec()`                       | Hardware (Camera, Mic), Process info (`ollama runner`), Architecture (Parameters, Context Window, Quantization, Layer count)                                  | Model Analysis  |
| `sensor/static_analyzer.py`          | Performs AST-based static analysis to detect NLP architectures and dependencies.                  | `ModelCodeAnalyzer`, `scan_directory()` | Language breakdown, imported libraries, acceleration flags (CUDA, MPS), Transformer block candidates                                                          | Code Analysis   |
| `sensor/neoray_logger.py`            | Advanced real-time hardware telemetry logger via `powermetrics` and `vm_stat`.                    | `NeoRay` class                          | CPU/GPU/ANE/Combined Power (mW), Thermal Pressure, Cluster Idle Ratios, RAM/Swap usage, VM proxy metrics (Translation faults, pageins/outs, compressed pages) | Somatic Monitor |
| `sensor/somatic_poc.py`              | Initial proof-of-concept for real-time hardware telemetry and process-specific memory monitoring. | `SomaticMonitor` class                  | CPU/GPU/ANE/Combined Power, Cluster active/idle ratios, Target Process RSS Memory (GB) and CPU %, VM stats                                                    | Somatic Monitor |
| `sensor/debug_somatic.py`            | Debugging script to dump raw `powermetrics` plist structures for M4 Pro chips.                    | `debug_m4_power()`                      | Raw dictionaries of `powermetrics` output (CPU, GPU, ANE, disks, thermal, etc.)                                                                               | Debug / Utils   |
| `sensor/debug_vm.py`                 | Debugging script to parse and calculate memory metrics from macOS `vm_stat` output.               | `test_vmstat_parsing()`                 | Raw macOS virtual memory stats (Pageins, Pageouts, Faults, Compressed pages)                                                                                  | Debug / Utils   |
| `dashboard/viewer.py`                | Local HTTP server providing a real-time web dashboard.                                            | `DashboardHandler`, `_serve_somatic()`  | Serves the collected Somatic data (power, RAM) and generates Cognitive data (TTFT, TPS, energy_per_token_mj) via live API calls                               | Web Dashboard   |
| `sensor/dummy_model_code.py`         | A simple dummy target file containing PyTorch code to test the `static_analyzer.py`.              | `MyCustomTransformer`, `SimpleNet`      | AST Parsable structures (`nn.Module`, `MultiheadAttention`, etc.)                                                                                             | Test / Mock     |

---

## 🚀 Usage Guide

### 1. Model Verification (Phase 1)

```bash
python toy_experiment/sensor/verify_tech_spec.py   # Architecture info
python toy_experiment/sensor/inspect_model.py       # Hyperparameters
python toy_experiment/sensor/inspect_internal_metrics.py  # Throughput baseline
python toy_experiment/sensor/test_cot.py           # Chain-of-Thought check
```

### 2. Somatic Monitor — Real-Time HW Telemetry

⚠️ **Requires `sudo`** — `powermetrics` needs root access.

```bash
sudo python toy_experiment/sensor/somatic_poc.py
```

**Outputs per sample (~10 Hz)**:

- `cpu_power_mw`: Combined CPU power draw (E + P clusters)
- `combined_power_mw`: Total SoC power draw
- `process_rss_gb`: **Ollama Process** distinct physical memory usage
- `clusters`: Per-cluster frequency and idle ratio (E, P0, P1)

**M4 Pro Cluster Map**:

```
E-Cluster  (CPU 0-3):  Efficiency cores — always on,  ~1 GHz
P0-Cluster (CPU 4-8):  Performance cores — power-gated when idle
P1-Cluster (CPU 9-13): Performance cores — active under LLM load, ~2-4 GHz
```

### 3. Live Dashboard

Launches a web UI at `http://localhost:8765` with:

- Static model specs (Phase 1 results)
- **Real-time time-series charts**: CPU Power, GPU Power, RAM Usage, Cluster Activity
- **Process Footprint**: Specific Ollama CPU/RAM usage

```bash
sudo python toy_experiment/dashboard/viewer.py
```

> **Without sudo**: The dashboard loads but somatic charts will show no data (powermetrics blocked).

---

## 🔬 Metric Interpretation Guide

| Metric            | Idle       | LLM Inference (3B)      | High Load            | Context         |
| ----------------- | ---------- | ----------------------- | -------------------- | --------------- |
| `cpu_power_mw`    | 150–250 mW | 300–800 mW              | >1000 mW             | System Body     |
| `gpu_power_mw`    | 0 mW       | 0–50 mW (CPU inference) | >1000 mW             | System Body     |
| `process_rss_gb`  | 0 GB       | ~2.2 GB (3B Q4)         | Model dependent      | Neural Activity |
| `process_cpu_pct` | 0%         | ~5-15%                  | >80% (Compute bound) | Neural Activity |
| `ram_percent`     | ~50–60%    | +2–5% (model loaded)    | >85% = pressure      | System Body     |
| `swap_used_gb`    | 0          | 0 (fits in RAM)         | >0 = warn            | System Body     |
