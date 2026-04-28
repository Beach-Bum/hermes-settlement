"""
agent/settlement/base.py

SettlementClient ABC — the interface that every settlement backend implements.

Two concrete implementations:
  - ERC8004Client: identity, reputation, validation registries on EVM
  - BittensorClient: TAO rewards, subnet participation, staking
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentIdentity:
    agent_id: str
    tx_hash: str
    stake: str
    block: int
    mock: bool = False


@dataclass
class ReputationScore:
    agent_id: str
    score: float          # 0.0 - 1.0
    total_tasks: int
    source: str           # "erc8004" | "bittensor" | "mock"
    mock: bool = False


@dataclass
class PaymentResult:
    tx_hash: str
    from_id: str
    to_id: str
    amount: str
    currency: str         # "TAO" | "ETH"
    block: int
    mock: bool = False


class SettlementClient(ABC):
    """
    Abstract settlement interface.

    Concrete implementations handle the chain-specific details.
    The agent core only talks to this interface.
    """

    @abstractmethod
    async def check_connection(self) -> bool:
        """Check if the settlement backend is reachable."""
        ...

    @abstractmethod
    async def register_identity(
        self,
        agent_pub_key: str,
        stake: str,
        capability_hash: str,
    ) -> AgentIdentity:
        """Register agent identity on-chain."""
        ...

    @abstractmethod
    async def get_reputation(self, agent_id: str) -> ReputationScore:
        """Read agent reputation from the settlement layer."""
        ...

    @abstractmethod
    async def get_balance(self, agent_id: str) -> str:
        """Get balance for an agent identity."""
        ...

    @abstractmethod
    async def transfer(
        self,
        to_agent_id: str,
        amount: str,
    ) -> PaymentResult:
        """Transfer funds to another agent."""
        ...
