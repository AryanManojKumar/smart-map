"""
Capability Loader — reads sub-agent markdown docs and produces a compact
summary string for injection into the supervisor's system prompt.

Docs are loaded once at import time and cached. The summary is a concise
bullet-list (not the full markdown) so the supervisor LLM gets just enough
context to make good routing decisions without prompt bloat.
"""

import os
from pathlib import Path
from typing import Dict

DOCS_DIR = Path(__file__).parent / "docs"


def _load_raw_docs() -> Dict[str, str]:
    """Read all .md files from the docs directory into a name→content dict."""
    docs = {}
    if not DOCS_DIR.is_dir():
        return docs
    for md_file in sorted(DOCS_DIR.glob("*.md")):
        node_name = md_file.stem
        docs[node_name] = md_file.read_text(encoding="utf-8")
    return docs


def _extract_section(text: str, heading: str) -> str:
    """Pull out the text under a specific markdown ## heading."""
    lines = text.split("\n")
    capture = False
    result = []
    for line in lines:
        if line.strip().startswith("## ") and heading.lower() in line.lower():
            capture = True
            continue
        if capture and line.strip().startswith("## "):
            break
        if capture:
            stripped = line.strip()
            if stripped and not stripped.startswith("|---"):
                result.append(stripped)
    return "\n".join(result)


def _build_node_summary(name: str, raw: str) -> str:
    """Compress one doc into a short summary suitable for the supervisor prompt."""
    purpose = _extract_section(raw, "Purpose")
    when_to_use = _extract_section(raw, "When to use")
    when_not = _extract_section(raw, "When NOT to use")

    lines = [f"### {name}"]
    if purpose:
        lines.append(purpose.split("\n")[0])
    if when_to_use:
        lines.append("Use when:")
        for l in when_to_use.split("\n"):
            l = l.strip()
            if l.startswith("- "):
                lines.append(f"  {l}")
    if when_not:
        lines.append("Do NOT use when:")
        for l in when_not.split("\n"):
            l = l.strip()
            if l.startswith("- "):
                lines.append(f"  {l}")
    return "\n".join(lines)


def build_capability_summary(raw_docs: Dict[str, str] = None) -> str:
    """
    Build a compact capability summary from the raw docs.

    The order matters: routing_node and search_node are the two most important
    nodes for the supervisor to distinguish between, so they come first.
    """
    if raw_docs is None:
        raw_docs = _load_raw_docs()

    preferred_order = [
        "routing_node",
        "search_node",
        "disambiguation_node",
        "route_question_node",
        "conversation_node",
    ]

    summaries = []
    for name in preferred_order:
        if name in raw_docs:
            summaries.append(_build_node_summary(name, raw_docs[name]))

    for name, raw in raw_docs.items():
        if name not in preferred_order:
            summaries.append(_build_node_summary(name, raw))

    return "\n\n".join(summaries)


# ── Module-level cache ──────────────────────────
# Loaded once on first import; zero cost on subsequent requests.

RAW_DOCS: Dict[str, str] = _load_raw_docs()
CAPABILITY_SUMMARY: str = build_capability_summary(RAW_DOCS)
