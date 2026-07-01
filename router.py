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
"""

COMMERCE_KEYWORDS = [
    "do you have", "is there", "availability", "available",
    "in stock", "out of stock", "stock",
    "price", "cost", "how much",
    "purchase", "buy", "isbn", "order", "delivery", "shipping",
]


def classify(message: str) -> str:
    lowered = message.lower()
    if any(keyword in lowered for keyword in COMMERCE_KEYWORDS):
        return "commerce"
    return "general"
