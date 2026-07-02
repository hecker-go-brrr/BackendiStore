"""
router.py
---------
LLM-based intent classification, with the original keyword heuristic kept
as an automatic fallback.

WHY BOTH: this project has hit multiple LLM-provider outages already (the
tunnel going down, a wrong domain, a stale deploy). If routing depended
entirely on one LLM call with no fallback, a provider outage would silently
break BOTH the general chat path AND the commerce path at once — worse than
the keyword-only version this replaces. So classify() tries the LLM first;
if that call fails or returns something unparseable for any reason, it
falls straight back to the keyword check rather than crashing or guessing.

This does mean general questions now involve two sequential LLM calls
(classify, then answer) instead of one — worth watching in practice. If
latency becomes a problem, the two calls could be merged later, but that
adds complexity (the answer call needs real product data for commerce
queries, which isn't available at classification time) — shipping the
simple, correct version first.
"""

import llm

# Kept as the fallback path — see classify_keywords() below.
COMMERCE_KEYWORDS = [
    "do you have", "is there", "availability", "available",
    "in stock", "out of stock", "stock",
    "price", "cost", "how much",
    "purchase", "buy", "isbn",
]

CLASSIFIER_SYSTEM_PROMPT = (
    "You classify customer chat messages for a bookstore and gift shop's "
    "assistant. Respond with EXACTLY one word, nothing else:\n\n"
    "- 'commerce' if the message is asking whether a SPECIFIC product is "
    "available, in stock, its price, or wants to buy/order a particular "
    "named item (e.g. \"do you have the gita?\", \"is the gold frame in "
    "stock?\", \"how much is X\").\n"
    "- 'general' for everything else — greetings, store hours, policies, "
    "shipping questions, browsing by topic without a specific item in mind, "
    "or any other conversational question.\n\n"
    "Respond with only the single word 'commerce' or 'general'. No "
    "punctuation, no explanation, nothing else."
)


def classify_keywords(message: str) -> str:
    """The original keyword heuristic. Used as an automatic fallback if the
    LLM classifier call fails or returns something unparseable — never used
    as the primary path anymore, but kept because it's fast, free, and
    doesn't depend on any external service being up."""
    lowered = message.lower()
    if any(keyword in lowered for keyword in COMMERCE_KEYWORDS):
        return "commerce"
    return "general"


async def classify(message: str) -> str:
    try:
        raw = await llm.ask_llm(
            message,
            system_prompt=CLASSIFIER_SYSTEM_PROMPT,
            reasoning_effort="low",
        )
    except Exception as exc:  # noqa: BLE001 — any provider failure falls back, never breaks routing
        print(f"[router] LLM classification failed, falling back to keywords: {exc!r}")
        return classify_keywords(message)

    cleaned = raw.strip().lower()

    if cleaned.startswith("commerce") or (
        "commerce" in cleaned and "general" not in cleaned
    ):
        return "commerce"
    if cleaned.startswith("general") or (
        "general" in cleaned and "commerce" not in cleaned
    ):
        return "general"

    # Response didn't clearly say either word — don't guess, fall back.
    print(f"[router] LLM classification returned unexpected output {raw!r}, falling back to keywords")
    return classify_keywords(message)
