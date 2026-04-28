# Settlement Toolset for Hermes Agent

On-chain identity (ERC-8004) and Bittensor settlement as a native Hermes toolset.

## Install

```bash
# From the hermes-agent repo root:
cp /path/to/nous-agent/hermes_toolset/settlement_tool.py tools/settlement_tool.py

# Install dependencies
pip install web3 bittensor

# Add to your .env
ERC8004_RPC=http://localhost:8545
ERC8004_PRIVATE_KEY=0x...
BT_NETWORK=test
BT_NETUID=1
```

The toolset auto-registers on import — Hermes discovers it via `tools/registry.py`.

## Tools

| Tool | What it does |
|------|-------------|
| `settlement_register` | Register agent identity on-chain (ERC-8004) |
| `settlement_reputation` | Query reputation from ERC-8004 + Bittensor |
| `settlement_record_task` | Record task completion on-chain |
| `settlement_balance` | Check ETH + TAO balances |
| `settlement_subnet_info` | Query Bittensor subnet metrics |
| `settlement_transfer` | Transfer TAO to another agent |

## Usage in Hermes

Once installed, the tools appear in `hermes tools`:

```
hermes tools            # settlement toolset shows up
hermes                  # start chatting
> register me on-chain  # triggers settlement_register
> what's my reputation? # triggers settlement_reputation
> check my balances     # triggers settlement_balance
```

Or enable the toolset explicitly:

```bash
hermes --toolsets settlement
```

## Toolset definition

Add to `TOOLSETS` in `toolsets.py` if you want it composable:

```python
"settlement": {
    "description": "On-chain identity (ERC-8004) and Bittensor settlement tools",
    "tools": [
        "settlement_register", "settlement_reputation",
        "settlement_record_task", "settlement_balance",
        "settlement_subnet_info", "settlement_transfer",
    ],
    "includes": [],
},
```

## Architecture

```
Hermes Agent
  └── tools/settlement_tool.py  (this toolset)
        └── agent/settlement/erc8004.py  (web3.py → AgentRegistry.sol)
        └── agent/settlement/bittensor.py (bittensor SDK → testnet/finney)
```

The toolset is a thin adapter — all logic lives in the settlement clients.
Hermes gets on-chain capabilities without any changes to its core.

## Requirements

- `web3>=7.0` — for ERC-8004 interactions
- `bittensor>=10.0` — for Bittensor subnet operations
- An EVM node (Anvil for dev, any L1/L2 for prod)
- AgentRegistry contract deployed (see `contracts/`)
