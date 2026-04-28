"""
Test the settlement tools as standalone async calls (without Hermes registry).
Validates the tool handlers work before copying into hermes-agent/tools/.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock the tools.registry import so settlement_tool.py can be tested standalone
import types
mock_registry_module = types.ModuleType("tools")
mock_registry_module.registry = types.ModuleType("tools.registry")

class MockRegistry:
    def register(self, **kwargs):
        print(f"  [mock-registry] Registered: {kwargs['name']} (toolset={kwargs['toolset']})")
mock_registry_module.registry.registry = MockRegistry()
sys.modules["tools"] = mock_registry_module
sys.modules["tools.registry"] = mock_registry_module.registry

from hermes_toolset.settlement_tool import (
    _handle_register, _handle_reputation, _handle_record_task,
    _handle_balance, _handle_subnet_info,
)

CYAN = "\033[36m"
GREEN = "\033[32m"
RESET = "\033[0m"

def step(msg):
    print(f"\n{GREEN}▶ {msg}{RESET}")

async def main():
    print(f"{CYAN}Settlement Toolset — Standalone Test{RESET}\n")

    step("settlement_register")
    r = await _handle_register({"pub_key": "hermes-test", "stake": "0.01", "capabilities": ["inference"]})
    print(f"  {json.loads(r)}")

    step("settlement_reputation")
    r = await _handle_reputation({"agent_id": "self"})
    print(f"  {json.loads(r)}")

    step("settlement_record_task (success=true)")
    r = await _handle_record_task({"success": True})
    print(f"  {json.loads(r)}")

    step("settlement_reputation (after task)")
    r = await _handle_reputation({"agent_id": "self"})
    print(f"  {json.loads(r)}")

    step("settlement_balance")
    r = await _handle_balance({"agent_id": "self"})
    print(f"  {json.loads(r)}")

    step("settlement_subnet_info")
    r = await _handle_subnet_info({})
    print(f"  {json.loads(r)}")

    print(f"\n{CYAN}All tools working.{RESET}")

if __name__ == "__main__":
    asyncio.run(main())
