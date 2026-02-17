#!/bin/bash
set -e

# Configuration
ENV_NAME="neolat"
PYTHON_VERSION="3.11"

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Conda Environment Setup...${NC}"

# Check for Conda
if ! command -v conda &> /dev/null; then
    echo "Conda could not be found. Please install Anaconda or Miniconda."
    exit 1
fi

# Create Conda Environment
if conda info --envs | grep -q "$ENV_NAME"; then
    echo -e "${GREEN}Conda environment '$ENV_NAME' already exists.${NC}"
else
    echo -e "${GREEN}Creating Conda environment '$ENV_NAME' with Python $PYTHON_VERSION...${NC}"
    conda create -n $ENV_NAME python=$PYTHON_VERSION -y
fi

# Install Dependencies using conda run
echo -e "${GREEN}Installing dependencies in '$ENV_NAME'...${NC}"
# We use conda run to execute pip inside the environment without activating it in the shell
conda run -n $ENV_NAME pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    conda run -n $ENV_NAME pip install -r requirements.txt
    conda run -n $ENV_NAME pip install -e ".[dev]"
else
    echo "requirements.txt not found!"
    exit 1
fi

# Register Kernel
echo -e "${GREEN}Registering Jupyter Kernel...${NC}"
conda run -n $ENV_NAME python -m ipykernel install --user --name=$ENV_NAME --display-name "Python ($ENV_NAME)"

echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}To activate the environment, run:${NC}"
echo -e "    conda activate $ENV_NAME"
