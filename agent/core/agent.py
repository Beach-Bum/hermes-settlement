"""
agent/core/agent.py

Nous reference agent — autonomous agent with Hermes brain,
ERC-8004 identity, and Bittensor settlement.

This is the main orchestrator. It:
  1. Initializes wallet and keypair
  2. Connects to settlement layers (ERC-8004 + Bittensor)
  3. Registers on-chain identity
  4. Builds skill registry
  5. Runs the agent loop (listen, evaluate, execute, settle)
"""

import asyncio
import hashlib
import json
import time
import secrets
from dataclasses import dataclass, field
from typing import Optional, Callable

from agent.daemon.llm import HermesLLM, AgentReasoner
from agent.settlement.base import SettlementClient
from agent.settlement.erc8004 import ERC8004Client
from agent.settlement.bittensor import BittensorClient
from agent.transport.http import HttpTransport, CapabilityManifest, CapabilityService
from agent.core.wallet import AgentWallet
from agent.skills.base import SkillRegistry, SkillContext
from agent.skills.settlement_skills import register_settlement_skills
from agent.skills.agent_skills import register_agent_skills
from agent.skills.meta_skills import register_meta_skills


@dataclass
class AgentConfig:
    agent_name: str = "nous-agent"
    stake_tao: str = "1.0"
    services: list = field(default_factory=lambda: [
        CapabilityService(
            id="inference-v1", category="inference",
            price_per_unit="0.001", model="hermes-3-8b",
            context_window=32768, avg_latency_ms=850,
        ),
    ])
    bittensor_network: str = "test"
    bittensor_netuid: int = 1
    erc8004_rpc_url: str = "http://localhost:8545"
    capability_broadcast_interval_s: int = 60
    auto_sell: bool = True


class NousAgent:
    """
    Autonomous agent on the Nous-aligned stack.

    Hermes brain. ERC-8004 identity. Bittensor settlement.
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.wallet = AgentWallet(self.config.agent_name)
        self.llm = HermesLLM()
        self.reasoner = AgentReasoner(self.llm, role="seller")

        # Settlement: dual-layer
        self.identity = ERC8004Client(rpc_url=self.config.erc8004_rpc_url)
        self.settlement = BittensorClient(
            network=self.config.bittensor_network,
            netuid=self.config.bittensor_netuid,
        )

        self.transport = HttpTransport()
        self.registry: Optional[SkillRegistry] = None
        self._identity_record = None
        self._running = False
        self._event_log: list[dict] = []
        self._on_event: Optional[Callable] = None

        # Stats
        self.tasks_completed = 0
        self.tasks_failed = 0

    def _sign(self, data: bytes) -> str:
        import hmac
        sig = hmac.new(self.wallet._key.bytes, data, hashlib.sha256).hexdigest()
        return "3045" + sig

    def _emit(self, event: str, level: str = "info", **data):
        entry = {"event": event, "level": level, "ts": time.time(), **data}
        self._event_log.append(entry)
        if self._on_event:
            self._on_event(entry)

    def build_registry(self) -> SkillRegistry:
        registry = SkillRegistry()
        register_settlement_skills(registry, self.wallet, self.settlement)
        register_agent_skills(
            registry,
            agent_name=self.config.agent_name,
            agent_pub_key=self.wallet.pub_key_hex,
            transport=self.transport,
        )
        register_meta_skills(registry, self.wallet)
        self.registry = registry
        self._emit("skills_registered", msg=f"Skill SDK ready — {registry.count} skills")
        return registry

    async def start(self):
        self._emit("agent_starting", msg="Initializing Nous agent...")

        # Initialize wallet
        pub_key = self.wallet.initialize()
        self._emit("wallet_ready", msg=f"Wallet ready: {pub_key[:20]}...",
                   pub_key=pub_key)

        # Connect to settlement layers
        await self.identity.check_connection()
        await self.settlement.check_connection()

        # Register on-chain identity via ERC-8004
        capability_hash = hashlib.sha256(
            json.dumps([s.id for s in self.config.services]).encode()
        ).hexdigest()

        self._identity_record = await self.identity.register_identity(
            agent_pub_key=pub_key,
            stake=self.config.stake_tao,
            capability_hash=capability_hash,
        )
        self._emit("identity_registered",
                   msg=f"Identity registered: {self._identity_record.tx_hash[:20]}...",
                   mock=self._identity_record.mock)

        # Register on Bittensor subnet
        await self.settlement.register_identity(
            agent_pub_key=pub_key,
            stake=self.config.stake_tao,
            capability_hash=capability_hash,
        )
        self._emit("bittensor_registered", msg="Bittensor subnet registration complete")

        # Build skill registry
        self.build_registry()

        self._running = True
        self._emit("agent_ready", level="success",
                   msg="Nous agent is online and autonomous")

        # Background loops
        tasks = []
        if self.config.auto_sell:
            tasks.append(self._broadcast_capabilities_loop())

        if tasks:
            await asyncio.gather(*tasks)

    async def stop(self):
        self._running = False
        self.wallet.shutdown()
        self._emit("agent_stopped", msg="Agent stopped — key zeroed")

    async def invoke_skill(self, name: str, params: dict, caller: str = "owner") -> dict:
        if not self.registry:
            self.build_registry()
        context = SkillContext(
            agent_pub_key=self.wallet.pub_key_hex,
            wallet_balance=self.wallet._balance_tao,
            caller=caller,
        )
        result = await self.registry.invoke(name, params, context)
        return result.to_dict()

    async def _broadcast_capabilities_loop(self):
        while self._running:
            if self._identity_record and self.config.services:
                rep = await self.settlement.get_reputation(self.wallet.pub_key_hex)
                manifest = CapabilityManifest(
                    agent_id=self.wallet.pub_key_hex,
                    identity_tx_hash=self._identity_record.tx_hash,
                    stake=self.config.stake_tao,
                    reputation=rep.score,
                    capabilities=self.config.services,
                )
                await self.transport.broadcast_capabilities(manifest, self._sign)
            await asyncio.sleep(self.config.capability_broadcast_interval_s)

    def state(self) -> dict:
        wallet_state = self.wallet.state()
        return {
            "running": self._running,
            "wallet": wallet_state,
            "identity": {
                "pub_key": self.wallet.pub_key_hex,
                "erc8004_tx": self._identity_record.tx_hash if self._identity_record else None,
                "mock": self._identity_record.mock if self._identity_record else True,
            },
            "stats": {
                "tasks_completed": self.tasks_completed,
                "tasks_failed": self.tasks_failed,
            },
            "services": [
                {"id": s.id, "category": s.category, "price": s.price_per_unit}
                for s in self.config.services
            ],
            "backend": self.llm._backend or "detecting...",
        }

    def get_events(self, since_index: int = 0) -> dict:
        entries = self._event_log[since_index:]
        return {"entries": entries, "cursor": len(self._event_log)}
