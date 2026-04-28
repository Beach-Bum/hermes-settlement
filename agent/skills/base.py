"""
agent/skills/base.py

Skill SDK — base classes and registry for pluggable agent skills.
"""

import asyncio
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SkillContext:
    """Runtime context passed to every skill execution."""
    agent_pub_key: str = ""
    wallet_balance: float = 0.0
    caller: str = "owner"
    task_id: Optional[str] = None
    timeout_ms: int = 30000


@dataclass
class SkillResult:
    """Standardized result from skill execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0

    @classmethod
    def ok(cls, data: Any = None, duration_ms: float = 0.0) -> "SkillResult":
        return cls(success=True, data=data, duration_ms=duration_ms)

    @classmethod
    def fail(cls, error: str, duration_ms: float = 0.0) -> "SkillResult":
        return cls(success=False, error=error, duration_ms=duration_ms)

    def to_dict(self) -> dict:
        d = {"success": self.success, "duration_ms": round(self.duration_ms, 1)}
        if self.success:
            d["data"] = self.data
        else:
            d["error"] = self.error
        return d


class Skill(ABC):
    """Base class for all agent skills."""

    name: str = ""
    description: str = ""
    parameters: dict = {}
    category: str = "misc"
    requires_approval: bool = False

    @abstractmethod
    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        ...

    def validate_params(self, params: dict) -> Optional[str]:
        for param_name, schema in self.parameters.items():
            if schema.get("required", False) and param_name not in params:
                return f"Missing required parameter: {param_name}"
            if param_name in params:
                expected_type = schema.get("type", "string")
                value = params[param_name]
                if expected_type == "string" and not isinstance(value, str):
                    return f"Parameter '{param_name}' must be a string"
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    return f"Parameter '{param_name}' must be a number"
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return f"Parameter '{param_name}' must be a boolean"
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "requires_approval": self.requires_approval,
        }


class SkillRegistry:
    """Registry of available skills with isolated execution."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' already registered")
        if not skill.name:
            raise ValueError("Skill must have a non-empty name")
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        return [s.to_dict() for s in self._skills.values()]

    def list_by_category(self, category: str) -> list[dict]:
        return [s.to_dict() for s in self._skills.values() if s.category == category]

    async def invoke(self, name: str, params: dict, context: SkillContext) -> SkillResult:
        skill = self._skills.get(name)
        if not skill:
            return SkillResult.fail(f"Unknown skill: {name}")

        error = skill.validate_params(params)
        if error:
            return SkillResult.fail(error)

        t0 = time.time()
        try:
            result = await asyncio.wait_for(
                skill.execute(params, context),
                timeout=context.timeout_ms / 1000.0,
            )
            result.duration_ms = (time.time() - t0) * 1000
            return result
        except asyncio.TimeoutError:
            duration = (time.time() - t0) * 1000
            return SkillResult.fail(f"Skill '{name}' timed out after {context.timeout_ms}ms", duration)
        except Exception as e:
            duration = (time.time() - t0) * 1000
            traceback.print_exc()
            return SkillResult.fail(f"Skill '{name}' failed: {type(e).__name__}: {e}", duration)

    @property
    def count(self) -> int:
        return len(self._skills)
