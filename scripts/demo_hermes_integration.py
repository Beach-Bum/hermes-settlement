"""
scripts/demo_hermes_integration.py

Demo: Hermes Agent calling settlement tools via its native tool system.

Uses Hermes 4 405B via Nous Portal inference API with tool calling.
The LLM decides which tools to call — we don't hardcode anything.
Tool dispatch goes through Hermes's actual tools/registry.py.

Run from the hermes-agent directory:
    LD_LIBRARY_PATH=... ERC8004_PRIVATE_KEY=... NOUS_API_KEY=... python3 /tmp/nous-agent/scripts/demo_hermes_integration.py
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
    # Import Hermes internals
    from tools.registry import registry
    import tools.settlement_tool  # registers our 6 tools

    settlement_tools = registry.get_tool_names_for_toolset("settlement")

    # Get tool schemas for the LLM
    tool_defs = registry.get_definitions(set(settlement_tools))

    import httpx

    nous_url = "https://inference-api.nousresearch.com/v1"
    nous_key = os.environ.get("NOUS_API_KEY", "")
    model = "nousresearch/hermes-4-405b"

    print(f"  Model:      {model}")
    print(f"  Endpoint:   {nous_url}")
    print(f"  Toolset:    settlement ({len(settlement_tools)} tools)")
    print(f"  Registry:   Hermes tools/registry.py")
    print(f"  Available:  {registry.is_toolset_available('settlement')}")
    print()

    client = httpx.AsyncClient(timeout=120.0)

    async def nous_chat(messages):
        resp = await client.post(f"{nous_url}/chat/completions",
            headers={"Authorization": f"Bearer {nous_key}"},
            json={
                "model": model,
                "messages": messages,
                "tools": tool_defs,
                "max_tokens": 500,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]

    async def chat_with_tools(user_message, history=None):
        """Send a message to Hermes model with settlement tools available."""
        messages = history or []
        messages.append({"role": "user", "content": user_message})

        user_says(user_message)

        assistant_msg = await nous_chat(messages)
        messages.append(assistant_msg)

        # Process up to 3 rounds of tool calls
        for _ in range(3):
            if not assistant_msg.get("tool_calls"):
                break

            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                func_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                result = registry.dispatch(func_name, func_args)
                tool_call(func_name, func_args, result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            assistant_msg = await nous_chat(messages)
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
    print(f"  Hermes 4 405B called settlement tools natively")
    print(f"  through Hermes's own tool registry — no wrapper, no adapter.")
    print(f"  The same tools appear in `hermes tools` alongside")
    print(f"  the 30+ built-in tools.")
    print()


if __name__ == "__main__":
    asyncio.run(run_demo())
