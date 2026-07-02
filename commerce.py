from typing import Optional
import os
import re
from rapidfuzz import fuzz

import llm

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "have", "has", "had", "i", "you", "your", "we", "they", "he", "she",
    "it", "this", "that", "these", "those", "in", "on", "at", "to", "of",
    "for", "with", "and", "or", "if", "not", "no", "yes", "stock",
    "available", "availability", "price", "cost", "much", "how", "there",
    "sell", "buy", "purchase", "order", "please", "can", "could", "would",
    "will", "want", "looking", "get", "got", "any", "some",
}

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

  overlap_ratio = shared / min(len(set(q_words)), len(set(n_words)))

    q_clean, n_clean = " ".join(q_words), " ".join(n_words)
    fuzzy = max(fuzz.WRatio(q_clean, n_clean), fuzz.partial_ratio(q_clean, n_clean))

    return 0.6 * (overlap_ratio * 100) + 0.4 * fuzzy


def _rank_candidates(message: str, product_data: list) -> list:
    """Returns (score, product_index, name) tuples, sorted best-first,
    for every product with a nonzero score (i.e. passed the word-overlap
    gate). Shared by the shortlist builder, the local-only fallback, and
    the debug endpoint."""
    scored = []
    for idx, product in enumerate(product_data):
        name = product.get("name", "")
        if not name:
            continue
        s = _score(message, name)
        if s > 0:
            scored.append((s, idx, name))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


NO_MATCH_THRESHOLD = 35       
SINGLE_MATCH_THRESHOLD = 55   
SINGLE_MATCH_GAP = 15         
LIST_THRESHOLD = 35           
MAX_LIST_ITEMS = 3
LLM_SHORTLIST_SIZE = 12       


def debug_match(message: str, product_data: list, top_n: int = 10) -> list:
    """Returns the top N scored candidates with raw scores, for tuning
    against real catalog data — used by /debug/commerce-match. Not used in
    the actual chat flow, which only needs the final formatted reply."""
    scored = _rank_candidates(message, product_data)
    return [
        {"name": name, "score": round(s, 1), "status": product_data[idx].get("status")}
        for s, idx, name in scored[:top_n]
    ]


COMMERCE_MATCH_SYSTEM_PROMPT = (
    "You match a customer's message to product names from a bookstore and "
    "gift shop's catalog (Chennai Math iStore, run by Ramakrishna Math). "
    "You'll be given the customer's message and a numbered shortlist of "
    "candidate product names (already narrowed down by a search step). "
    "Decide which product(s), if any, the customer is actually asking about "
    "— they may phrase it indirectly, with typos, in a different language, "
    "or ask a broad question that genuinely matches several items.\n\n"
    "Respond in EXACTLY one of these three formats, nothing else:\n"
    "1. A single number from the list, if exactly one product is clearly "
    "the best match — just the number, e.g. \"3\"\n"
    "2. Several numbers separated by commas, if multiple products are all "
    "plausible matches for a broad question — e.g. \"2,5\"\n"
    "3. The word NONE, if nothing in the list is a reasonable match for "
    "what they're asking.\n\n"
    "No explanation, no extra text — only the number(s) or NONE."
)


async def _llm_disambiguate(message: str, shortlist: list, product_data: list) -> str:
    """shortlist: (score, product_index, name) tuples, local-score order.
    Builds a numbered prompt, asks the LLM to pick by number (far more
    robust than asking it to copy a name back verbatim), and returns a
    fully formatted reply. Raises on any failure or unparseable response —
    handle_commerce_query() catches this and falls back to pure local
    scoring."""
    numbered_lines = "\n".join(f"{i + 1}. {name}" for i, (_, _, name) in enumerate(shortlist))
    prompt = f"Customer message: {message!r}\n\nCandidate products:\n{numbered_lines}"

    raw = await llm.ask_llm(prompt, system_prompt=COMMERCE_MATCH_SYSTEM_PROMPT, reasoning_effort="low")
    print(f"[commerce] LLM disambiguation raw response: {raw!r}")

    cleaned = raw.strip().upper()
    if cleaned == "NONE" or cleaned.startswith("NONE"):
        return "I couldn't find anything matching that in our catalog — a team member can help you directly."

    numbers = re.findall(r"\d+", cleaned)
    if not numbers:
        raise ValueError(f"Unparseable disambiguation response: {raw!r}")

    valid_indices = [int(n) - 1 for n in numbers if 0 <= int(n) - 1 < len(shortlist)]
    if not valid_indices:
        raise ValueError(f"Disambiguation response referenced no valid list items: {raw!r}")

    if len(valid_indices) == 1:
        _, product_idx, _ = shortlist[valid_indices[0]]
        return format_product_summary(product_data[product_idx])

    listed = [product_data[shortlist[i][1]] for i in valid_indices[:MAX_LIST_ITEMS]]
    lines = [f"- {format_product_summary(p)}" for p in listed]
    return "Here are a few things that might match what you're looking for:\n" + "\n".join(lines)


def _local_decision(scored: list, product_data: list) -> str:
    """The previous pure-local decision logic, kept as an automatic
    fallback for when LLM disambiguation fails."""
    top_matches = scored[:5]
    top_score, top_idx, top_name = top_matches[0]

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

    listed = [product_data[idx] for score, idx, name in top_matches if score >= LIST_THRESHOLD][:MAX_LIST_ITEMS]
    lines = [f"- {format_product_summary(p)}" for p in listed]
    return "Here are a few things that might match what you're looking for:\n" + "\n".join(lines)


async def handle_commerce_query(message: str, product_data: Optional[list] = None) -> str:
    if not product_data:
        return (
            "I can't check live stock or pricing just yet — that part of "
            "the store assistant isn't connected. I can still help with "
            "general questions, or a team member can follow up on product "
            "details."
        )

    scored = _rank_candidates(message, product_data)

    # Cheap rejection BEFORE calling the LLM at all — true non-matches
    # ("harry potter" against a Vedanta catalog) never pass the word-overlap
    # gate, so there's no reason to spend an LLM call confirming that.
    if not scored or scored[0][0] < NO_MATCH_THRESHOLD:
        return "I couldn't find anything matching that in our catalog — a team member can help you directly."

    shortlist = scored[:LLM_SHORTLIST_SIZE]

    try:
        return await _llm_disambiguate(message, shortlist, product_data)
    except Exception as exc:  # noqa: BLE001 — any LLM failure falls back to pure local scoring
        print(f"[commerce] LLM disambiguation failed, falling back to local scoring: {exc!r}")
        return _local_decision(scored, product_data)


STOREFRONT_BASE_URL = os.environ.get("STOREFRONT_BASE_URL", "").rstrip("/")


def _format_price(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(v)) if v == int(v) else f"{v:g}"


def _product_link(product: dict) -> str:
    """Builds the real storefront product page URL from the product's
    'url' (a slug, not a full link) and 'product_id'. Returns "" if
    STOREFRONT_BASE_URL isn't configured or either field is missing —
    never guesses at a link that might be wrong."""
    if not STOREFRONT_BASE_URL:
        return ""
    slug = product.get("url")
    product_id = product.get("product_id")
    if not slug or not product_id:
        return ""
    return f"{STOREFRONT_BASE_URL}/products/{slug}/{product_id}"


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

    link = _product_link(product)
    link_text = f" {link}" if link else ""

    return f"{name}: {stock_text}{price_text}.{link_text}"

