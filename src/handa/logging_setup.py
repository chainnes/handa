"""Stdout logging. The API key is never written, even if a provider echoes it."""

import logging
import os

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        logging.getLogger().setLevel(level.upper())
        return
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Chroma and its HTTP client are noisy at INFO and try to phone home.
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
    for name in ("chromadb", "httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Chroma 0.5 still calls PostHog when telemetry is off, and this PostHog build rejects the call.
    logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
    _CONFIGURED = True


def redact(text: str, secret: str = "") -> str:
    if secret and secret in text:
        text = text.replace(secret, "[redacted]")
    return text[:500]
