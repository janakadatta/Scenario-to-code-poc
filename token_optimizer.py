"""
Token optimization for the codegen pipeline.

Two problems this solves:
1. Uploaded documents can be large (a full HLD doc can be thousands of
   words). Sending that entire thing, verbatim, into the final code
   generation prompt burns a lot of tokens on a document generation only
   needs 10% of.
2. Confluence coding standards and the Java skill file don't change between
   runs, so re-fetching/re-sending them identically every single time is
   wasted cost.

This module keeps a rough token estimate, summarizes long documents down to
their essential structure with a cheap "map-reduce" pass before they hit the
main generation call, and caches anything that doesn't change run-to-run.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

# Very rough rule of thumb (roughly 4 characters per token for English
# text). This is not exact - Gemini doesn't publish a simple tokenizer for
# quick local estimation - but it's good enough to decide "is this small
# enough to just send as-is, or does it need summarizing first."
CHARS_PER_TOKEN_ESTIMATE = 4

# If a document's estimated token count is below this, skip summarization
# entirely and send it as-is - summarizing a short document usually costs
# more tokens (an extra LLM call) than it saves.
SUMMARIZE_THRESHOLD_TOKENS = 3000

# When summarizing, break the document into chunks of roughly this many
# characters before the "map" step.
CHUNK_SIZE_CHARS = 8000

SUMMARIZE_CHUNK_PROMPT = """\
Summarize the following excerpt from a technical design document. Keep
every entity name, field name, relationship, endpoint, and business rule
mentioned - do not summarize those away, only trim prose, repetition, and
boilerplate (headers, footers, page numbers, disclaimers).

Excerpt:
{chunk}
"""

COMBINE_SUMMARIES_PROMPT = """\
Combine the following partial summaries of one technical design document
into a single, de-duplicated summary. Keep every distinct entity, field,
relationship, endpoint, and business rule. Remove exact duplicates that
appear because the same entity was mentioned in multiple excerpts.

Partial summaries:
{summaries}
"""


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


def chunk_text(text: str, chunk_size_chars: int = CHUNK_SIZE_CHARS) -> list[str]:
    return [text[i:i + chunk_size_chars] for i in range(0, len(text), chunk_size_chars)]


def summarize_if_needed(text: str, model: ChatGoogleGenerativeAI) -> tuple[str, dict]:
    """Returns (possibly-summarized text, stats dict for logging/demo).

    If the text is already small, returns it unchanged - summarizing a
    short document would cost more tokens than it saves.
    """
    original_tokens = estimate_tokens(text)
    if original_tokens <= SUMMARIZE_THRESHOLD_TOKENS:
        return text, {
            "summarized": False,
            "original_tokens_est": original_tokens,
            "final_tokens_est": original_tokens,
        }

    chunks = chunk_text(text)
    chunk_summaries = []
    for chunk in chunks:
        response = model.invoke(SUMMARIZE_CHUNK_PROMPT.format(chunk=chunk))
        chunk_summaries.append(response.content)

    if len(chunk_summaries) == 1:
        combined = chunk_summaries[0]
    else:
        response = model.invoke(
            COMBINE_SUMMARIES_PROMPT.format(summaries="\n\n---\n\n".join(chunk_summaries))
        )
        combined = response.content

    final_tokens = estimate_tokens(combined)
    return combined, {
        "summarized": True,
        "original_tokens_est": original_tokens,
        "final_tokens_est": final_tokens,
        "chunks": len(chunks),
        "reduction_pct": round(100 * (1 - final_tokens / original_tokens), 1),
    }


def _cache_key(namespace: str, identifier: str) -> Path:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{namespace}__{digest}.json"


def cached(namespace: str, identifier: str, ttl_seconds: int, compute_fn):
    """Disk-based cache: if a cached value exists for this identifier and
    hasn't expired, return it without calling compute_fn. Otherwise call
    compute_fn(), cache the result, and return it.

    Used for things that don't change between runs, like the Confluence
    coding standards page or the Java skill file content - no reason to
    treat those as fresh input every single run.
    """
    path = _cache_key(namespace, identifier)
    if path.exists():
        cached_entry = json.loads(path.read_text())
        if time.time() - cached_entry["cached_at"] < ttl_seconds:
            return cached_entry["value"], True  # (value, was_cache_hit)

    value = compute_fn()
    path.write_text(json.dumps({"cached_at": time.time(), "value": value}))
    return value, False
