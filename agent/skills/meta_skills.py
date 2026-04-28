"""
agent/skills/meta_skills.py

Meta skills — agent introspection and configuration.

Skills:
  meta.skills    — list available skills
  meta.status    — report agent state
  meta.configure — update runtime configuration
"""

from agent.skills.base import Skill, SkillContext, SkillResult, SkillRegistry
from agent.core.wallet import AgentWallet
from agent.skills.agent_skills import task_store


class MetaSkillsSkill(Skill):
    name = "meta.skills"
    description = "List all available skills and their parameters"
    category = "meta"
    parameters = {
        "category": {"type": "string", "required": False},
    }

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        category = params.get("category")
        if category:
            skills = self._registry.list_by_category(category)
        else:
            skills = self._registry.list_skills()
        return SkillResult.ok({"skills": skills, "count": len(skills)})


class MetaStatusSkill(Skill):
    name = "meta.status"
    description = "Report agent state, balance, and active tasks"
    category = "meta"
    parameters = {}

    def __init__(self, wallet: AgentWallet, registry: SkillRegistry):
        self._wallet = wallet
        self._registry = registry

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        wallet_state = self._wallet.state()
        active_tasks = task_store.list_active()
        return SkillResult.ok({
            "agent": {
                "pub_key": wallet_state["pub_key"],
                "frozen": wallet_state["frozen"],
            },
            "wallet": {
                "balance_tao": wallet_state["balance_tao"],
                "available_tao": wallet_state["available_tao"],
                "earned_total_tao": wallet_state["earned_total_tao"],
            },
            "skills": {"total": self._registry.count},
            "tasks": {"active": len(active_tasks)},
        })


class MetaConfigureSkill(Skill):
    name = "meta.configure"
    description = "Update runtime configuration"
    category = "meta"
    parameters = {
        "key": {"type": "string", "required": True},
        "value": {"type": "string", "required": True},
    }

    ALLOWED_KEYS = {
        "spending.max_per_tx": "max_per_tx_tao",
        "spending.daily_cap": "daily_cap_tao",
        "spending.frozen": "frozen",
    }

    def __init__(self, wallet: AgentWallet):
        self._wallet = wallet

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        key = params["key"]
        value = params["value"]

        if key not in self.ALLOWED_KEYS:
            return SkillResult.fail(f"Unknown config key: {key}")

        if key == "spending.max_per_tx":
            self._wallet.policy.max_per_tx_tao = float(value)
            self._wallet.policy.save()
        elif key == "spending.daily_cap":
            self._wallet.policy.daily_cap_tao = float(value)
            self._wallet.policy.save()
        elif key == "spending.frozen":
            if value.lower() in ("true", "1", "yes"):
                self._wallet.freeze()
            else:
                self._wallet.unfreeze()

        return SkillResult.ok({"updated": True, "key": key, "value": value})


def register_meta_skills(registry: SkillRegistry, wallet: AgentWallet):
    registry.register(MetaSkillsSkill(registry))
    registry.register(MetaStatusSkill(wallet, registry))
    registry.register(MetaConfigureSkill(wallet))
