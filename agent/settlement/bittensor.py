"""
agent/settlement/bittensor.py

Bittensor settlement client — TAO rewards, subnet participation, staking.

Bittensor is the incentive substrate. This client handles:
  - Subnet registration (coldkey/hotkey management)
  - TAO balance queries
  - TAO transfers between agents
  - Subnet reward tracking
  - Reputation derived from subnet performance metrics

The agent earns TAO by participating in a Bittensor subnet as a miner,
providing Hermes inference to validators. Settlement is native — no
bridging, no wrapped tokens, no third-party payment rails.
"""

import time
from typing import Optional

from agent.settlement.base import (
    SettlementClient, AgentIdentity, ReputationScore, PaymentResult,
)


# Bittensor network endpoints
FINNEY_ENDPOINT = "wss://entrypoint-finney.opentensor.ai:443"
TESTNET_ENDPOINT = "wss://test.finney.opentensor.ai:443"
LOCAL_ENDPOINT = "ws://localhost:9944"


class BittensorClient(SettlementClient):
    """
    Bittensor settlement client.

    Uses the bittensor SDK to interact with the Bittensor network.
    TAO is the native currency — no bridging needed.

    In mock mode (no subtensor reachable), all operations return
    synthetic data for local development.
    """

    def __init__(
        self,
        network: str = "test",
        netuid: int = 1,
        wallet_name: str = "nous-agent",
        hotkey_name: str = "default",
    ):
        self.network = network
        self.netuid = netuid
        self.wallet_name = wallet_name
        self.hotkey_name = hotkey_name
        self._mock = False
        self._subtensor = None
        self._wallet = None

    async def check_connection(self) -> bool:
        """Connect to the Bittensor network via subtensor."""
        try:
            import bittensor as bt
            self._subtensor = bt.Subtensor(network=self.network)
            block = self._subtensor.get_current_block()
            self._mock = False
            n_subnets = self._subtensor.get_total_subnets()
            print(f"[Bittensor] Connected to {self.network} at block {block} | {n_subnets} subnets")
            return True
        except Exception as e:
            self._mock = True
            print(f"[Bittensor] Cannot reach {self.network}: {e} — mock mode")
            return False

    def _ensure_wallet(self):
        """Load or create a bittensor wallet."""
        if self._wallet:
            return self._wallet
        try:
            import bittensor as bt
            self._wallet = bt.Wallet(name=self.wallet_name, hotkey=self.hotkey_name)
            return self._wallet
        except Exception as e:
            print(f"[Bittensor] Wallet error: {e}")
            return None

    async def register_identity(
        self,
        agent_pub_key: str,
        stake: str,
        capability_hash: str,
    ) -> AgentIdentity:
        """
        Register on a Bittensor subnet.

        In production: registers a hotkey on the target subnet via
        burned_register (burns TAO to register without PoW).
        Staking TAO is the credibility bond — same concept as Agora's
        NOM staking, but using Bittensor's native mechanism.
        """
        if self._mock:
            return AgentIdentity(
                agent_id=agent_pub_key,
                tx_hash="0x" + "b" * 64,
                stake=stake,
                block=1000 + int(time.time()) % 1000,
                mock=True,
            )

        wallet = self._ensure_wallet()
        if not wallet:
            return AgentIdentity(
                agent_id=agent_pub_key, tx_hash="0x_no_wallet",
                stake=stake, block=0, mock=True,
            )

        try:
            # Check if already registered on this subnet
            hotkey_ss58 = wallet.hotkey.ss58_address
            is_reg = self._subtensor.is_hotkey_registered_on_subnet(
                hotkey_ss58=hotkey_ss58, netuid=self.netuid
            )
            if is_reg:
                uid = self._subtensor.get_uid_for_hotkey_on_subnet(
                    hotkey_ss58=hotkey_ss58, netuid=self.netuid
                )
                block = self._subtensor.get_current_block()
                print(f"[Bittensor] Already registered on subnet {self.netuid} as UID {uid}")
                return AgentIdentity(
                    agent_id=hotkey_ss58,
                    tx_hash=f"0x_registered_uid_{uid}",
                    stake=stake,
                    block=block,
                    mock=False,
                )

            # Register via burned_register (burns TAO, no PoW)
            success = self._subtensor.burned_register(
                wallet=wallet, netuid=self.netuid
            )
            block = self._subtensor.get_current_block()
            if success:
                print(f"[Bittensor] Registered on subnet {self.netuid} at block {block}")
                return AgentIdentity(
                    agent_id=hotkey_ss58,
                    tx_hash=f"0x_burned_register_{block}",
                    stake=stake,
                    block=block,
                    mock=False,
                )
            else:
                print(f"[Bittensor] Registration failed")
                return AgentIdentity(
                    agent_id=agent_pub_key, tx_hash="0x_reg_failed",
                    stake=stake, block=0, mock=True,
                )
        except Exception as e:
            print(f"[Bittensor] register_identity failed: {e}")
            return AgentIdentity(
                agent_id=agent_pub_key, tx_hash="0x_error",
                stake=stake, block=0, mock=True,
            )

    async def get_reputation(self, agent_id: str) -> ReputationScore:
        """
        Derive reputation from Bittensor subnet metrics.

        On Bittensor, reputation maps to:
          - Trust score from validators
          - Incentive share on the subnet
          - Historical emission earnings

        This is more honest than inventing a custom reputation system —
        Bittensor already tracks these metrics on-chain.
        """
        if self._mock:
            return ReputationScore(
                agent_id=agent_id, score=0.85,
                total_tasks=0, source="bittensor", mock=True,
            )

        try:
            wallet = self._ensure_wallet()
            if not wallet:
                raise ValueError("No wallet")

            hotkey_ss58 = wallet.hotkey.ss58_address
            mg = self._subtensor.metagraph(netuid=self.netuid)

            if hotkey_ss58 not in mg.hotkeys:
                return ReputationScore(
                    agent_id=agent_id, score=0.0,
                    total_tasks=0, source="bittensor", mock=False,
                )

            idx = mg.hotkeys.index(hotkey_ss58)
            incentive = float(mg.incentive[idx])
            emission = float(mg.emission[idx])
            consensus = float(mg.consensus[idx])
            stake_val = float(mg.stake[idx])

            # Composite score: weighted average of subnet metrics
            score = (incentive * 0.4 + consensus * 0.4 + min(emission * 100, 1.0) * 0.2)

            return ReputationScore(
                agent_id=agent_id,
                score=score,
                total_tasks=int(emission * 1000),  # proxy for work done
                source="bittensor",
                mock=False,
            )
        except Exception as e:
            print(f"[Bittensor] get_reputation failed: {e}")
            return ReputationScore(
                agent_id=agent_id, score=0.0,
                total_tasks=0, source="bittensor", mock=True,
            )

    async def get_balance(self, agent_id: str) -> str:
        """Get TAO balance for the agent's coldkey."""
        if self._mock:
            return "10.0"

        try:
            wallet = self._ensure_wallet()
            if not wallet:
                return "0 (no wallet)"
            balance = self._subtensor.get_balance(wallet.coldkeypub.ss58_address)
            return str(balance)
        except Exception:
            # No wallet on disk yet — testnet connection is live, just no funded key
            return "0 (no wallet — create with btcli)"

    async def transfer(self, to_agent_id: str, amount: str) -> PaymentResult:
        """
        Transfer TAO to another agent.

        TAO transfers are native Bittensor operations — no bridging,
        no wrapped tokens, no Coinbase dependency.
        """
        if self._mock:
            return PaymentResult(
                tx_hash="0x" + "t" * 64,
                from_id="self", to_id=to_agent_id,
                amount=amount, currency="TAO",
                block=1000 + int(time.time()) % 1000, mock=True,
            )

        try:
            wallet = self._ensure_wallet()
            if not wallet:
                raise ValueError("No wallet")

            import bittensor as bt
            success = self._subtensor.transfer(
                wallet=wallet,
                dest=to_agent_id,
                amount=bt.Balance.from_tao(float(amount)),
            )
            block = self._subtensor.get_current_block()
            return PaymentResult(
                tx_hash=f"0x_transfer_{block}",
                from_id=wallet.coldkeypub.ss58_address,
                to_id=to_agent_id,
                amount=amount, currency="TAO",
                block=block, mock=not success,
            )
        except Exception as e:
            print(f"[Bittensor] transfer failed: {e}")
            return PaymentResult(
                tx_hash="0x_error", from_id="self", to_id=to_agent_id,
                amount=amount, currency="TAO", block=0, mock=True,
            )

    async def get_subnet_info(self) -> dict:
        """Get info about the target subnet — useful for the demo."""
        if self._mock:
            return {
                "netuid": self.netuid, "network": self.network,
                "miners": 256, "validators": 64,
                "emission_rate": "1.0 TAO/block", "mock": True,
            }

        try:
            mg = self._subtensor.metagraph(netuid=self.netuid)
            block = self._subtensor.get_current_block()
            return {
                "netuid": self.netuid,
                "network": self.network,
                "neurons": int(mg.n),
                "block": block,
                "mock": False,
            }
        except Exception as e:
            print(f"[Bittensor] get_subnet_info failed: {e}")
            return {"netuid": self.netuid, "network": self.network, "mock": True}
