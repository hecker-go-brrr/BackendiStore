"""
router.py
---------
Simple keyword-based routing for the POC. Replace with an intent
classifier once the architecture is validated end to end.
"""

COMMERCE_KEYWORDS = [
    "availability", "available", "stock", "in stock", "price", "cost",
    "how much", "book", "author", "purchase", "buy", "product", "isbn",
    "order", "delivery", "shipping", "catalog",
]


def classify(message: str) -> str:
    lowered = message.lower()
    if any(keyword in lowered for keyword in COMMERCE_KEYWORDS):
        return "commerce"
    return "general"
