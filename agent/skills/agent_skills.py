"""
agent/skills/agent_skills.py

A2A agent-to-agent coordination skills over HTTP transport.

Skills:
  agent.card      — return A2A-compatible Agent Card
  agent.discover  — fetch Agent Card from a URL
  agent.task      — send task request to another agent
"""

import json
import time
import secrets
from typing import Optional

from agent.skills.base import Skill, SkillContext, SkillResult, SkillRegistry
from agent.transport.http import HttpTransport, TaskRequest


A2A_PROTOCOL_VERSION = "1.0.0"

TASK_SUBMITTED = "submitted"
TASK_WORKING = "working"
TASK_COMPLETED = "completed"
TASK_FAILED = "failed"
TASK_CANCELED = "canceled"

TERMINAL_STATES = {TASK_COMPLETED, TASK_FAILED, TASK_CANCELED}


def build_agent_card(
    agent_name: str,
    agent_pub_key: str,
    base_url: str,
    skills: list[dict],
    description: str = "",
) -> dict:
    """Build an A2A v1.0.0 compatible Agent Card."""
    return {
        "agentCard": {
            "name": agent_name,
            "description": description or "Autonomous AI agent — Hermes brain, Bittensor settlement",
            "version": "1.0.0",
            "supportedInterfaces": [
                {
                    "url": f"{base_url}/a2a",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": A2A_PROTOCOL_VERSION,
                },
            ],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
            },
            "defaultInputModes": ["application/json", "text/plain"],
            "defaultOutputModes": ["application/json", "text/plain"],
            "skills": [
                {
                    "id": s["name"],
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "tags": [s.get("category", "misc")],
                }
                for s in skills
            ],
            "securitySchemes": {
                "erc8004": {
                    "type": "erc8004-identity",
                    "description": "ERC-8004 on-chain identity verification",
                },
            },
            "provider": {
                "organization": "hermes-settlement",
            },
            "identity": {
                "publicKey": agent_pub_key,
            },
        }
    }


class TaskStore:
    """In-memory task state store."""

    def __init__(self):
        self._tasks: dict[str, dict] = {}

    def create(self, task_id: str, skill: str, params: dict,
               caller: str, agent_url: str) -> dict:
        task = {
            "id": task_id,
            "state": TASK_SUBMITTED,
            "skill": skill,
            "params": params,
            "caller": caller,
            "agent_url": agent_url,
            "created_at": time.time(),
            "updated_at": time.time(),
            "result": None,
            "error": None,
        }
        self._tasks[task_id] = task
        return task

    def update_state(self, task_id: str, state: str,
                     result=None, error=None) -> Optional[dict]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        task["state"] = state
        task["updated_at"] = time.time()
        if result is not None:
            task["result"] = result
        if error is not None:
            task["error"] = error
        return task

    def get(self, task_id: str) -> Optional[dict]:
        return self._tasks.get(task_id)

    def list_active(self) -> list[dict]:
        return [t for t in self._tasks.values() if t["state"] not in TERMINAL_STATES]


task_store = TaskStore()


class AgentCardSkill(Skill):
    name = "agent.card"
    description = "Return A2A-compatible Agent Card"
    category = "agent"
    parameters = {}

    def __init__(self, agent_name: str, agent_pub_key: str,
                 base_url: str, skill_registry: SkillRegistry):
        self._agent_name = agent_name
        self._pub_key = agent_pub_key
        self._base_url = base_url
        self._registry = skill_registry

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        card = build_agent_card(
            agent_name=self._agent_name,
            agent_pub_key=self._pub_key,
            base_url=self._base_url,
            skills=self._registry.list_skills(),
        )
        return SkillResult.ok(card)


class AgentDiscoverSkill(Skill):
    name = "agent.discover"
    description = "Fetch Agent Card from a URL"
    category = "agent"
    parameters = {
        "url": {"type": "string", "required": True, "description": "Agent base URL"},
    }

    def __init__(self, transport: HttpTransport):
        self._transport = transport

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        card = await self._transport.fetch_agent_card(params["url"])
        if card:
            return SkillResult.ok(card)
        return SkillResult.fail(f"No agent card found at {params['url']}")


class AgentTaskSkill(Skill):
    name = "agent.task"
    description = "Send task request to another agent"
    category = "agent"
    parameters = {
        "agent_url": {"type": "string", "required": True},
        "category": {"type": "string", "required": True},
        "task": {"type": "string", "required": True},
        "budget_tao": {"type": "string", "required": False},
    }

    def __init__(self, transport: HttpTransport):
        self._transport = transport

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        task_id = secrets.token_hex(16)
        request = TaskRequest(
            task_id=task_id,
            buyer_id=context.agent_pub_key,
            category=params["category"],
            task_description=params["task"],
            budget_tao=params.get("budget_tao", "0.1"),
        )

        task_store.create(
            task_id=task_id,
            skill=params["category"],
            params={"task": params["task"]},
            caller=context.agent_pub_key,
            agent_url=params["agent_url"],
        )

        result = await self._transport.send_task(params["agent_url"], request)

        return SkillResult.ok({
            "task_id": task_id,
            "state": TASK_SUBMITTED,
            "agent_url": params["agent_url"],
        })


def register_agent_skills(registry: SkillRegistry, agent_name: str,
                          agent_pub_key: str, transport: HttpTransport,
                          base_url: str = "http://localhost:8080"):
    registry.register(AgentCardSkill(agent_name, agent_pub_key, base_url, registry))
    registry.register(AgentDiscoverSkill(transport))
    registry.register(AgentTaskSkill(transport))
