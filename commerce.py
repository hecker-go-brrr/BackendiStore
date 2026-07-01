"""
commerce.py
-----------
Matches a visitor's message against product data that the SalesIQ Zobot
already fetched from Zoho Commerce (via the "istore" Connection, using
GET https://commerce.zoho.com/store/api/v1/products) and passed along in
the /chat request as `product_data`.

This module never calls Zoho itself — it can't; SalesIQ Connections only
work inside Deluge. It just matches and formats.

Handles two distinct query shapes with one scoring pass rather than trying
to keyword-detect intent up front (that approach broke on phrasing like
"what books do you have on Vivekananda?", which contains "do you have" but
is really a browse question, not a lookup for one specific known title):
  - Lookup ("do you have the gita?", "is X in stock"): one item scores far
    above the rest -> answer with that single item's stock/price directly.
  - Browse ("what books do you have on Vivekananda?"): several items score
    close together (or only one plausible match exists at all) -> list
    what's plausible rather than confidently picking one arbitrary "winner".
"""

from typing import Optional
import re
from rapidfuzz import process, fuzz

# WRatio (and even max(WRatio, partial_ratio)) can be fooled by filler words
# shared between a conversational query and a formal product title — e.g.
# "is the gold frame in stock?" scored 85.5 against "Bhagavad Gita: With the
# Commentary of Sri Sankaracharya" purely from words like "the"/"with"/"in",
# while the actual gold frame product scored lower. Stripping stopwords from
# both sides before scoring forces matches to hinge on real content words —
# tested against an 11-query set covering lookups, browse-style queries with
# multiple genuine candidates, and true non-matches; see the walkthrough in
# the README for the numbers this was calibrated against.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "have", "has", "had", "i", "you", "your", "we", "they", "he", "she",
    "it", "this", "that", "these", "those", "in", "on", "at", "to", "of",
    "for", "with", "and", "or", "if", "not", "no", "yes", "stock",
    "available", "availability", "price", "cost", "much", "how", "there",
    "sell", "buy", "purchase", "order", "please", "can", "could", "would",
    "will", "want", "looking", "get", "got", "any", "some",
}


def _clean(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    kept = [w for w in words if w not in _STOPWORDS]
    return " ".join(kept) if kept else text.lower()


def _combined_scorer(query: str, choice: str, processor=None, score_cutoff=None) -> float:
    q, c = _clean(query), _clean(choice)
    return max(fuzz.WRatio(q, c), fuzz.partial_ratio(q, c))


NO_MATCH_THRESHOLD = 46       # below this, nothing in the catalog is a real match
SINGLE_MATCH_THRESHOLD = 53   # at/above this + a clear gap = confident single item
SINGLE_MATCH_GAP = 13         # how far ahead of the runner-up counts as "clearly the one"
LIST_THRESHOLD = 46           # anything at/above this (but no clear winner) is worth listing
MAX_LIST_ITEMS = 3


async def handle_commerce_query(message: str, product_data: Optional[list] = None) -> str:
    if not product_data:
        return (
            "I can't check live stock or pricing just yet — that part of "
            "the store assistant isn't connected. I can still help with "
            "general questions, or a team member can follow up on product "
            "details."
        )

    names = [p.get("name", "") for p in product_data if p.get("name")]
    if not names:
        return "I don't see any products in the catalog right now — a team member can help you directly."

    matches = process.extract(message, names, scorer=_combined_scorer, limit=5)
    if not matches:
        return "I couldn't find anything matching that in our catalog — a team member can help you directly."

    top_name, top_score, top_idx = matches[0]

    if top_score < NO_MATCH_THRESHOLD:
        return "I couldn't find anything matching that in our catalog — a team member can help you directly."

    second_score = matches[1][1] if len(matches) > 1 else 0
    is_confident_single = (
        top_score >= SINGLE_MATCH_THRESHOLD and (top_score - second_score) >= SINGLE_MATCH_GAP
    )

    if is_confident_single:
        product = product_data[top_idx]
        return format_product_summary(product)

    if top_score < SINGLE_MATCH_THRESHOLD:
        return (
            f"I couldn't find an exact match for that in our catalog — "
            f"did you mean \"{top_name}\"? If not, a team member can help you look further."
        )

    # Several plausible candidates, none dominant enough to answer confidently
    # as a single item — list the top few instead of guessing which one they meant.
    listed = [product_data[idx] for _, score, idx in matches if score >= LIST_THRESHOLD][:MAX_LIST_ITEMS]
    lines = [f"- {format_product_summary(p)}" for p in listed]
    return "Here are a few things that might match what you're looking for:\n" + "\n".join(lines)


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
            price_text = f", priced between ₹{min_rate} and ₹{max_rate}"
        else:
            price_text = f", priced at ₹{min_rate}"

    return f"{name}: {stock_text}{price_text}."

