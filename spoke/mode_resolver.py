# SPDX-License-Identifier: MIT
"""Modal intent resolver — classifies utterances by operative mode.

Determines which of Spoke's operative modes an utterance belongs to,
enabling implicit mode switching without the user explicitly requesting
a mode change.

Two resolution layers:
  1. Mode classification — which mode does this utterance assume?
  2. Within-mode intent — what action within that mode? (deferred to
     the mode-specific resolver, e.g. SettingsMode)

Architecture: spoke-operative-modes-and-consensus-intent-resolution_2026-05-08.md
"""
from __future__ import annotations

import logging

from .consensus_resolver import ConsensusResolver, Intent, ResolverResult

logger = logging.getLogger(__name__)

# ── Mode vocabulary ────────────────────────────────────────────────────

MODE_INTENTS = [
    Intent(
        "settings",
        "The user wants to change Spoke's configuration: switch backend, "
        "switch model, change voice, change transcription, show current "
        "settings, list available models. Infrastructure commands.",
        (
            "use the big model",
            "switch to cloud",
            "what model am I using",
            "change the voice",
            "use local whisper",
            "switch to gemini",
            "list models",
            "use the fast one",
            "show settings",
            "use vmlx",
        ),
    ),
    Intent(
        "assistant",
        "The user wants to have a conversation, ask a question, get help "
        "with something, or have the assistant do a task using its tools. "
        "General assistant interaction, thinking, analysis, coding help.",
        (
            "what does this error mean",
            "help me write an email",
            "summarize this document",
            "what's the best way to do X",
            "can you explain how this works",
            "rewrite this paragraph",
            "what do you think about this",
            "draft a response to this message",
            "how do I fix this bug",
            "tell me about quantum computing",
        ),
    ),
    Intent(
        "research",
        "The user wants to search the web, look something up online, find "
        "current information, or do internet research. Requires web access.",
        (
            "search for the latest on MLX",
            "what's the news about Apple",
            "look up the mlx 0.32 release notes",
            "find me the documentation for aiohttp",
            "what happened with the OpenAI announcement",
            "search for python async best practices",
            "is there an update on the M5 chip",
            "look up how to use Metal compute shaders",
        ),
    ),
    Intent(
        "epistaxis",
        "The user wants to interact with Epistaxis: view topoi, check lane "
        "status, read attractors, see what agents are doing, manage "
        "coordination state. Operational project management.",
        (
            "what lanes are active",
            "show me the current topoi",
            "what's the status of the butterfinger packet",
            "check the attractors",
            "what are the agents working on",
            "show epistaxis state",
            "any findings pending",
            "what's the steward doing",
        ),
    ),
    Intent(
        "read_aloud",
        "The user wants something read to them, or wants Spoke to act as "
        "a screen reader / read-aloud companion. Audio output of content.",
        (
            "read this to me",
            "read the screen",
            "what does it say",
            "read the next section",
            "keep reading",
            "read that email",
            "what's on screen",
        ),
    ),
    Intent(
        "tray",
        "The user wants to type or edit text in the tray, paste something, "
        "or work with the editable text field directly.",
        (
            "let me type something",
            "open the tray",
            "I want to edit this",
            "paste that",
            "let me write it out",
        ),
    ),
]


# ── Mode resolver ──────────────────────────────────────────────────────

class ModeResolver:
    """Classify utterances into operative modes via parallel consensus."""

    def __init__(
        self,
        resolver_url: str,
        resolver_model: str,
        *,
        n: int = 8,
        timeout: float = 10.0,
        api_key: str = "",
    ):
        self._resolver = ConsensusResolver(
            base_url=resolver_url,
            model=resolver_model,
            intents=MODE_INTENTS,
            n=n,
            timeout=timeout,
            api_key=api_key,
        )

    def resolve(self, utterance: str) -> ResolverResult:
        """Classify an utterance into an operative mode."""
        result = self._resolver.resolve(utterance)
        logger.info(
            "Mode resolve: '%s' → %s (%.0f%% confidence, %d/%d, %.0fms)",
            utterance,
            result.intent_id or "AMBIGUOUS",
            result.confidence * 100,
            result.n_responses,
            result.n_requested,
            result.latency_ms,
        )
        if result.raw_votes:
            logger.info("  votes: %s", result.raw_votes)
        return result


# ── CLI smoke test ─────────────────────────────────────────────────────

def _smoke_test():
    """Run interactive or batch smoke test for mode classification."""
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description="Mode resolver smoke test")
    parser.add_argument("--url", default="http://localhost:8001", help="Model server URL")
    parser.add_argument("--model", default="", help="Model name")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("-n", type=int, default=8, help="Parallel calls")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout")
    parser.add_argument("--batch", action="store_true", help="Run built-in test battery")
    parser.add_argument("utterance", nargs="*", help="Utterance(s) to resolve")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    api_key = args.api_key or os.environ.get("OMLX_SERVER_API_KEY", "")

    model = args.model
    if not model:
        try:
            import json
            import urllib.request
            url = f"{args.url.rstrip('/')}/v1/models"
            req = urllib.request.Request(url)
            if api_key:
                req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m["id"] for m in data.get("data", []) if isinstance(m, dict)]
            if models:
                model = models[0]
                print(f"Using model: {model}")
        except Exception as e:
            print(f"Cannot reach server: {e}", file=sys.stderr)
            sys.exit(1)

    resolver = ModeResolver(
        resolver_url=args.url,
        resolver_model=model,
        n=args.n,
        timeout=args.timeout,
        api_key=api_key,
    )

    if args.batch:
        # Built-in test battery with expected modes
        tests = [
            # Settings
            ("use the big model", "settings"),
            ("switch to cloud", "settings"),
            ("what model am I using", "settings"),
            ("list models", "settings"),
            ("change the voice", "settings"),
            # Assistant
            ("what does this error mean", "assistant"),
            ("help me write an email to my boss", "assistant"),
            ("explain how async await works in python", "assistant"),
            ("what's the best way to structure this code", "assistant"),
            ("rewrite this more concisely", "assistant"),
            # Research
            ("search for the latest MLX release", "research"),
            ("what's the news about Apple silicon", "research"),
            ("look up aiohttp documentation", "research"),
            # Epistaxis
            ("what lanes are active", "epistaxis"),
            ("show the current topoi", "epistaxis"),
            ("any pending findings", "epistaxis"),
            # Read aloud
            ("read this to me", "read_aloud"),
            ("what does it say on screen", "read_aloud"),
            # Out of vocabulary
            ("nevermind", None),
            ("uhh", None),
        ]
        correct = 0
        total = len(tests)
        for utterance, expected in tests:
            result = resolver.resolve(utterance)
            got = result.intent_id
            match = "✓" if got == expected else "✗"
            if got != expected:
                print(f"  {match} '{utterance}' → {got} (expected {expected}, "
                      f"{result.confidence:.0%}, votes={result.raw_votes})")
            else:
                print(f"  {match} '{utterance}' → {got} ({result.confidence:.0%})")
                correct += 1
        print(f"\n{correct}/{total} correct ({correct/total:.0%})")
        sys.exit(0 if correct == total else 1)

    if args.utterance:
        utterance = " ".join(args.utterance)
        result = resolver.resolve(utterance)
        print(f"\nMode: {result.intent_id or 'AMBIGUOUS'} ({result.confidence:.0%})")
        if result.alternatives:
            print(f"Alternatives: {result.alternatives}")
        sys.exit(0 if result.intent_id else 1)

    # Interactive
    print(f"\nMode resolver smoke test (N={args.n}, server={args.url})")
    print("Type utterances to classify. Ctrl-C to quit.\n")
    try:
        while True:
            utterance = input(">>> ").strip()
            if not utterance:
                continue
            result = resolver.resolve(utterance)
            print(f"  → {result.intent_id or 'AMBIGUOUS'} ({result.confidence:.0%})")
            if result.alternatives:
                print(f"    alternatives: {result.alternatives}")
            print()
    except (KeyboardInterrupt, EOFError):
        print("\nDone.")


if __name__ == "__main__":
    _smoke_test()
