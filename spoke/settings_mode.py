# SPDX-License-Identifier: MIT
"""Settings mode for Spoke — consensus-resolved infrastructure commands.

This is the first operative mode prototype. It proves out the consensus
resolver architecture on a small, enumerable intent vocabulary before
extending to larger mode vocabularies.

Intent vocabulary covers: backend switching, model switching, show current
settings, list available models.

Architecture: spoke-operative-modes-and-consensus-intent-resolution_2026-05-08.md
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from .consensus_resolver import ConsensusResolver, Intent, ResolverResult

logger = logging.getLogger(__name__)

# ── Intent vocabulary ──────────────────────────────────────────────────

SETTINGS_INTENTS = [
    # Backend switching
    Intent(
        "switch_backend_local",
        "Switch assistant to local backend (omlx or vmlx on this machine)",
        ("use local", "switch to local", "go local", "use omlx", "use vmlx",
         "switch to omlx", "switch to vmlx", "local model"),
    ),
    Intent(
        "switch_backend_sidecar",
        "Switch assistant to sidecar backend (remote server on LAN)",
        ("use sidecar", "switch to sidecar", "use the remote server",
         "use the other machine"),
    ),
    Intent(
        "switch_backend_cloud",
        "Switch assistant to cloud backend (Gemini or OpenRouter)",
        ("use cloud", "switch to cloud", "use gemini", "use openrouter",
         "go cloud", "switch to gemini"),
    ),

    # Model switching
    Intent(
        "switch_model_bigger",
        "Switch to a bigger/more capable model",
        ("use the big model", "bigger model", "use the 35B",
         "switch to the large model", "more capable model", "use the smart one"),
    ),
    Intent(
        "switch_model_smaller",
        "Switch to a smaller/faster model",
        ("use the small model", "smaller model", "use the fast one",
         "switch to the quick model", "use the 3B", "faster model"),
    ),
    Intent(
        "switch_model_by_name",
        "Switch to a specific model by name",
        ("use qwen", "switch to llama", "use nemotron",
         "switch to the qwen model"),
    ),

    # Informational
    Intent(
        "show_current_settings",
        "Show the current backend, model, and configuration",
        ("what model am I using", "show settings", "current settings",
         "what backend", "which model", "status", "show config"),
    ),
    Intent(
        "list_available_models",
        "List available models on the current backend",
        ("list models", "what models are available", "show models",
         "available models"),
    ),

    # TTS
    Intent(
        "switch_tts",
        "Change text-to-speech settings (voice, backend, model)",
        ("change voice", "switch tts", "different voice",
         "use a different voice", "tts settings"),
    ),

    # Whisper / transcription
    Intent(
        "switch_transcription",
        "Change transcription/whisper settings",
        ("change whisper", "switch transcription", "use cloud whisper",
         "use local whisper", "transcription settings"),
    ),
]


# ── Settings mode controller ───────────────────────────────────────────

class SettingsMode:
    """Operative mode for infrastructure configuration.

    Wraps ConsensusResolver with the settings intent vocabulary and
    provides action dispatch for resolved intents.
    """

    def __init__(
        self,
        resolver_url: str,
        resolver_model: str,
        *,
        n: int = 8,
        timeout: float = 5.0,
        api_key: str = "",
        on_result: Callable[[ResolverResult], None] | None = None,
    ):
        self._resolver = ConsensusResolver(
            base_url=resolver_url,
            model=resolver_model,
            intents=SETTINGS_INTENTS,
            n=n,
            timeout=timeout,
            api_key=api_key,
        )
        self._on_result = on_result

    def resolve(self, utterance: str) -> ResolverResult:
        """Resolve an utterance to a settings intent."""
        result = self._resolver.resolve(utterance)
        logger.info(
            "Settings resolve: '%s' → %s (%.0f%% confidence, %d/%d responses, %.0fms)",
            utterance,
            result.intent_id or "AMBIGUOUS",
            result.confidence * 100,
            result.n_responses,
            result.n_requested,
            result.latency_ms,
        )
        if result.raw_votes:
            logger.info("  votes: %s", result.raw_votes)
        if result.alternatives:
            logger.info("  alternatives: %s", result.alternatives)
        if self._on_result:
            self._on_result(result)
        return result


# ── CLI smoke test ─────────────────────────────────────────────────────

def _smoke_test():
    """Run interactive smoke test against a running server."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Settings mode consensus resolver smoke test")
    parser.add_argument("--url", default="http://localhost:8080", help="Model server URL")
    parser.add_argument("--model", default="", help="Model name (empty = use server default)")
    parser.add_argument("--api-key", default=None, help="API key (default: $OMLX_SERVER_API_KEY)")
    parser.add_argument("-n", type=int, default=8, help="Number of parallel calls")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-call timeout in seconds")
    parser.add_argument("utterance", nargs="*", help="Utterance to resolve (interactive if omitted)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    import os
    api_key = args.api_key or os.environ.get("OMLX_SERVER_API_KEY", "")

    model = args.model
    if not model:
        # Try to get first model from server
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
            else:
                print("No models found on server", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Cannot reach server at {args.url}: {e}", file=sys.stderr)
            sys.exit(1)

    mode = SettingsMode(
        resolver_url=args.url,
        resolver_model=model,
        n=args.n,
        timeout=args.timeout,
        api_key=api_key,
    )

    if args.utterance:
        utterance = " ".join(args.utterance)
        result = mode.resolve(utterance)
        print(f"\nResult: {result.intent_id or 'AMBIGUOUS'} ({result.confidence:.0%})")
        if result.alternatives:
            print(f"Alternatives: {result.alternatives}")
        sys.exit(0 if result.intent_id else 1)

    # Interactive loop
    print(f"\nSettings mode smoke test (N={args.n}, server={args.url})")
    print("Type utterances to resolve. Ctrl-C to quit.\n")
    try:
        while True:
            utterance = input(">>> ").strip()
            if not utterance:
                continue
            result = mode.resolve(utterance)
            print(f"  → {result.intent_id or 'AMBIGUOUS'} ({result.confidence:.0%})")
            if result.alternatives:
                print(f"    alternatives: {result.alternatives}")
            print()
    except (KeyboardInterrupt, EOFError):
        print("\nDone.")


if __name__ == "__main__":
    _smoke_test()
