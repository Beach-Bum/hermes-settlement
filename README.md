# nous-agent

Reference autonomous agent: Hermes brain, ERC-8004 identity, Bittensor settlement.

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
```

## Quick start

```bash
pip install -r requirements.txt

# Point at a Hermes endpoint (vLLM, llama.cpp, etc)
export HERMES_URL=http://localhost:8080
export HERMES_MODEL=NousResearch/Hermes-3-Llama-3.1-8B

python scripts/run_agent.py
```

The agent will connect to available backends and fall back to mock mode
for any layer that isn't reachable.



## License

MIT
