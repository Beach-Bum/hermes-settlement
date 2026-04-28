"""
hermes_toolset/settlement_tool.py

Settlement toolset for Hermes Agent — ERC-8004 identity + Bittensor settlement.

Drop this file into hermes-agent/tools/ and it auto-registers via
tools/registry.py's module-level discovery. Hermes users get on-chain
identity, reputation, and TAO settlement from the CLI or any gateway.

Toolset: "settlement"
Tools:
  - settlement_register   — Register agent identity on-chain (ERC-8004)
  - settlement_reputation  — Query on-chain reputation score
  - settlement_record_task — Record task completion on-chain
  - settlement_balance     — Check ETH + TAO balances
  - settlement_subnet_info — Query Bittensor subnet metrics
  - settlement_transfer    — Transfer TAO to another agent

Env vars:
  ERC8004_RPC          — EVM RPC endpoint (default: http://localhost:8545)
  ERC8004_REGISTRY     — AgentRegistry contract address
  ERC8004_PRIVATE_KEY  — Private key for EVM transactions
  BT_NETWORK           — Bittensor network: test | finney | local
  BT_NETUID            — Bittensor subnet UID (default: 1)
"""

import hashlib
import json
import os
from typing import Optional


# ---------------------------------------------------------------------------
# Lazy singleton clients — initialized on first tool call
# ---------------------------------------------------------------------------

_erc8004_client = None
_bittensor_client = None
_initialized = False


def _ensure_clients():
    """Lazy-init settlement clients. Safe to call repeatedly."""
    global _erc8004_client, _bittensor_client, _initialized
    if _initialized:
        return
    _initialized = True

    try:
        from agent.settlement.erc8004 import ERC8004Client
        _erc8004_client = ERC8004Client(
            rpc_url=os.environ.get("ERC8004_RPC", "http://localhost:8545"),
            registry_address=os.environ.get(
                "ERC8004_REGISTRY",
                "0x5FbDB2315678afecb367f032d93F642f64180aa3",
            ),
            private_key=os.environ.get("ERC8004_PRIVATE_KEY", ""),
        )
    except ImportError:
        pass

    try:
        from agent.settlement.bittensor import BittensorClient
        _bittensor_client = BittensorClient(
            network=os.environ.get("BT_NETWORK", "test"),
            netuid=int(os.environ.get("BT_NETUID", "1")),
        )
    except ImportError:
        pass


async def _connect_if_needed():
    """Connect clients if not already connected."""
    _ensure_clients()
    if _erc8004_client and _erc8004_client._w3 is None:
        await _erc8004_client.check_connection()
    if _bittensor_client and _bittensor_client._subtensor is None:
        await _bittensor_client.check_connection()


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def _handle_register(args: dict) -> str:
    """Register agent identity on ERC-8004."""
    await _connect_if_needed()
    if not _erc8004_client:
        return json.dumps({"error": "ERC-8004 client not available"})

    pub_key = args.get("pub_key", "hermes-agent")
    stake = args.get("stake", "0.01")
    capabilities = args.get("capabilities", ["inference"])

    cap_hash = hashlib.sha256(
        json.dumps(capabilities, sort_keys=True).encode()
    ).hexdigest()

    identity = await _erc8004_client.register_identity(
        agent_pub_key=pub_key, stake=stake, capability_hash=cap_hash,
    )
    return json.dumps({
        "registered": True,
        "tx_hash": identity.tx_hash,
        "block": identity.block,
        "on_chain": not identity.mock,
        "stake": stake,
    }, ensure_ascii=False)


async def _handle_reputation(args: dict) -> str:
    """Query reputation from ERC-8004 and/or Bittensor."""
    await _connect_if_needed()
    result = {}

    agent_id = args.get("agent_id", "self")

    if _erc8004_client:
        rep = await _erc8004_client.get_reputation(agent_id)
        result["erc8004"] = {
            "score": rep.score,
            "total_tasks": rep.total_tasks,
            "on_chain": not rep.mock,
        }

    if _bittensor_client:
        rep = await _bittensor_client.get_reputation(agent_id)
        result["bittensor"] = {
            "score": rep.score,
            "total_tasks": rep.total_tasks,
            "on_chain": not rep.mock,
        }

    if not result:
        return json.dumps({"error": "No settlement clients available"})

    return json.dumps(result, ensure_ascii=False)


async def _handle_record_task(args: dict) -> str:
    """Record task completion on-chain (ERC-8004)."""
    await _connect_if_needed()
    if not _erc8004_client:
        return json.dumps({"error": "ERC-8004 client not available"})

    success = args.get("success", True)
    tx_hash = await _erc8004_client.record_task(success=success)
    return json.dumps({
        "recorded": True,
        "success": success,
        "tx_hash": tx_hash,
    }, ensure_ascii=False)


async def _handle_balance(args: dict) -> str:
    """Check ETH and TAO balances."""
    await _connect_if_needed()
    result = {}
    agent_id = args.get("agent_id", "self")

    if _erc8004_client:
        result["eth"] = await _erc8004_client.get_balance(agent_id)

    if _bittensor_client:
        result["tao"] = await _bittensor_client.get_balance(agent_id)

    if not result:
        return json.dumps({"error": "No settlement clients available"})

    return json.dumps(result, ensure_ascii=False)


async def _handle_subnet_info(args: dict) -> str:
    """Query Bittensor subnet info."""
    await _connect_if_needed()
    if not _bittensor_client:
        return json.dumps({"error": "Bittensor client not available"})

    info = await _bittensor_client.get_subnet_info()
    return json.dumps(info, ensure_ascii=False)


async def _handle_transfer(args: dict) -> str:
    """Transfer TAO to another agent."""
    await _connect_if_needed()
    if not _bittensor_client:
        return json.dumps({"error": "Bittensor client not available"})

    to = args.get("to")
    amount = args.get("amount")
    if not to or not amount:
        return json.dumps({"error": "Both 'to' and 'amount' are required"})

    result = await _bittensor_client.transfer(to_agent_id=to, amount=str(amount))
    return json.dumps({
        "tx_hash": result.tx_hash,
        "from": result.from_id,
        "to": result.to_id,
        "amount": result.amount,
        "currency": result.currency,
        "on_chain": not result.mock,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Sync wrappers (Hermes registry expects sync handlers)
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Bridge async handler to sync for Hermes tool dispatch."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def check_settlement_requirements() -> bool:
    """Settlement tools are available if web3 or bittensor is importable."""
    try:
        import web3  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import bittensor  # noqa: F401
        return True
    except ImportError:
        pass
    return False


# ---------------------------------------------------------------------------
# OpenAI Function-Calling Schemas
# ---------------------------------------------------------------------------

REGISTER_SCHEMA = {
    "name": "settlement_register",
    "description": (
        "Register this agent's identity on-chain via ERC-8004. "
        "Creates a permanent, verifiable identity with a stake bond. "
        "Returns the transaction hash and block number."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pub_key": {
                "type": "string",
                "description": "Agent's public key or identifier (default: hermes-agent)",
            },
            "stake": {
                "type": "string",
                "description": "ETH stake amount (default: 0.01)",
            },
            "capabilities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of capability strings (e.g. ['inference', 'code_review'])",
            },
        },
        "required": [],
    },
}

REPUTATION_SCHEMA = {
    "name": "settlement_reputation",
    "description": (
        "Query this agent's on-chain reputation score from ERC-8004 "
        "and Bittensor subnet metrics. Returns scores from both layers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "Agent ID to query (default: self)",
            },
        },
        "required": [],
    },
}

RECORD_TASK_SCHEMA = {
    "name": "settlement_record_task",
    "description": (
        "Record a completed task on-chain (ERC-8004). Updates the agent's "
        "reputation score. Call after finishing a task to build on-chain history."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether the task was completed successfully (default: true)",
            },
        },
        "required": [],
    },
}

BALANCE_SCHEMA = {
    "name": "settlement_balance",
    "description": (
        "Check the agent's ETH balance (ERC-8004 chain) and TAO balance "
        "(Bittensor network)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "Agent ID to check (default: self)",
            },
        },
        "required": [],
    },
}

SUBNET_INFO_SCHEMA = {
    "name": "settlement_subnet_info",
    "description": (
        "Query Bittensor subnet information — number of neurons, current "
        "block, network status. Useful for understanding the agent's "
        "economic environment."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

TRANSFER_SCHEMA = {
    "name": "settlement_transfer",
    "description": (
        "Transfer TAO to another agent on the Bittensor network. "
        "Native transfer — no bridging or wrapped tokens."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Destination agent SS58 address",
            },
            "amount": {
                "type": "string",
                "description": "Amount of TAO to transfer",
            },
        },
        "required": ["to", "amount"],
    },
}


# ---------------------------------------------------------------------------
# Registry — auto-discovered by Hermes when this file is in tools/
# ---------------------------------------------------------------------------

from tools.registry import registry  # noqa: E402

_check = check_settlement_requirements

registry.register(
    name="settlement_register",
    toolset="settlement",
    schema=REGISTER_SCHEMA,
    handler=lambda args, **kw: _run_async(_handle_register(args)),
    check_fn=_check,
    requires_env=["ERC8004_PRIVATE_KEY"],
    is_async=False,
    emoji="🔗",
)

registry.register(
    name="settlement_reputation",
    toolset="settlement",
    schema=REPUTATION_SCHEMA,
    handler=lambda args, **kw: _run_async(_handle_reputation(args)),
    check_fn=_check,
    emoji="⭐",
)

registry.register(
    name="settlement_record_task",
    toolset="settlement",
    schema=RECORD_TASK_SCHEMA,
    handler=lambda args, **kw: _run_async(_handle_record_task(args)),
    check_fn=_check,
    requires_env=["ERC8004_PRIVATE_KEY"],
    emoji="✅",
)

registry.register(
    name="settlement_balance",
    toolset="settlement",
    schema=BALANCE_SCHEMA,
    handler=lambda args, **kw: _run_async(_handle_balance(args)),
    check_fn=_check,
    emoji="💰",
)

registry.register(
    name="settlement_subnet_info",
    toolset="settlement",
    schema=SUBNET_INFO_SCHEMA,
    handler=lambda args, **kw: _run_async(_handle_subnet_info(args)),
    check_fn=_check,
    emoji="🌐",
)

registry.register(
    name="settlement_transfer",
    toolset="settlement",
    schema=TRANSFER_SCHEMA,
    handler=lambda args, **kw: _run_async(_handle_transfer(args)),
    check_fn=_check,
    requires_env=["ERC8004_PRIVATE_KEY"],
    emoji="💸",
)
