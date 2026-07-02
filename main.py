"""
main.py
-------
FastAPI backend for the Chennai Math iStore assistant.

Endpoints:
  POST /chat            <- called by the SalesIQ Zobot Message Handler
  GET  /health           <- for Render's health checks
  POST /debug/raw-llm    <- returns the LLM's raw, unprocessed JSON so you
                             can confirm its response shape before relying
                             on llm.py's parsing. Remove or protect this
                             before going fully live.
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional
import os

import router
import llm
import commerce

app = FastAPI(title="Chennai Math iStore Assistant")

# Shared-secret check: your Zobot sends this header on every call, so random
# internet traffic hitting your public Render URL can't rack up LLM/Commerce
# API usage. Set BACKEND_SHARED_SECRET in Render's environment variables,
# generate a long random string for it, and send the same value as the
# X-Backend-Secret header from the Deluge script.
BACKEND_SHARED_SECRET = os.environ.get("BACKEND_SHARED_SECRET")


def verify_secret(x_backend_secret: Optional[str] = Header(default=None)):
    if BACKEND_SHARED_SECRET and x_backend_secret != BACKEND_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Backend-Secret header")


class ChatRequest(BaseModel):
    message: str
    visitor_id: Optional[str] = None
    product_data: Optional[list] = None  # populated by Deluge in Phase 2


class DebugRequest(BaseModel):
    message: str
    provider: Optional[str] = None  # "local" or "azure" — overrides LLM_PROVIDER for this one call


class DebugCommerceRequest(BaseModel):
    message: str
    product_data: list


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", dependencies=[Depends(verify_secret)])
async def chat(payload: ChatRequest):
    if not payload.message or not payload.message.strip():
        return {"reply": "Could you tell me a bit more about what you're looking for?"}

    try:
        intent = await router.classify(payload.message)
        if intent == "commerce":
            reply = await commerce.handle_commerce_query(payload.message, payload.product_data)
        else:
            reply = await llm.ask_llm(payload.message)
    except Exception as exc:  # noqa: BLE001 — deliberately broad: SalesIQ needs *some* reply, always
        # Log this properly once you have real logging/observability wired up.
        print(f"[chat] error handling message={payload.message!r}: {exc!r}")
        reply = (
            "Sorry, I'm having trouble reaching my brain right now — "
            "a team member will be with you shortly."
        )

    return {"reply": reply}


@app.post("/debug/raw-llm", dependencies=[Depends(verify_secret)])
async def debug_raw_llm(payload: DebugRequest):
    """Hit this after deploying to see the exact JSON a provider returns,
    before trusting llm.py's parsing. Pass {"provider": "azure"} or
    {"provider": "local"} to test either one regardless of which is
    currently set as LLM_PROVIDER on Render."""
    active_provider = (payload.provider or llm.LLM_PROVIDER).lower()
    try:
        raw = await llm.ask_llm_raw(payload.message, provider=payload.provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"[{active_provider}] {exc}") from exc
    return {"provider_used": active_provider, "raw_response": raw}


@app.post("/debug/commerce-match", dependencies=[Depends(verify_secret)])
async def debug_commerce_match(payload: DebugCommerceRequest):
    """Test product matching against REAL catalog data without going
    through /chat's final formatted reply. Pass a real message plus the
    actual product_data your Zobot fetches (e.g. paste in the trimmed
    products from a Deluge log or a fresh Commerce fetch). Returns the top
    10 scored candidates with raw scores, so mismatches can be diagnosed
    precisely instead of guessing at what the fuzzy matcher is doing."""
    ranked = commerce.debug_match(payload.message, payload.product_data)
    return {"query": payload.message, "top_matches": ranked}
