"""
agent/core/wallet.py

Autonomous wallet with user-configurable spending policy.
Adapted for TAO (Bittensor native currency).

Security design:
  - Agent has its own keypair, separate from the user's wallet
  - Every spend checked against policy BEFORE signing
  - All transactions logged to audit trail
  - User can freeze wallet instantly
  - Earning is unrestricted
"""

import json
import time
import os
import secrets
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from agent.core.keystore import AgentKeystore, SecureKey, get_or_create_key

WALLET_DIR = Path.home() / ".hermes-settlement" / "wallet"
POLICY_FILE = WALLET_DIR / "policy.json"
AUDIT_FILE = WALLET_DIR / "audit.jsonl"


@dataclass
class SpendingPolicy:
    max_per_tx_tao: float = 1.0
    daily_cap_tao: float = 10.0
    approved_categories: list = field(default_factory=lambda: [
        "inference", "research", "code", "data"
    ])
    max_escrow_timeout_ms: int = 300_000
    max_slash_bps: int = 1000
    min_counterparty_reputation: float = 0.5
    frozen: bool = False

    def save(self):
        WALLET_DIR.mkdir(parents=True, exist_ok=True)
        POLICY_FILE.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> "SpendingPolicy":
        if POLICY_FILE.exists():
            data = json.loads(POLICY_FILE.read_text())
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        policy = cls()
        policy.save()
        return policy


@dataclass
class AuditEntry:
    ts: float
    action: str
    amount_tao: float
    counterparty: str
    session_id: str
    category: str
    status: str
    reason: str
    balance_after: float


class AgentWallet:
    """
    Autonomous wallet for the Nous agent. TAO-denominated.
    """

    def __init__(self, agent_name: str = "hermes-settlement"):
        self.agent_name = agent_name
        self._key: Optional[SecureKey] = None
        self.pub_key_hex: str = ""
        self.policy = SpendingPolicy.load()
        self._balance_tao: float = 0.0
        self._spent_today: float = 0.0
        self._earned_total: float = 0.0
        self._spend_window: list[tuple[float, float]] = []
        self._audit: list[AuditEntry] = []
        self._pending_escrows: dict[str, float] = {}

        WALLET_DIR.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> str:
        self._key = get_or_create_key(self.agent_name)

        import hashlib
        self.pub_key_hex = "03" + hashlib.sha256(self._key.bytes).hexdigest()[:64]

        balance_file = WALLET_DIR / "balance.json"
        if balance_file.exists():
            data = json.loads(balance_file.read_text())
            self._balance_tao = data.get("balance", 0.0)
            self._earned_total = data.get("earned_total", 0.0)

        return self.pub_key_hex

    def _save_balance(self):
        balance_file = WALLET_DIR / "balance.json"
        balance_file.write_text(json.dumps({
            "balance": self._balance_tao,
            "earned_total": self._earned_total,
            "updated": time.time(),
        }))

    def fund(self, amount_tao: float, from_user: str = "user") -> dict:
        self._balance_tao += amount_tao
        self._save_balance()
        self._log_audit("fund", amount_tao, from_user, "", "", "completed",
                        f"Funded by {from_user}")
        return {"balance": self._balance_tao, "funded": amount_tao}

    def check_spend(self, amount_tao: float, category: str,
                    counterparty_rep: float = 1.0,
                    escrow_timeout_ms: int = 60000,
                    slash_bps: int = 500) -> tuple[bool, str]:
        if self.policy.frozen:
            return False, "wallet frozen"
        if amount_tao > self._balance_tao:
            return False, f"insufficient balance: {self._balance_tao:.4f} TAO"
        if amount_tao > self.policy.max_per_tx_tao:
            return False, f"exceeds per-tx limit: {self.policy.max_per_tx_tao:.4f} TAO"
        self._prune_spend_window()
        daily_total = sum(amt for _, amt in self._spend_window)
        if daily_total + amount_tao > self.policy.daily_cap_tao:
            return False, f"exceeds daily cap"
        if category not in self.policy.approved_categories:
            return False, f"category '{category}' not approved"
        if counterparty_rep < self.policy.min_counterparty_reputation:
            return False, f"counterparty reputation too low"
        return True, "approved"

    def spend(self, amount_tao: float, counterparty: str, session_id: str,
              category: str) -> tuple[bool, str]:
        allowed, reason = self.check_spend(amount_tao, category)
        if not allowed:
            self._log_audit("spend", amount_tao, counterparty, session_id,
                           category, "denied", reason)
            return False, reason
        self._balance_tao -= amount_tao
        self._spend_window.append((time.time(), amount_tao))
        self._save_balance()
        self._log_audit("spend", amount_tao, counterparty, session_id,
                       category, "approved", "policy check passed")
        return True, "approved"

    def earn(self, amount_tao: float, counterparty: str, session_id: str,
             category: str) -> float:
        self._balance_tao += amount_tao
        self._earned_total += amount_tao
        self._save_balance()
        self._log_audit("earn", amount_tao, counterparty, session_id,
                       category, "completed", "Task payment received")
        return self._balance_tao

    def freeze(self) -> dict:
        self.policy.frozen = True
        self.policy.save()
        return {"frozen": True, "balance": self._balance_tao}

    def unfreeze(self) -> dict:
        self.policy.frozen = False
        self.policy.save()
        return {"frozen": False, "balance": self._balance_tao}

    def state(self) -> dict:
        self._prune_spend_window()
        daily_spent = sum(amt for _, amt in self._spend_window)
        locked = sum(self._pending_escrows.values())
        return {
            "pub_key": self.pub_key_hex,
            "balance_tao": round(self._balance_tao, 4),
            "available_tao": round(self._balance_tao - locked, 4),
            "locked_in_escrow_tao": round(locked, 4),
            "earned_total_tao": round(self._earned_total, 4),
            "spent_today_tao": round(daily_spent, 4),
            "frozen": self.policy.frozen,
        }

    def audit_log(self, limit: int = 50) -> list[dict]:
        return [asdict(e) for e in self._audit[-limit:]]

    def _prune_spend_window(self):
        cutoff = time.time() - 86400
        self._spend_window = [(t, a) for t, a in self._spend_window if t > cutoff]

    def _log_audit(self, action, amount, counterparty, session_id, category, status, reason):
        entry = AuditEntry(
            ts=time.time(), action=action, amount_tao=amount,
            counterparty=counterparty[:20] if counterparty else "",
            session_id=session_id[:16] if session_id else "",
            category=category, status=status, reason=reason,
            balance_after=self._balance_tao,
        )
        self._audit.append(entry)
        with open(AUDIT_FILE, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def shutdown(self):
        if self._key:
            self._key.zero()
            self._key = None
