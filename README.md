<div align="center">
  <img src="docs/assets/banner.png" alt="neoLAT - Local Agentic AI Testbed" width="100%">
  
  <p>
    <a href="https://github.com/neomakes/neolat/actions"><img src="https://img.shields.io/github/actions/workflow/status/neomakes/neolat/ci.yml?branch=main&label=build&style=for-the-badge" alt="Build Status"></a>
    <a href="https://github.com/neomakes/neolat/releases"><img src="https://img.shields.io/github/v/release/neomakes/neolat?style=for-the-badge&color=blue" alt="Version"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License"></a>
  </p>
</div>

**neoLAT** is a specialized testbed designed for evaluating and experimenting with Local Agentic AI systems. It provides a robust environment for comparing performance across different local inference engines (MLX-based PyTorch, Ollama) and testing cognitive capabilities on tasks like Sudoku, ARC-1, and ARC-2.

## 🚀 Key Features

- **Local Inference Focus**: Optimized for running powerful models locally on Apple Silicon (via MLX) and other platforms.
- **Modular Architecture**: Clean separation of agents, environments, analysis tools, and core logic.
- **Experimentation Framework**: Integrated with [Hydra](https://hydra.cc/) for configuration management and [WandB](https://wandb.ai/) for experiment tracking.
- **Cognitive Benchmarks**: Includes environments for testing high-level reasoning and problem-solving skills.
- **Documentation First**: Built with extensive MkDocs integration for clear and accessible documentation.

## 📂 Directory Structure

```plaintext
neolat/
├── neolat/                 # Core package source code
│   ├── agents/             # Agent implementations and interfaces
│   ├── analysis/           # Tools for analyzing experiment results
│   ├── core/               # Core configurations and base classes
│   ├── envs/               # Environment definitions (Sensory, Cognitive)
│   └── utils/              # General utility functions
├── docs/                   # Documentation source files (MkDocs)
├── experiments/            # Experiment configurations and scripts
├── results/                # Output directory for artifacts and logs
├── setup_env.sh            # Automated environment setup script
├── mkdocs.yml              # MkDocs configuration
└── requirements.txt        # Python dependencies
```

## 🛠️ Installation & Setup

### Prerequisites

- **Conda**: Anaconda or Miniconda installed on your system.
- **OS**: optimized for macOS (Apple Silicon), but compatible with Linux/Windows.

### Quick Start

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/neomakes/neolat.git
    cd neolat
    ```

2.  **Run the setup script:**
    This script creates a Conda environment named `neolat` (Python 3.11), installs dependencies, and registers the Jupyter kernel.

    ```bash
    chmod +x setup_env.sh
    ./setup_env.sh
    ```

3.  **Activate the environment:**
    ```bash
    conda activate neolat
    ```

## 📖 Usage

### Running Documentation

To view the project documentation locally:

```bash
mkdocs serve
```

Then navigate to `http://127.0.0.1:8000` in your browser.

### Running Experiments

(Instructions for running specific experiments will be added as the framework evolves. Check `experiments/` for available configurations.)

## 🤝 Contributing

Contributions to improve agents, environments, or analysis tools are welcome. Please ensure you update tests and documentation for any new features.

## 📄 License & Copyright

### Source Code

The software source code in this repository is available under the **MIT License**. You are free to use, modify, and distribute the code. See the [LICENSE](LICENSE) file for details.

### Documentation & Assets

All documentation, brand assets, logos, and specific datasets (unless otherwise noted) are **Copyright © 2026 NeoMakes, Inc. All Rights Reserved.** They may not be reproduced, distributed, or used for commercial purposes without explicit written permission.
