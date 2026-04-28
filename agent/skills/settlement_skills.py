"""
agent/skills/settlement_skills.py

Settlement skills — TAO-denominated wallet and Bittensor operations.

Skills:
  wallet.balance  — return agent's current TAO balance
  wallet.send     — send TAO; enforces spending policy
  wallet.history  — return recent transaction summary
  subnet.info     — return Bittensor subnet info
"""

from agent.skills.base import Skill, SkillContext, SkillResult
from agent.core.wallet import AgentWallet
from agent.settlement.bittensor import BittensorClient


class WalletBalanceSkill(Skill):
    name = "wallet.balance"
    description = "Return agent's current TAO balance"
    category = "settlement"
    parameters = {}

    def __init__(self, wallet: AgentWallet):
        self._wallet = wallet

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        state = self._wallet.state()
        return SkillResult.ok({
            "balance_tao": state["balance_tao"],
            "available_tao": state["available_tao"],
            "earned_total_tao": state["earned_total_tao"],
            "frozen": state["frozen"],
        })


class WalletSendSkill(Skill):
    name = "wallet.send"
    description = "Send TAO to a recipient; enforces spending policy"
    category = "settlement"
    requires_approval = True
    parameters = {
        "recipient": {"type": "string", "required": True},
        "amount": {"type": "number", "required": True},
    }

    def __init__(self, wallet: AgentWallet, settlement: BittensorClient):
        self._wallet = wallet
        self._settlement = settlement

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        amount = float(params["amount"])
        recipient = params["recipient"]

        allowed, reason = self._wallet.check_spend(amount, "transfer")
        if not allowed:
            return SkillResult.fail(f"Spending denied: {reason}")

        import secrets
        session_id = secrets.token_hex(16)
        self._wallet.spend(amount, recipient[:20], session_id, "transfer")

        tx = await self._settlement.transfer(recipient, str(amount))

        return SkillResult.ok({
            "sent": True,
            "amount_tao": amount,
            "recipient": recipient,
            "tx_hash": tx.tx_hash,
            "remaining_balance": self._wallet._balance_tao,
        })


class WalletHistorySkill(Skill):
    name = "wallet.history"
    description = "Return recent transaction summary"
    category = "settlement"
    parameters = {
        "limit": {"type": "number", "required": False},
    }

    def __init__(self, wallet: AgentWallet):
        self._wallet = wallet

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        limit = int(params.get("limit", 20))
        entries = self._wallet.audit_log(limit)
        return SkillResult.ok({"entries": entries, "count": len(entries)})


class SubnetInfoSkill(Skill):
    name = "subnet.info"
    description = "Return Bittensor subnet information"
    category = "settlement"
    parameters = {}

    def __init__(self, settlement: BittensorClient):
        self._settlement = settlement

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        info = await self._settlement.get_subnet_info()
        return SkillResult.ok(info)


def register_settlement_skills(registry, wallet: AgentWallet, settlement: BittensorClient):
    registry.register(WalletBalanceSkill(wallet))
    registry.register(WalletSendSkill(wallet, settlement))
    registry.register(WalletHistorySkill(wallet))
    registry.register(SubnetInfoSkill(settlement))
