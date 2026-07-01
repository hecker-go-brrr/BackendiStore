"""
commerce.py
-----------
PHASE 2 — NOT YET WIRED UP.

We don't have Zoho Commerce API credentials yet, and SalesIQ Connections
can only be invoked from Deluge running inside SalesIQ (not from this
external Python service). So the real flow, once access exists, is:

  1. The SalesIQ Zobot Message Handler (Deluge) calls Zoho Commerce
     directly via `invokeUrl [... connection: "zoho_commerce_conn"]`.
  2. The Zobot POSTs the visitor's message *and* that product data to
     this backend's /chat endpoint.
  3. handle_commerce_query() below runs RapidFuzz matching against the
     product data it was handed (instead of fetching anything itself).
  4. The matched product info is handed to llm.py to phrase naturally.

For now, this returns an honest "not connected yet" message so the bot
never crashes or hallucinates stock/pricing it doesn't have.
"""

from typing import Optional


async def handle_commerce_query(message: str, product_data: Optional[list] = None) -> str:
    if not product_data:
        return (
            "I can't check live stock or pricing just yet — that part of "
            "the store assistant isn't connected. I can still help with "
            "general questions, or a team member can follow up on product "
            "details."
        )

    # --- Phase 2 implementation (once product_data is being passed in) ---
    # from rapidfuzz import process, fuzz
    # names = [p["name"] for p in product_data]
    # match, score, idx = process.extractOne(message, names, scorer=fuzz.WRatio)
    # if score >= 90:
    #     product = product_data[idx]
    #     return format_product_for_llm(product)
    # return "I couldn't find a close match for that item in the catalog."

    return "Product lookup is connected but not yet implemented — coming in Phase 2."
