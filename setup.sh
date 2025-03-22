#!/bin/bash

# check if sudo exists as it doesn't on RunPod
if command -v sudo 2>&1 >/dev/null
then
    PREFIX="sudo"
else
    PREFIX=""
fi

$PREFIX apt update -y
$PREFIX apt install -y \
    python3-pip \
    nano \
    libgl1 \
    npm

$PREFIX npm install -g pm2@latest

# install repository itself
pip install -e . --use-pep517

# Create miner.env if it doesn't exist
if [ -f "miner.env" ]; then
    echo "File 'miner.env' already exists. Skipping creation."
else
    cat > miner.env << 'EOL'
# Subtensor Network Configuration:
NETUID=                                        # Network UID options: 18, 301
SUBTENSOR_NETWORK=                             # Networks: finney, test, local
SUBTENSOR_CHAIN_ENDPOINT=
                                               # Endpoints:
                                               # - wss://entrypoint-finney.opentensor.ai:443
                                               # - wss://test.finney.opentensor.ai:443/

# Wallet Configuration:
WALLET_NAME=default
WALLET_HOTKEY=default

# Miner Settings:
AXON_PORT=
BLACKLIST_FORCE_VALIDATOR_PERMIT=True          # Default setting to force validator permit for blacklisting
EOL
    echo "File 'miner.env' created."
fi

# Create validator.env if it doesn't exist
if [ -f "validator.env" ]; then
    echo "File 'validator.env' already exists. Skipping creation."
else
    cat > validator.env << 'EOL'
NETUID=                                         # Netuids: 18 (for finney), 301 (for testnet)
SUBTENSOR_NETWORK=                              # Networks: finney, test, local
SUBTENSOR_CHAIN_ENDPOINT=
                                                # Endpoints:
                                                # - wss://entrypoint-finney.opentensor.ai:443
                                                # - wss://test.finney.opentensor.ai:443/

# Wallet Configuration:
WALLET_NAME=default
WALLET_HOTKEY=default

# Validator Port Setting:
AXON_PORT=
PROXY_PORT=

# API Keys:
WANDB_API_KEY=      # https://wandb.ai/authorize
CDS_API_KEY =       # https://github.com/Orpheus-AI/Zeus/blob/main/docs/Validating.md#ecmwf
PROXY_API_KEY=      # Your Proxy API Key, you can generate it yourself
EOL
    echo "File 'validator.env' created."
fi

echo "Environment setup completed successfully."