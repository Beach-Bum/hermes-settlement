"""
scripts/demo_hermes_integration.py

Demo: Hermes Agent calling settlement tools via its native tool system.

This runs Hermes's actual AIAgent with the settlement toolset enabled,
sending prompts that trigger on-chain operations. The LLM (hermes3:8b
via Ollama) decides which tools to call — we don't hardcode anything.

Run from the hermes-agent directory:
    LD_LIBRARY_PATH=... ERC8004_PRIVATE_KEY=... python3 /tmp/nous-agent/scripts/demo_hermes_integration.py
"""

import os
import sys
import json
import asyncio

# Must run from hermes-agent directory
sys.path.insert(0, os.getcwd())

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def banner(msg):
    print(f"\n{BOLD}{CYAN}{'='*70}{RESET}")
    print(f"{BOLD}{CYAN}  {msg}{RESET}")
    print(f"{BOLD}{CYAN}{'='*70}{RESET}\n")


def user_says(msg):
    print(f"\n{BOLD}{GREEN}User >{RESET} {msg}")


def agent_says(msg):
    for line in msg.strip().split('\n'):
        print(f"  {YELLOW}{line}{RESET}")


def tool_call(name, args, result):
    print(f"  {DIM}[tool: {name}]{RESET}")
    try:
        parsed = json.loads(result)
        print(f"  {DIM}{json.dumps(parsed, indent=2)}{RESET}")
    except (json.JSONDecodeError, TypeError):
        print(f"  {DIM}{str(result)[:200]}{RESET}")


async def run_demo():
    banner("Hermes Agent + Settlement Toolset Demo")
    print(f"  Model:    hermes3:8b (Ollama, local)")
    print(f"  Toolset:  settlement (ERC-8004 + Bittensor)")
    print(f"  Registry: Hermes tools/registry.py")
    print()

    # Import Hermes internals
    from tools.registry import registry
    import tools.settlement_tool  # registers our 6 tools

    settlement_tools = registry.get_tool_names_for_toolset("settlement")
    print(f"  Registered tools: {settlement_tools}")
    print(f"  Available: {registry.is_toolset_available('settlement')}")

    # Get tool schemas for the LLM
    tool_defs = registry.get_definitions(set(settlement_tools))
    print(f"  Tool definitions for LLM: {len(tool_defs)}")
    print()

    # Use Ollama directly (same as Hermes does internally)
    import httpx

    ollama_url = "http://localhost:11434"
    model = "hermes3:8b"

    client = httpx.AsyncClient(timeout=120.0)

    async def ollama_chat(messages):
        resp = await client.post(f"{ollama_url}/api/chat", json={
            "model": model,
            "messages": messages,
            "tools": tool_defs,
            "stream": False,
        })
        resp.raise_for_status()
        return resp.json()["message"]

    async def chat_with_tools(user_message, history=None):
        """Send a message to Hermes model with settlement tools available."""
        messages = history or []
        messages.append({"role": "user", "content": user_message})

        user_says(user_message)

        assistant_msg = await ollama_chat(messages)
        messages.append(assistant_msg)

        # Process up to 3 rounds of tool calls
        for _ in range(3):
            if not assistant_msg.get("tool_calls"):
                break

            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                func_args = tc["function"]["arguments"]
                result = registry.dispatch(func_name, func_args)
                tool_call(func_name, func_args, result)
                messages.append({"role": "tool", "content": result})

            assistant_msg = await ollama_chat(messages)
            messages.append(assistant_msg)

        if assistant_msg.get("content"):
            agent_says(assistant_msg["content"])

        return messages

    # System prompt
    system = [{
        "role": "system",
        "content": (
            "You are Hermes, an autonomous AI agent by Nous Research. "
            "You have settlement tools for on-chain identity (ERC-8004) and "
            "Bittensor network operations. Use them when the user asks about "
            "blockchain identity, reputation, balances, or subnet info. "
            "Be concise."
        ),
    }]

    # --- Conversation ---

    history = list(system)

    history = await chat_with_tools(
        "Register my agent identity on-chain with 0.01 ETH stake and capabilities: inference, code_review",
        history,
    )

    history = await chat_with_tools(
        "What does the Bittensor subnet look like right now?",
        history,
    )

    history = await chat_with_tools(
        "I just completed a task successfully. Record it and show me my updated reputation.",
        history,
    )

    history = await chat_with_tools(
        "Check all my balances — ETH and TAO.",
        history,
    )

    await client.aclose()

    banner("Demo Complete")
    print(f"  Hermes (hermes3:8b) called settlement tools natively")
    print(f"  through its own tool registry — no wrapper, no adapter.")
    print(f"  The same tools appear in `hermes tools` alongside")
    print(f"  the 40+ built-in tools.")
    print()


if __name__ == "__main__":
    asyncio.run(run_demo())
