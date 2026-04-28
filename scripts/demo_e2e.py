"""
scripts/demo_e2e.py

End-to-end demo: register → task → Hermes execution → settle → reputation.

This is the script for the demo video. Run it with Anvil running on :8545.
Bittensor will use mock mode on Mac (real on Alienware).

Usage:
    python scripts/demo_e2e.py
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.core.agent import NousAgent, AgentConfig
from agent.daemon.llm import HermesLLM, AgentReasoner


CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def banner(msg):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {msg}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")


def step(n, msg):
    print(f"{BOLD}{GREEN}[Step {n}]{RESET} {msg}")


def info(msg):
    print(f"  {DIM}{msg}{RESET}")


def result(msg):
    print(f"  {YELLOW}{msg}{RESET}")


async def main():
    banner("Nous Agent — End-to-End Demo")
    print(f"  Stack: Hermes brain + ERC-8004 identity + Bittensor settlement")
    print(f"  Time:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ── Step 1: Initialize agent ──
    step(1, "Initializing agent...")
    config = AgentConfig(
        agent_name="nous-demo-agent",
        stake_tao="0.01",
        erc8004_rpc_url=os.environ.get("ERC8004_RPC", "http://localhost:8545"),
    )
    agent = NousAgent(config)

    # Initialize wallet
    pub_key = agent.wallet.initialize()
    info(f"Wallet pub key: {pub_key[:40]}...")
    info(f"Currency: TAO")

    # ── Step 2: Connect settlement layers ──
    step(2, "Connecting settlement layers...")

    erc_ok = await agent.identity.check_connection()
    bt_ok = await agent.settlement.check_connection()

    result(f"ERC-8004: {'LIVE (on-chain)' if erc_ok else 'mock mode'}")
    result(f"Bittensor: {'LIVE (testnet)' if bt_ok else 'mock mode'}")

    if bt_ok:
        subnet_info = await agent.settlement.get_subnet_info()
        result(f"Subnet {subnet_info.get('netuid')}: {subnet_info.get('neurons', '?')} neurons, block {subnet_info.get('block', '?')}")

    # ── Step 3: Register on-chain identity ──
    step(3, "Registering on-chain identity (ERC-8004)...")

    import hashlib, json
    capability_hash = hashlib.sha256(
        json.dumps([s.id for s in config.services]).encode()
    ).hexdigest()

    identity = await agent.identity.register_identity(
        agent_pub_key=pub_key,
        stake=config.stake_tao,
        capability_hash=capability_hash,
    )
    agent._identity_record = identity
    agent._running = True
    result(f"tx_hash: {identity.tx_hash[:40]}...")
    result(f"block: {identity.block}")
    result(f"on-chain: {not identity.mock}")

    # ── Step 4: Detect LLM backend ──
    step(4, "Detecting Hermes inference backend...")

    llm = agent.llm
    # Force backend detection
    await llm._ensure_backend()
    result(f"Backend: {llm._backend}")

    # Quick inference test
    test_resp = await llm.complete("Say 'ready' if you can hear me.", temperature=0.1)
    result(f"Inference test: {test_resp.text[:80]}")
    result(f"Latency: {test_resp.latency_ms:.0f}ms")

    # ── Step 5: Receive and evaluate a task ──
    step(5, "Receiving incoming task request...")

    task_request = {
        "task_id": "task-001",
        "type": "inference",
        "description": "Summarize the key principles of decentralized AI agent economies in 3 bullet points.",
        "requester": "0xRequesterAgent",
        "offered_payment": "0.005 TAO",
    }

    info(f"Task: {task_request['description'][:60]}...")
    info(f"Payment offered: {task_request['offered_payment']}")

    # Get balance and reputation for evaluation
    balance = await agent.settlement.get_balance(pub_key)
    rep = await agent.identity.get_reputation(pub_key)

    reasoner = agent.reasoner
    decision = await reasoner.evaluate_task(task_request, balance, rep.score)

    result(f"Decision: {json.dumps(decision, indent=2)}")

    # ── Step 6: Execute task via Hermes ──
    step(6, "Executing task via Hermes inference...")

    t0 = time.time()
    output = await reasoner.execute_task(task_request["description"])
    elapsed = time.time() - t0

    result(f"Execution time: {elapsed:.1f}s")
    print(f"\n{BOLD}  Task output:{RESET}")
    for line in output.strip().split('\n'):
        print(f"  {line}")
    print()

    # ── Step 7: Record task completion on-chain ──
    step(7, "Recording task completion on-chain (ERC-8004)...")

    tx_hash = await agent.identity.record_task(success=True)
    result(f"recordTask tx: {tx_hash[:40]}...")
    agent.tasks_completed += 1

    # ── Step 8: Check updated reputation ──
    step(8, "Querying updated on-chain reputation...")

    rep_after = await agent.identity.get_reputation(pub_key)
    result(f"Reputation score: {rep_after.score:.4f}")
    result(f"Total tasks: {rep_after.total_tasks}")
    result(f"Source: {rep_after.source}")
    result(f"On-chain: {not rep_after.mock}")

    # ── Step 9: Check balances ──
    step(9, "Checking balances...")

    eth_balance = await agent.identity.get_balance(pub_key)
    tao_balance = await agent.settlement.get_balance(pub_key)
    result(f"ETH balance: {eth_balance}")
    result(f"TAO balance: {tao_balance}")

    # ── Step 10: Agent state summary ──
    step(10, "Final agent state...")

    state = agent.state()
    print(f"\n{BOLD}  Agent State:{RESET}")
    print(f"  Running:    {state['running']}")
    print(f"  Backend:    {state['backend']}")
    print(f"  Pub key:    {state['identity']['pub_key'][:40]}...")
    print(f"  ERC-8004:   {state['identity']['erc8004_tx'][:40] if state['identity']['erc8004_tx'] else 'none'}...")
    print(f"  On-chain:   {not state['identity']['mock']}")
    print(f"  Tasks done: {state['stats']['tasks_completed']}")
    print(f"  Services:   {[s['id'] for s in state['services']]}")

    # Shutdown
    await agent.stop()

    banner("Demo Complete")
    print(f"  The agent registered on-chain, received a task,")
    print(f"  evaluated it with Hermes, executed it, recorded")
    print(f"  the result on-chain, and updated its reputation.")
    print(f"  All settlement is native — no bridges, no wrappers.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
