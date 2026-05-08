# SPDX-License-Identifier: MIT
"""Consensus intent resolver for Spoke operative modes.

Resolves operator utterances to bounded intents by launching N parallel
non-streaming calls to a small local model with reasoning disabled.
Convergence across the N responses is the confidence signal — no
meta-model call needed.

Architecture: spoke-operative-modes-and-consensus-intent-resolution_2026-05-08.md
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Intent:
    """A single resolvable intent in an operative mode's vocabulary."""
    id: str
    description: str
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolverResult:
    """Result of a consensus resolution attempt."""
    intent_id: str | None          # winning intent, or None if no consensus
    confidence: float              # fraction of respondents that agreed (0.0–1.0)
    alternatives: list[str]        # other intent_ids that got votes, descending
    raw_votes: dict[str, int]      # intent_id → count
    latency_ms: float              # wall-clock time for the full resolution
    n_responses: int               # how many of N calls returned successfully
    n_requested: int               # N that were launched


def _build_system_prompt(intents: Sequence[Intent]) -> str:
    """Build a minimal system prompt for intent classification."""
    lines = [
        "You are an intent classifier. The user will say something.",
        "Reply with EXACTLY one of these intent IDs and nothing else.",
        "Do not explain. Do not add punctuation. Just the intent ID.",
        "",
        "Available intents:",
    ]
    for intent in intents:
        lines.append(f"  {intent.id} — {intent.description}")
        for ex in intent.examples:
            lines.append(f"    example: \"{ex}\"")
    lines.append("")
    lines.append("If the utterance doesn't match any intent, reply: unknown")
    return "\n".join(lines)


def _single_call(
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: float,
) -> str | None:
    """Make one non-streaming chat completion call. Returns the intent string
    or None on failure."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices", [])
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content", "")
        # Strip whitespace and any accidental punctuation the model might add
        return content.strip().strip("\"'`.").strip()
    except Exception as e:
        logger.debug("Consensus call failed: %s", e)
        return None


class ConsensusResolver:
    """Resolve utterances to intents via parallel consensus.

    Usage:
        resolver = ConsensusResolver(
            base_url="http://localhost:8080",
            model="qwen3.6-3b-2bit",
            intents=[
                Intent("switch_backend_local", "Switch to local backend", ("use local", "switch to omlx")),
                ...
            ],
            n=8,
        )
        result = resolver.resolve("switch to the big model")
        if result.confidence >= 0.6:
            apply(result.intent_id)
        else:
            show_alternatives(result.alternatives)
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        intents: Sequence[Intent],
        *,
        n: int = 8,
        timeout: float = 5.0,
        api_key: str = "",
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._intents = list(intents)
        self._intent_ids = {i.id for i in intents}
        self._intent_ids.add("unknown")
        self._n = n
        self._timeout = timeout
        self._api_key = api_key
        self._system_prompt = _build_system_prompt(intents)

        # Detect version prefix in URL (same logic as CommandClient)
        from urllib.parse import urlparse
        path = urlparse(self._base_url).path.rstrip("/")
        self._url_has_version_prefix = any(
            seg.startswith("v") and seg[1:].replace("beta", "").isdigit()
            for seg in path.split("/") if seg
        )

    def _chat_url(self) -> str:
        if self._url_has_version_prefix:
            return f"{self._base_url}/chat/completions"
        return f"{self._base_url}/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        h["X-Spoke-Pathway"] = "consensus-resolver"
        return h

    def _payload(self, utterance: str) -> dict:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": utterance},
            ],
            "stream": False,
            "temperature": 0.3,
            "max_tokens": 32,
            "chat_template_kwargs": {"enable_thinking": False},
        }

    def resolve(self, utterance: str) -> ResolverResult:
        """Launch N parallel calls and return consensus result.

        Blocks until all N calls complete or timeout. Thread-safe.
        """
        t0 = time.monotonic()
        url = self._chat_url()
        headers = self._headers()
        payload = self._payload(utterance)

        results: list[str | None] = [None] * self._n
        threads: list[threading.Thread] = []

        def _worker(idx: int):
            results[idx] = _single_call(url, headers, payload, self._timeout)

        for i in range(self._n):
            t = threading.Thread(target=_worker, args=(i,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=self._timeout + 1.0)

        elapsed_ms = (time.monotonic() - t0) * 1000

        # Tally votes
        votes: dict[str, int] = {}
        n_ok = 0
        for raw in results:
            if raw is None:
                continue
            n_ok += 1
            # Normalize: lowercase, strip, take first word if model babbled
            normalized = raw.lower().split()[0] if raw.split() else "unknown"
            # Check against known intent IDs (case-insensitive match)
            matched = None
            for iid in self._intent_ids:
                if normalized == iid.lower():
                    matched = iid
                    break
            if matched is None:
                # Fuzzy: check if normalized is a substring of any intent ID
                for iid in self._intent_ids:
                    if normalized in iid.lower() or iid.lower() in normalized:
                        matched = iid
                        break
            intent_key = matched or "unknown"
            votes[intent_key] = votes.get(intent_key, 0) + 1

        if not votes or n_ok == 0:
            return ResolverResult(
                intent_id=None,
                confidence=0.0,
                alternatives=[],
                raw_votes=votes,
                latency_ms=elapsed_ms,
                n_responses=n_ok,
                n_requested=self._n,
            )

        # Sort by vote count descending
        ranked = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
        winner_id, winner_count = ranked[0]
        confidence = winner_count / n_ok

        alternatives = [iid for iid, _ in ranked[1:] if iid != winner_id]

        # Don't return "unknown" as a positive resolution
        resolved_id = winner_id if winner_id != "unknown" else None

        return ResolverResult(
            intent_id=resolved_id,
            confidence=confidence,
            alternatives=alternatives,
            raw_votes=votes,
            latency_ms=elapsed_ms,
            n_responses=n_ok,
            n_requested=self._n,
        )
