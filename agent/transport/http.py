"""
agent/transport/http.py

A2A-over-HTTP transport — direct agent-to-agent communication.

Replaces Logos Messaging (Waku) with plain HTTP for the Nous demo.
P2P transport is a separate sovereignty thesis that stays in Agora.
This project uses HTTP because the demo is about the agent lifecycle
(register, discover, task, settle, reputation), not the transport layer.

Implements A2A v1.0.0 JSON-RPC over HTTP.
"""

import asyncio
import json
import time
import secrets
import httpx
from typing import Callable, Optional
from dataclasses import dataclass, field
from collections import defaultdict


# Security constants
MESSAGE_VALIDITY_WINDOW_MS = 5 * 60 * 1000
RATE_LIMIT_PER_SENDER_PER_MIN = 10


class NonceCache:
    """Tracks seen message nonces to prevent replay attacks."""

    def __init__(self):
        self._seen: dict[str, int] = {}

    def check_and_record(self, nonce: str) -> bool:
        now = int(time.time() * 1000)
        self._evict_expired(now)
        if nonce in self._seen:
            return False
        self._seen[nonce] = now + MESSAGE_VALIDITY_WINDOW_MS * 2
        return True

    def _evict_expired(self, now: int):
        expired = [n for n, exp in self._seen.items() if exp <= now]
        for n in expired:
            del self._seen[n]


class RateLimiter:
    """Per-sender sliding window rate limiter."""

    def __init__(self, max_per_min: int = RATE_LIMIT_PER_SENDER_PER_MIN):
        self._max = max_per_min
        self._windows: dict[str, list[int]] = defaultdict(list)

    def allow(self, sender_id: str) -> bool:
        now = int(time.time() * 1000)
        window_start = now - 60_000
        msgs = [t for t in self._windows[sender_id] if t > window_start]
        self._windows[sender_id] = msgs
        if len(msgs) >= self._max:
            return False
        self._windows[sender_id].append(now)
        return True


@dataclass
class CapabilityService:
    id: str
    category: str
    price_per_unit: str
    currency: str = "TAO"
    model: Optional[str] = None
    context_window: Optional[int] = None
    avg_latency_ms: Optional[int] = None


@dataclass
class CapabilityManifest:
    agent_id: str
    identity_tx_hash: str
    stake: str
    reputation: float
    capabilities: list

    def to_message(self, sign_fn: Callable) -> dict:
        data = {
            "version": "nous/1",
            "type": "capability_manifest",
            "agentId": self.agent_id,
            "identityTxHash": self.identity_tx_hash,
            "stake": self.stake,
            "reputation": self.reputation,
            "capabilities": [
                c.__dict__ if hasattr(c, '__dict__') else c
                for c in self.capabilities
            ],
            "ts": int(time.time() * 1000),
            "nonce": secrets.token_hex(16),
        }
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        data["sig"] = sign_fn(canonical.encode())
        return data


@dataclass
class TaskRequest:
    """A2A task request sent between agents."""
    task_id: str
    buyer_id: str
    category: str
    task_description: str
    budget_tao: str
    buyer_nonce: str = field(default_factory=lambda: secrets.token_hex(16))

    def to_a2a_message(self) -> dict:
        return {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": json.dumps({
                        "task_id": self.task_id,
                        "category": self.category,
                        "task": self.task_description,
                        "budget": self.budget_tao,
                    })}],
                    "taskId": self.task_id,
                    "metadata": {
                        "sender": self.buyer_id,
                        "transport": "http",
                        "nonce": self.buyer_nonce,
                    },
                },
            },
        }


class HttpTransport:
    """
    Direct HTTP transport for A2A communication.

    Agents expose /.well-known/agent-card.json and accept
    JSON-RPC requests at their base URL.
    """

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self._nonce_cache = NonceCache()
        self._rate_limiter = RateLimiter()

    async def send_task(self, agent_url: str, task: TaskRequest) -> dict:
        """Send a task request to another agent via HTTP."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{agent_url}/a2a",
                    json=task.to_a2a_message(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            print(f"[Transport] Failed to send task to {agent_url}: {e}")
            return {"error": str(e)}

    async def fetch_agent_card(self, agent_url: str) -> Optional[dict]:
        """Fetch an agent's A2A Agent Card."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{agent_url}/.well-known/agent-card.json",
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            print(f"[Transport] Failed to fetch agent card from {agent_url}: {e}")
        return None

    async def broadcast_capabilities(self, manifest: CapabilityManifest,
                                      sign_fn: Callable,
                                      discovery_urls: list[str] = None) -> bool:
        """Broadcast capabilities to known discovery endpoints."""
        msg = manifest.to_message(sign_fn)
        success = False
        for url in (discovery_urls or []):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(f"{url}/capabilities", json=msg)
                    if resp.status_code == 200:
                        success = True
            except Exception:
                pass
        if not discovery_urls:
            print(f"[Transport] Capabilities ready (no discovery endpoints configured)")
            success = True
        return success
