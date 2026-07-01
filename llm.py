"""
llm.py
------
Talks to the locally-hosted Qwen model via its tunneled endpoint
(e.g. https://rkmmai-33.localcan.dev/v1/responses).

This is a *custom* Responses-API-style endpoint, not the stock
OpenAI /v1/chat/completions shape. We don't yet know the exact JSON
shape of a successful response, so extract_output_text() tries a few
common shapes defensively and raises a clear error if none match.

Once you test /debug/raw-llm (see main.py) and see the real JSON,
tell Claude the shape and this function gets locked down precisely.
"""

import os
import httpx

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://rkmmai-33.localcan.dev").rstrip("/")
LLM_API_KEY = os.environ["LLM_API_KEY"]  # set this in Render's environment variables, never hardcode
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.6-35b-a3b-nvfp4")

# Keep reasoning effort modest by default — SalesIQ's invokeUrl task has a
# hard 40-second timeout per call, and the whole message handler has a
# 90-second budget. "high" effort risks timing out inside SalesIQ.
DEFAULT_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "low")

SYSTEM_PROMPT = (
    "You are the store assistant for the Chennai Math iStore, a bookstore "
    "and gift store run by Ramakrishna Math. Answer customer questions "
    "warmly, clearly, and concisely, in a tone suitable for all ages. "
    "If asked about specific product availability, pricing, or stock, say "
    "plainly that you're checking with the store team rather than guessing "
    "a number."
)


async def ask_llm(
    user_message: str,
    system_prompt: str = SYSTEM_PROMPT,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }
    payload = {
        "model": LLM_MODEL,
        "system_prompt": system_prompt,
        "input": user_message,
        "reasoning": {"effort": reasoning_effort},
    }

    async with httpx.AsyncClient(timeout=35) as client:
        resp = await client.post(f"{LLM_BASE_URL}/v1/responses", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    return extract_output_text(data)


async def ask_llm_raw(user_message: str, reasoning_effort: str = "low") -> dict:
    """Used only by the /debug/raw-llm endpoint so you can see the exact
    JSON shape the model returns, unprocessed."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }
    payload = {
        "model": LLM_MODEL,
        "system_prompt": SYSTEM_PROMPT,
        "input": user_message,
        "reasoning": {"effort": reasoning_effort},
    }
    async with httpx.AsyncClient(timeout=35) as client:
        resp = await client.post(f"{LLM_BASE_URL}/v1/responses", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


def extract_output_text(data: dict) -> str:
    """Best-effort parsing across a few plausible Responses-API shapes.

    Known shapes this handles:
      1. {"output_text": "..."}                                   (OpenAI Responses API convenience field)
      2. {"output": [{"content": [{"type": "output_text"/"text", "text": "..."}]}]}
      3. {"response": "..."}
      4. {"text": "..."}

    If none match, raises with the raw payload so the error is debuggable
    instead of silently returning garbage.
    """
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()

    output = data.get("output")
    if isinstance(output, list):
        chunks = []
        for item in output:
            for content in item.get("content", []):
                if content.get("type") in ("output_text", "text") and content.get("text"):
                    chunks.append(content["text"])
        if chunks:
            return "\n".join(chunks).strip()

    if isinstance(data.get("response"), str):
        return data["response"].strip()

    if isinstance(data.get("text"), str):
        return data["text"].strip()

    raise ValueError(f"Unrecognized response shape from LLM: {data}")
