"""
commerce.py
-----------
Matches a visitor's message against product data that the SalesIQ Zobot
already fetched from Zoho Commerce (via the "istore" Connection, using
GET https://commerce.zoho.com/store/api/v1/products) and passed along in
the /chat request as `product_data`.

This module never calls Zoho itself — it can't; SalesIQ Connections only
work inside Deluge. It just matches and formats.

MATCHING APPROACH — word-overlap gate, then fuzzy scoring within that gate.
Character-level fuzzy ratios alone (WRatio/partial_ratio) were tested and
found unreliable at real catalog scale (~1000 products): two genuinely
UNRELATED strings can score deceptively high just from incidental character
overlap ("is the gold frame in stock?" once scored 85 against a Bhagavad
Gita title purely from shared filler words). At small scale that's a rare
fluke; at 1000 candidates, some accidental high-scoring collision becomes
common rather than rare — this was reported as "random options for items
definitely not in the catalog," and is a structural weakness of pure
character-ratio scoring, not a threshold-tuning problem.

Fix: before trusting ANY fuzzy score, require genuine shared words (exact,
or near-exact for minor typos) between the query and the product name. No
shared real word = zero score, full stop, regardless of how similar the
raw characters look. This also improves matching short casual queries
("gita") against long formal titles ("Bhagavad Gita: With the Commentary
of Sri Sankaracharya") — word overlap is normalized by the SHORTER side,
so a short query matching a subset of a long title's words still scores
well, rather than being diluted by the title's extra length the way a
whole-string ratio would be.

Handles two distinct query shapes:
  - Lookup ("do you have the gita?", "is X in stock"): one item scores far
    above the rest -> answer with that single item's stock/price directly.
  - Browse ("what books do you have on Vivekananda?"): several items score
    close together -> list what's plausible rather than confidently picking
    one arbitrary "winner".
"""

from typing import Optional
import re
from rapidfuzz import fuzz

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "have", "has", "had", "i", "you", "your", "we", "they", "he", "she",
    "it", "this", "that", "these", "those", "in", "on", "at", "to", "of",
    "for", "with", "and", "or", "if", "not", "no", "yes", "stock",
    "available", "availability", "price", "cost", "much", "how", "there",
    "sell", "buy", "purchase", "order", "please", "can", "could", "would",
    "will", "want", "looking", "get", "got", "any", "some",
}

# Two words count as "the same" if they're identical, OR near-identical
# (catches minor typos/spelling variants like "vivekanand" vs "vivekananda")
_WORD_TYPO_THRESHOLD = 82


def _tokenize(text: str) -> list:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) >= 2]


def _shared_word_count(query_words: list, name_words: list) -> int:
    """How many query words have a real match (exact or near-exact) among
    the product name's words. This is the hard gate — zero shared words
    means zero score, regardless of character-level similarity."""
    name_set = list(dict.fromkeys(name_words))  # dedupe, preserve order
    shared = 0
    for qw in set(query_words):
        if qw in name_set:
            shared += 1
            continue
        for nw in name_set:
            if fuzz.ratio(qw, nw) >= _WORD_TYPO_THRESHOLD:
                shared += 1
                break
    return shared


def _score(query: str, name: str) -> float:
    q_words = _tokenize(query)
    n_words = _tokenize(name)

    if not q_words or not n_words:
        return 0.0

    shared = _shared_word_count(q_words, n_words)
    if shared == 0:
        return 0.0  # hard gate — no real shared content, no match, period

    # Overlap ratio normalized by the SHORTER side so a short query ("gita")
    # matching a subset of a long formal title still scores well.
    overlap_ratio = shared / min(len(set(q_words)), len(set(n_words)))

    # Fuzzy score within the already-filtered candidates, to distinguish a
    # near-exact match from a loose one that only shares one common word.
    q_clean, n_clean = " ".join(q_words), " ".join(n_words)
    fuzzy = max(fuzz.WRatio(q_clean, n_clean), fuzz.partial_ratio(q_clean, n_clean))

    return 0.6 * (overlap_ratio * 100) + 0.4 * fuzzy


NO_MATCH_THRESHOLD = 35       # below this, nothing in the catalog is a real match
SINGLE_MATCH_THRESHOLD = 55   # at/above this + a clear gap = confident single item
SINGLE_MATCH_GAP = 15         # how far ahead of the runner-up counts as "clearly the one"
LIST_THRESHOLD = 35           # anything at/above this (but no clear winner) is worth listing
MAX_LIST_ITEMS = 3


def debug_match(message: str, product_data: list, top_n: int = 10) -> list:
    """Returns the top N scored candidates with raw scores, for tuning
    against real catalog data — used by /debug/commerce-match. Not used in
    the actual chat flow, which only needs the final formatted reply."""
    scored = []
    for idx, product in enumerate(product_data):
        name = product.get("name", "")
        if not name:
            continue
        s = _score(message, name)
        scored.append({"name": name, "score": round(s, 1), "status": product.get("status")})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


async def handle_commerce_query(message: str, product_data: Optional[list] = None) -> str:
    if not product_data:
        return (
            "I can't check live stock or pricing just yet — that part of "
            "the store assistant isn't connected. I can still help with "
            "general questions, or a team member can follow up on product "
            "details."
        )

    scored = []
    for idx, product in enumerate(product_data):
        name = product.get("name", "")
        if not name:
            continue
        s = _score(message, name)
        if s > 0:
            scored.append((s, idx, name))

    if not scored:
        return "I couldn't find anything matching that in our catalog — a team member can help you directly."

    scored.sort(key=lambda x: x[0], reverse=True)
    top_matches = scored[:5]

    top_score, top_idx, top_name = top_matches[0]

    if top_score < NO_MATCH_THRESHOLD:
        return "I couldn't find anything matching that in our catalog — a team member can help you directly."

    second_score = top_matches[1][0] if len(top_matches) > 1 else 0
    is_confident_single = (
        top_score >= SINGLE_MATCH_THRESHOLD and (top_score - second_score) >= SINGLE_MATCH_GAP
    )

    if is_confident_single:
        return format_product_summary(product_data[top_idx])

    if top_score < SINGLE_MATCH_THRESHOLD:
        return (
            f"I couldn't find an exact match for that in our catalog — "
            f"did you mean \"{top_name}\"? If not, a team member can help you look further."
        )

    # Several plausible candidates, none dominant enough to answer confidently
    # as a single item — list the top few instead of guessing which one they meant.
    listed = [product_data[idx] for score, idx, name in top_matches if score >= LIST_THRESHOLD][:MAX_LIST_ITEMS]
    lines = [f"- {format_product_summary(p)}" for p in listed]
    return "Here are a few things that might match what you're looking for:\n" + "\n".join(lines)


def _format_price(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(v)) if v == int(v) else f"{v:g}"


def format_product_summary(product: dict) -> str:
    name = product.get("name", "This item")
    stock = product.get("overall_stock")
    min_rate = product.get("min_rate")
    max_rate = product.get("max_rate")
    status = product.get("status")

    if status and status != "active":
        return f"{name} isn't currently available in the store."

    if stock is None:
        stock_text = "I don't have current stock information for it"
    else:
        try:
            stock_num = float(stock)
        except (TypeError, ValueError):
            stock_num = 0
        stock_text = f"{int(stock_num)} in stock" if stock_num > 0 else "currently out of stock"

    price_text = ""
    if min_rate not in (None, "", 0):
        if max_rate not in (None, "", 0) and max_rate != min_rate:
            price_text = f", priced between ₹{_format_price(min_rate)} and ₹{_format_price(max_rate)}"
        else:
            price_text = f", priced at ₹{_format_price(min_rate)}"

    return f"{name}: {stock_text}{price_text}."

