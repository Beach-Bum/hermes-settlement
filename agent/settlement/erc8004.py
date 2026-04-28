"""
agent/settlement/erc8004.py

ERC-8004 identity, reputation, and validation registries on EVM.

ERC-8004 is an Ethereum standard for on-chain agent identity.
This client handles:
  - Agent registration (identity contract)
  - Reputation reads (reputation registry)
  - Validation checks (validation registry)

The chain target is configurable — defaults to a local Anvil node for dev,
production deployment TBD as canonical ERC-8004 implementations land.
"""

import time
import httpx
from typing import Optional

from agent.settlement.base import (
    SettlementClient, AgentIdentity, ReputationScore, PaymentResult,
)


# Default to local Anvil for development
DEFAULT_RPC_URL = "http://localhost:8545"

# ERC-8004 contract addresses — set via env or config when deployed
# These are placeholders for the reference implementation
IDENTITY_REGISTRY = "0x0000000000000000000000000000000000000000"
REPUTATION_REGISTRY = "0x0000000000000000000000000000000000000000"
VALIDATION_REGISTRY = "0x0000000000000000000000000000000000000000"


class ERC8004Client(SettlementClient):
    """
    ERC-8004 settlement client for agent identity and reputation.

    Handles on-chain identity registration, reputation reads, and
    validation checks. Degrades to mock mode when no node is reachable.

    This is the identity layer — TAO settlement happens via BittensorClient.
    """

    def __init__(
        self,
        rpc_url: str = DEFAULT_RPC_URL,
        identity_address: str = IDENTITY_REGISTRY,
        reputation_address: str = REPUTATION_REGISTRY,
    ):
        self.rpc_url = rpc_url
        self.identity_address = identity_address
        self.reputation_address = reputation_address
        self._mock = False
        self._chain_id: Optional[int] = None

    async def check_connection(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.rpc_url,
                    json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._chain_id = int(data.get("result", "0x0"), 16)
                    self._mock = False
                    print(f"[ERC-8004] Connected to chain {self._chain_id} at {self.rpc_url}")
                    return True
        except Exception:
            pass
        self._mock = True
        print(f"[ERC-8004] No node at {self.rpc_url} — mock mode")
        return False

    async def register_identity(
        self,
        agent_pub_key: str,
        stake: str,
        capability_hash: str,
    ) -> AgentIdentity:
        """
        Register agent identity in the ERC-8004 identity registry.

        In production: calls the identity contract's register() function.
        In mock mode: returns a synthetic identity for development.
        """
        if self._mock:
            return AgentIdentity(
                agent_id=agent_pub_key,
                tx_hash="0x" + "a" * 64,
                stake=stake,
                block=1000 + int(time.time()) % 1000,
                mock=True,
            )

        # TODO: Encode and send the ERC-8004 register transaction
        # The contract ABI will depend on the canonical ERC-8004 implementation.
        # For the reference agent, this is proof-of-shape — the contract interface
        # is defined, the transaction encoding is a straightforward web3.py call.
        #
        # identity_contract.functions.register(
        #     agent_pub_key, capability_hash
        # ).transact({"value": web3.to_wei(stake, "ether")})

        return AgentIdentity(
            agent_id=agent_pub_key,
            tx_hash="0x" + "a" * 64,
            stake=stake,
            block=0,
            mock=True,
        )

    async def get_reputation(self, agent_id: str) -> ReputationScore:
        """Read agent reputation from the ERC-8004 reputation registry."""
        if self._mock:
            return ReputationScore(
                agent_id=agent_id,
                score=0.85,
                total_tasks=0,
                source="erc8004",
                mock=True,
            )

        # TODO: Call reputation_contract.functions.getScore(agent_id).call()
        return ReputationScore(
            agent_id=agent_id,
            score=0.0,
            total_tasks=0,
            source="erc8004",
            mock=True,
        )

    async def get_balance(self, agent_id: str) -> str:
        """Get ETH balance for an agent address."""
        if self._mock:
            return "1.0"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_getBalance",
                        "params": [agent_id, "latest"],
                        "id": 1,
                    },
                    timeout=10.0,
                )
                data = resp.json()
                wei = int(data.get("result", "0x0"), 16)
                return str(wei / 1e18)
        except Exception:
            return "0"

    async def transfer(self, to_agent_id: str, amount: str) -> PaymentResult:
        """
        Transfer ETH. In the reference agent, identity registration
        is the primary on-chain operation — TAO handles payments.
        """
        if self._mock:
            return PaymentResult(
                tx_hash="0x" + "c" * 64,
                from_id="self",
                to_id=to_agent_id,
                amount=amount,
                currency="ETH",
                block=0,
                mock=True,
            )

        # TODO: web3.eth.send_transaction(...)
        return PaymentResult(
            tx_hash="0x" + "c" * 64,
            from_id="self",
            to_id=to_agent_id,
            amount=amount,
            currency="ETH",
            block=0,
            mock=True,
        )
