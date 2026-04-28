# nous-agent

Reference autonomous agent: Hermes brain, ERC-8004 identity, Bittensor settlement.

![Demo](demo/nous-demo.gif)

## Stack

| Layer | What | Why |
|-------|------|-----|
| **Hermes** | Reasoning core | Open-weight, Nous Research, OpenAI-compatible endpoint |
| **ERC-8004** | On-chain identity & reputation | Ethereum standard for agent registries |
| **Bittensor** | TAO rewards, subnet participation | Native incentive substrate — no bridging |
| **A2A** | Agent-to-agent protocol | Linux Foundation standard, JSON-RPC over HTTP |

## Architecture

```
agent/
  core/           Agent orchestrator, wallet, keystore
  daemon/         Hermes LLM interface (fallback ladder: Hermes > Ollama > OpenAI > mock)
  settlement/     SettlementClient ABC + ERC-8004 + Bittensor implementations
  transport/      A2A-over-HTTP (direct agent communication)
  skills/         Pluggable skill SDK (settlement, agent, meta skills)

contracts/
  src/            AgentRegistry.sol — ERC-8004 identity + reputation contract

hermes_toolset/
  settlement_tool.py  — Drop-in toolset for Hermes Agent (6 tools)
```

## Demo

The demo runs all three backends live — no mocks:

- **ERC-8004**: On-chain registration, task recording, reputation queries (Anvil/Foundry)
- **Bittensor**: Testnet connection, subnet metagraph queries (testnet block 7M+)
- **Hermes**: Real inference via Ollama/hermes3:8b

```bash
# Start Anvil + deploy contract
anvil &
cd contracts && forge create src/AgentRegistry.sol:AgentRegistry \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast

# Run the demo
ERC8004_PRIVATE_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80" \
  python scripts/demo_e2e.py
```

## Hermes Agent Integration

The `hermes_toolset/` directory contains a drop-in toolset for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Copy `settlement_tool.py` into `hermes-agent/tools/` and it auto-registers 6 tools:

| Tool | What |
|------|------|
| `settlement_register` | Register identity on-chain (ERC-8004) |
| `settlement_reputation` | Query on-chain reputation |
| `settlement_record_task` | Record task completion |
| `settlement_balance` | Check ETH + TAO balances |
| `settlement_subnet_info` | Query Bittensor subnet metrics |
| `settlement_transfer` | Transfer TAO natively |

See [`hermes_toolset/README.md`](hermes_toolset/README.md) for setup.

## Quick start

```bash
pip install web3 httpx bittensor

# Option 1: Use Ollama with Hermes
ollama pull hermes3:8b

# Option 2: Point at a Hermes endpoint (vLLM, llama.cpp, etc)
export HERMES_URL=http://localhost:8080
export HERMES_MODEL=NousResearch/Hermes-3-Llama-3.1-8B

python scripts/run_agent.py
```

The agent connects to available backends and falls back to mock mode for any layer that isn't reachable.

## License

MIT
