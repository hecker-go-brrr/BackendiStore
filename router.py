"""
router.py
---------
Simple keyword-based routing for the POC. Replace with an intent
classifier once the architecture is validated end to end.

NOTE: "book" and "author" were removed as triggers — in a bookstore chatbot,
those words appear in nearly every general question ("what books do you have
on Vivekananda?"), causing constant false-positive routing to the commerce
path. What's left are words that specifically signal checking a KNOWN item's
stock/price/availability, not just topical mentions of books in general.

NOTE: "order", "delivery", and "shipping" were also removed. These are
general store-POLICY questions ("can I order right now?", "do you ship
internationally?") — store_info.py now has real answers for shipping, but
only via the general LLM path. commerce.py can only match a message against
product NAMES; a shipping question doesn't resemble any product name, so it
would always fail there regardless of whether real product data is attached
("Can I order from the iStore right now, it's 11 PM?" was misrouted to
commerce and hit the "not connected" fallback because of "order" — a real
bug caught in testing, not a hypothetical).
"""

COMMERCE_KEYWORDS = [
    "do you have", "is there", "availability", "available",
    "in stock", "out of stock", "stock",
    "price", "cost", "how much",
    "purchase", "buy", "isbn",
]


def classify(message: str) -> str:
    lowered = message.lower()
    if any(keyword in lowered for keyword in COMMERCE_KEYWORDS):
        return "commerce"
    return "general"
