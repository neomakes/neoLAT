# NeoLAT Research Report: Toy Experiment Phase

## 🎯 Objective

Developing and validating the core measurement technology for simultaneous Somatic, Introspective, and Behavioral data collection.

## ✅ Completed Milestones

- [x] **Phase 1: Model Preparation & Deep Dive (Complete)**
  - **Setup**: Installed Ollama + `llama3.2` (3B) + Python venv.
  - **CoT Verification**: Confirmed step-by-step reasoning ("Thinking") capability.
  - **Internal Metrics**: Validated access to `eval_count`, `eval_duration`, `context` (KV Cache).
  - **Static Analysis**: Built POC for AST-based architecture scanning.
  - **Architecture Detection**: Added arch-type inference (Transformer Decoder-only, SSM, RNN).
  - **Dashboard**: Implemented `viewer.py` (Web UI) to visualize all metrics.

- [x] **Phase 2.1: Somatic Monitor – Debugging & Structural Discovery (Complete)**
  - **Root Cause Fixed**: Power fields (`cpu_power`, `gpu_power`, `ane_power`) are nested inside `data['processor']` in M4 Pro's `powermetrics` plist.
  - **M4 Pro Cluster Map Confirmed**: E-Cluster (Eff), P0/P1-Cluster (Perf).
  - **Process vs System Metrics**:
    - `psutil` Process CPU % is low (~5-10%) during inference because LLM is **Memory Bound**, causing CPU stalls.
    - However, P-Cluster "Active" ratio is high (~98%), confirming hardware is fully engaged waiting for memory.
  - **Memory Bandwidth**: M4 Pro `powermetrics` output does not expose DRAM bandwidth in plist/text format (returns N/A).

---

## 📚 Documentation

> **See [toy_experiment/tutorial.md](file:///Users/neo/neomakes/neolat/toy_experiment/tutorial.md) for usage guide of all Phase 1 scripts.**

---

## 🔍 Model Deep Dive Findings (Phase 1 Summary)

| Category           | Specification             | Notes                                             |
| :----------------- | :------------------------ | :------------------------------------------------ |
| **Model Family**   | Llama 3.2                 | Transformer (Decoder-only). Optimized for edge.   |
| **Parameters**     | 3.21 Billion              | Low VRAM footprint (~2-3 GB).                     |
| **Context Window** | 131,072 (128k)            | High capacity for long-term memory experiments.   |
| **Quantization**   | Q4_K_M                    | 4-bit quantization (standard speed/size balance). |
| **Runtime**        | Native Binary (Go/C++)    | `ollama_llama_server` process.                    |
| **Capabilities**   | Text Generation, Tool Use | Vision is NOT supported in this 3B variant.       |
| **Avg Speed**      | ~96 tokens/sec            | Measured on M4 Pro MacBook.                       |

---

## 🖥️ Hardware Logging Capability Matrix (M4 Pro)

| Resource                                                                                                                                                                                                                                     | Method                                   | Status                |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | --------------------- |
| CPU Power (mW)                                                                                                                                                                                                                               | `powermetrics` → `processor.cpu_power`   | ✅ Working            |
| GPU Power (mW)                                                                                                                                                                                                                               | `powermetrics` → `processor.gpu_power`   | ✅ Working            |
| ANE Power (mW)                                                                                                                                                                                                                               | `powermetrics` → `processor.ane_power`   | ✅ (0 when idle)      |
| Per-Cluster Frequency                                                                                                                                                                                                                        | `powermetrics` → `clusters[].freq_hz`    | ✅ Working            |
| Per-Cluster Idle Ratio                                                                                                                                                                                                                       | `powermetrics` → `clusters[].idle_ratio` | ✅ Working            |
| Process RAM (RSS)                                                                                                                                                                                                                            | `psutil.Process.memory_info().rss`       | ⏳ To implement       |
| Swap Usage                                                                                                                                                                                                                                   | `psutil.swap_memory()`                   | ⏳ To implement       |
| Disk I/O                                                                                                                                                                                                                                     | `powermetrics` disk sampler              | ✅ Available          |
| Network I/O                                                                                                                                                                                                                                  | `powermetrics` network sampler           | ✅ Available          |
| Thermal Pressure                                                                                                                                                                                                                             | `powermetrics` → `thermal_pressure`      | ✅ Available          |
| Memory Bandwidth (DRAM)                                                                                                                                                                                                                      | `--show-extra-power-info` (unverified)   | ⚠️ To probe           |
| Unified Memory Usage (UMA)                                                                                                                                                                                                                   | `psutil.virtual_memory()`                | ⏳ To implement       |
| > **Note on HBM**: Apple M4 Pro uses **LPDDR5X Unified Memory** (273 GB/s), not HBM. Effect is identical — all weights stream through this bus each token. HBM is for datacenter GPUs (A100/H100). UMA bandwidth is the key bottleneck here. |
| L1/L2/L3 Cache Hit-Rate                                                                                                                                                                                                                      | `kperf` / PMC (SIP restricted)           | ❌ Long-term research |
| Token Throughput                                                                                                                                                                                                                             | Ollama API `eval_count/eval_duration`    | ✅ Phase 1 complete   |
| KV Cache Size                                                                                                                                                                                                                                | Ollama API `context` field               | ✅ Phase 1 complete   |

---

## 📝 Next Steps (Phase 2 continuation)

- [ ] **psutil Integration**: Add RAM RSS, Swap, Process CPU% to `somatic_poc.py`.
- [ ] **DRAM Bandwidth Probe**: Test `powermetrics --show-extra-power-info` for memory metrics.
- [ ] **Cache (Long-term)**: Research `kperf` access under macOS SIP.
- [ ] **Dummy Agent**: Implement a simple mock agent for synchronization testing.
- [ ] **Data Sync Test**: Merge Somatic + Introspective + Behavioral streams.
