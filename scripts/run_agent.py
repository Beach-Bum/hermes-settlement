#!/usr/bin/env python3
"""
Launch the Nous reference agent.

Usage:
    python scripts/run_agent.py

Environment variables:
    HERMES_URL      Hermes endpoint (default: http://localhost:8080)
    HERMES_MODEL    Model name (default: NousResearch/Hermes-3-Llama-3.1-8B)
    BT_NETWORK      Bittensor network (default: test)
    BT_NETUID       Bittensor subnet UID (default: 1)
    ERC8004_RPC     EVM RPC URL (default: http://localhost:8545)
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.core.agent import NousAgent, AgentConfig


async def main():
    config = AgentConfig(
        bittensor_network=os.environ.get("BT_NETWORK", "test"),
        bittensor_netuid=int(os.environ.get("BT_NETUID", "1")),
        erc8004_rpc_url=os.environ.get("ERC8004_RPC", "http://localhost:8545"),
    )

    agent = NousAgent(config)

    try:
        await agent.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
