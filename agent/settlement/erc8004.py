"""
agent/settlement/erc8004.py

ERC-8004 identity, reputation, and validation registries on EVM.

Uses the AgentRegistry contract deployed via Foundry.
Chain target is configurable — defaults to local Anvil for dev.
"""

import hashlib
import os
import time
from typing import Optional

from web3 import Web3
from web3.exceptions import ContractLogicError

from agent.settlement.base import (
    SettlementClient, AgentIdentity, ReputationScore, PaymentResult,
)


DEFAULT_RPC_URL = os.environ.get("ERC8004_RPC", "http://localhost:8545")
DEFAULT_REGISTRY = os.environ.get("ERC8004_REGISTRY", "0x5FbDB2315678afecb367f032d93F642f64180aa3")

# Anvil's first default account — used for local dev only
DEFAULT_PRIVATE_KEY = os.environ.get("ERC8004_PRIVATE_KEY", "")

# Minimal ABI for AgentRegistry
REGISTRY_ABI = [
    {
        "type": "function",
        "name": "register",
        "inputs": [
            {"name": "pubKeyHash", "type": "bytes32"},
            {"name": "capabilityHash", "type": "bytes32"},
        ],
        "outputs": [],
        "stateMutability": "payable",
    },
    {
        "type": "function",
        "name": "getReputation",
        "inputs": [{"name": "agent", "type": "address"}],
        "outputs": [
            {"name": "score", "type": "uint256"},
            {"name": "total", "type": "uint256"},
            {"name": "successful", "type": "uint256"},
        ],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "isRegistered",
        "inputs": [{"name": "agent", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "recordTask",
        "inputs": [{"name": "success", "type": "bool"}],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "agentCount",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]


class ERC8004Client(SettlementClient):
    """
    ERC-8004 settlement client for agent identity and reputation.

    Uses web3.py to interact with the AgentRegistry contract.
    Degrades to mock mode when no node is reachable.
    """

    def __init__(
        self,
        rpc_url: str = DEFAULT_RPC_URL,
        registry_address: str = DEFAULT_REGISTRY,
        private_key: str = DEFAULT_PRIVATE_KEY,
    ):
        self.rpc_url = rpc_url
        self.registry_address = registry_address
        self._private_key = private_key
        self._mock = False
        self._w3: Optional[Web3] = None
        self._contract = None
        self._account = None

    async def check_connection(self) -> bool:
        try:
            self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if self._w3.is_connected():
                chain_id = self._w3.eth.chain_id
                self._contract = self._w3.eth.contract(
                    address=Web3.to_checksum_address(self.registry_address),
                    abi=REGISTRY_ABI,
                )
                if self._private_key:
                    self._account = self._w3.eth.account.from_key(self._private_key)
                self._mock = False
                agent_count = self._contract.functions.agentCount().call()
                print(f"[ERC-8004] Connected to chain {chain_id} | registry {self.registry_address[:20]}... | {agent_count} agents")
                return True
        except Exception as e:
            print(f"[ERC-8004] Connection failed: {e}")
        self._mock = True
        print(f"[ERC-8004] Mock mode")
        return False

    async def register_identity(
        self,
        agent_pub_key: str,
        stake: str,
        capability_hash: str,
    ) -> AgentIdentity:
        if self._mock or not self._account:
            return AgentIdentity(
                agent_id=agent_pub_key,
                tx_hash="0x" + "a" * 64,
                stake=stake,
                block=1000 + int(time.time()) % 1000,
                mock=True,
            )

        try:
            # Check if already registered
            is_reg = self._contract.functions.isRegistered(self._account.address).call()
            if is_reg:
                print(f"[ERC-8004] Already registered at {self._account.address}")
                return AgentIdentity(
                    agent_id=agent_pub_key,
                    tx_hash="0x_already_registered",
                    stake=stake,
                    block=self._w3.eth.block_number,
                    mock=False,
                )

            pub_key_hash = bytes.fromhex(hashlib.sha256(agent_pub_key.encode()).hexdigest())
            cap_hash = bytes.fromhex(capability_hash[:64].ljust(64, '0'))
            stake_wei = self._w3.to_wei(float(stake), 'ether')

            tx = self._contract.functions.register(pub_key_hash, cap_hash).build_transaction({
                'from': self._account.address,
                'value': stake_wei,
                'nonce': self._w3.eth.get_transaction_count(self._account.address),
                'gas': 300000,
                'gasPrice': self._w3.eth.gas_price,
            })

            signed = self._account.sign_transaction(tx)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)

            print(f"[ERC-8004] Registered! tx={tx_hash.hex()[:20]}... block={receipt['blockNumber']}")
            return AgentIdentity(
                agent_id=agent_pub_key,
                tx_hash=tx_hash.hex(),
                stake=stake,
                block=receipt['blockNumber'],
                mock=False,
            )
        except ContractLogicError as e:
            print(f"[ERC-8004] Contract error: {e}")
            return AgentIdentity(agent_id=agent_pub_key, tx_hash="0x_error", stake=stake, block=0, mock=True)
        except Exception as e:
            print(f"[ERC-8004] register_identity failed: {e}")
            return AgentIdentity(agent_id=agent_pub_key, tx_hash="0x_error", stake=stake, block=0, mock=True)

    async def get_reputation(self, agent_id: str) -> ReputationScore:
        if self._mock or not self._contract or not self._account:
            return ReputationScore(agent_id=agent_id, score=0.85, total_tasks=0, source="erc8004", mock=True)

        try:
            score_bps, total, successful = self._contract.functions.getReputation(
                self._account.address
            ).call()
            return ReputationScore(
                agent_id=agent_id,
                score=score_bps / 10000.0,
                total_tasks=total,
                source="erc8004",
                mock=False,
            )
        except Exception:
            return ReputationScore(agent_id=agent_id, score=0.0, total_tasks=0, source="erc8004", mock=True)

    async def record_task(self, success: bool) -> str:
        """Record a completed task on-chain. Returns tx hash."""
        if self._mock or not self._account:
            return "0x_mock"

        try:
            tx = self._contract.functions.recordTask(success).build_transaction({
                'from': self._account.address,
                'nonce': self._w3.eth.get_transaction_count(self._account.address),
                'gas': 100000,
                'gasPrice': self._w3.eth.gas_price,
            })
            signed = self._account.sign_transaction(tx)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            self._w3.eth.wait_for_transaction_receipt(tx_hash)
            return tx_hash.hex()
        except Exception as e:
            print(f"[ERC-8004] recordTask failed: {e}")
            return "0x_error"

    async def get_balance(self, agent_id: str) -> str:
        if self._mock or not self._w3:
            return "1.0"
        try:
            if self._account:
                wei = self._w3.eth.get_balance(self._account.address)
            else:
                wei = 0
            return str(self._w3.from_wei(wei, 'ether'))
        except Exception:
            return "0"

    async def transfer(self, to_agent_id: str, amount: str) -> PaymentResult:
        if self._mock:
            return PaymentResult(tx_hash="0x" + "c" * 64, from_id="self", to_id=to_agent_id,
                                 amount=amount, currency="ETH", block=0, mock=True)

        # Identity registration is the primary on-chain op — TAO handles payments
        return PaymentResult(tx_hash="0x_not_implemented", from_id="self", to_id=to_agent_id,
                             amount=amount, currency="ETH", block=0, mock=True)
