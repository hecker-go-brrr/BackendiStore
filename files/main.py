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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

import router
import llm
import commerce

app = FastAPI(title="Chennai Math iStore Assistant")


class ChatRequest(BaseModel):
    message: str
    visitor_id: Optional[str] = None
    product_data: Optional[list] = None  # populated by Deluge in Phase 2


class DebugRequest(BaseModel):
    message: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(payload: ChatRequest):
    if not payload.message or not payload.message.strip():
        return {"reply": "Could you tell me a bit more about what you're looking for?"}

    intent = router.classify(payload.message)

    try:
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


@app.post("/debug/raw-llm")
async def debug_raw_llm(payload: DebugRequest):
    """Hit this once via curl/Postman/browser after deploying, to see the
    exact JSON the local LLM returns, before trusting llm.py's parsing."""
    try:
        raw = await llm.ask_llm_raw(payload.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return raw
