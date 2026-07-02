"""
store_info.py
--------------
Factual information about Chennai Math iStore that the LLM treats as ground
truth for general questions. Edit this file whenever details change —
nothing else needs to change, no code logic depends on the exact wording.

NOTE: This is for general informational questions only. Product
availability/stock/pricing still comes from the live Zoho Commerce fetch via
commerce.py — never hardcode product data here, it goes stale immediately.

Two items are still marked TODO (returns/exchange policy, payment methods)
because they haven't been provided yet — the system prompt in llm.py
explicitly instructs the bot not to guess on anything marked TODO, so these
will correctly route to "let me connect you with the team" until filled in.
"""

STORE_INFO = """
Store name: Chennai Math iStore
Run by: Sri Ramakrishna Math, Chennai

IMPORTANT — two separate things people may ask about, don't confuse them:
1. The iStore (online store): open 24/7. Customers can browse and place
   orders at any time, day or night.
2. The physical temple (Sri Ramakrishna Math, Chennai) has separate Darshan
   hours, listed below. These apply to visiting the temple in person — they
   have nothing to do with the iStore's availability.

Darshan hours (physical temple, Indian Standard Time):
  05:00 AM         Shrine opens, Mangalarati
  06:40-07:00 AM   Vedic & Gita chanting
  07:30-09:00 AM   Puja
  11:00-11:30 AM   Food offering to Sri Ramakrishna (shrine remains closed)
  11:45 AM         Temple closes for midday
  03:00 PM         Temple reopens
  03:30 PM         Shrine opens
  06:30-07:15 PM   Aratrikam & Bhajan
  08:30-08:50 PM   Food offering to Sri Ramakrishna (shrine remains closed)
  09:00 PM         Temple closes for the day

Contact:
  Email: support@chennaimath.org
  Phone: +91 94983 04690

Shipping: Yes, the iStore ships orders. For specific shipping questions
(cost, delivery time, tracking, international shipping, etc.), don't guess —
tell the customer you'll connect them with a team member who can help with
shipping details directly (point them to the email/phone above).

Location (physical temple / Math): Sri Ramakrishna Math, Chennai.
Map: https://www.google.com/maps/place/Sri+Ramakrishna+Math+Chennai/@13.0310729,80.2649328,17z

More information about the Math and the Universal Temple:
  https://chennaimath.org/universal-temple

Official social media / channels:
  WhatsApp: https://www.whatsapp.com/channel/0029VaASoL67DAWs9Ldvxq2h
  Facebook: https://www.facebook.com/ramakrishnamath
  X (Twitter): https://x.com/ramakrishnamath
  Instagram: https://www.instagram.com/ramakrishnamath
  YouTube: https://www.youtube.com/user/chennaimath
  Flickr: https://www.flickr.com/photos/ramakrishnamath/

Returns/exchange policy: TODO — not yet provided. Don't guess; direct the
  customer to support@chennaimath.org or +91 94983 04690.
Payment methods accepted: TODO — not yet provided. Don't guess; direct the
  customer to support@chennaimath.org or +91 94983 04690.
"""
