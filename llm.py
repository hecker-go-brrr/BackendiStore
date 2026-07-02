"""
llm.py
------
Two interchangeable LLM providers, switched via the LLM_PROVIDER env var
(set on Render — no code change needed to switch):

  LLM_PROVIDER=local  (default) -> the tunneled local Qwen model
                                    (https://rkmmai-33.localcan.dev/v1/responses)
  LLM_PROVIDER=azure           -> Azure OpenAI's Responses API
                                    (https://admin-mnowkbwk-southindia.cognitiveservices.azure.com/openai/responses)

Both providers speak a Responses-API-style shape (input in, output[] with
output_text back), so extract_output_text() is shared between them. Azure's
exact response shape for this specific deployment hasn't been confirmed yet
(unlike the local one, which was confirmed via /debug/raw-llm earlier in this
project) — extract_output_text() also now handles the Chat Completions shape
(choices[].message.content) as a fallback, in case this Azure deployment
actually responds that way instead. Test with /debug/raw-llm before trusting
it in production, the same way the local provider was verified.

IMPORTANT auth difference: Azure uses an `api-key` header, NOT
`Authorization: Bearer` like the local provider. Getting this wrong produces
a 401, not a helpful error — this is coded correctly below, but worth knowing
if you ever touch this by hand.
"""

import os
import httpx

from store_info import STORE_INFO

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "local").lower()  # "local" or "azure"

DEFAULT_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "low")

SYSTEM_PROMPT = (
    "You are the store assistant for the Chennai Math iStore, a bookstore "
    "and gift store run by Ramakrishna Math. Answer customer questions "
    "warmly, clearly, and concisely, in a tone suitable for all ages.\n\n"
    "Here is verified information about the store — treat this as ground "
    "truth and answer directly from it when relevant:\n"
    f"{STORE_INFO}\n\n"
    "If something is asked that ISN'T covered in the information above "
    "(or is marked TODO/unfilled), say plainly that you'll check with the "
    "store team rather than guessing. Never invent hours, prices, addresses, "
    "or policies that aren't stated above.\n\n"
    "If asked about specific product availability, pricing, or stock, say "
    "plainly that you're checking with the store team rather than guessing "
    "a number — that information comes from a separate, live inventory "
    "check, not from you directly."
)

# ---- Local (tunneled Qwen) provider config ----
LOCAL_BASE_URL = os.environ.get("LLM_BASE_URL", "https://rkmmai-33.localcan.dev").rstrip("/")
LOCAL_API_KEY = os.environ.get("LLM_API_KEY")
LOCAL_MODEL = os.environ.get("LLM_MODEL", "qwen3.6-35b-a3b-nvfp4")

# ---- Azure OpenAI provider config ----
AZURE_ENDPOINT = os.environ.get(
    "AZURE_LLM_ENDPOINT", "https://admin-mnowkbwk-southindia.cognitiveservices.azure.com"
).rstrip("/")
AZURE_API_KEY = os.environ.get("AZURE_LLM_API_KEY")
AZURE_DEPLOYMENT = os.environ.get("AZURE_LLM_DEPLOYMENT", "gpt-5.4-nano-for-salesiq")
AZURE_API_VERSION = os.environ.get("AZURE_LLM_API_VERSION", "2025-04-01-preview")


async def ask_llm(
    user_message: str,
    system_prompt: str = SYSTEM_PROMPT,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    provider: str = None,
) -> str:
    data = await _call_provider(user_message, system_prompt, reasoning_effort, provider)
    return extract_output_text(data)


async def ask_llm_raw(user_message: str, reasoning_effort: str = "low", provider: str = None) -> dict:
    """Used by /debug/raw-llm so you can see the exact JSON shape a provider
    returns, unprocessed — pass provider="azure" or provider="local" to test
    either one regardless of which is set as the active LLM_PROVIDER."""
    return await _call_provider(user_message, SYSTEM_PROMPT, reasoning_effort, provider)


async def _call_provider(user_message: str, system_prompt: str, reasoning_effort: str, provider: str = None) -> dict:
    active = (provider or LLM_PROVIDER).lower()
    if active == "azure":
        return await _call_azure(user_message, system_prompt)
    if active == "local":
        return await _call_local(user_message, system_prompt, reasoning_effort)
    raise ValueError(f"Unknown LLM provider {active!r} — expected 'local' or 'azure'.")


async def _call_local(user_message: str, system_prompt: str, reasoning_effort: str) -> dict:
    if not LOCAL_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set — required for the 'local' provider.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LOCAL_API_KEY}",
    }
    payload = {
        "model": LOCAL_MODEL,
        "system_prompt": system_prompt,
        "input": user_message,
        "reasoning": {"effort": reasoning_effort},
    }

    async with httpx.AsyncClient(timeout=35) as client:
        resp = await client.post(f"{LOCAL_BASE_URL}/v1/responses", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


async def _call_azure(user_message: str, system_prompt: str) -> dict:
    if not AZURE_API_KEY:
        raise RuntimeError("AZURE_LLM_API_KEY is not set — required for the 'azure' provider.")

    # Azure uses an `api-key` header, not `Authorization: Bearer` — different
    # from the local provider. Easy to get wrong, coded explicitly here.
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_API_KEY,
    }
    payload = {
        "model": AZURE_DEPLOYMENT,
        "input": user_message,
        "instructions": system_prompt,
    }
    url = f"{AZURE_ENDPOINT}/openai/responses?api-version={AZURE_API_VERSION}"

    async with httpx.AsyncClient(timeout=35) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


def extract_output_text(data: dict) -> str:
    """Best-effort parsing across plausible response shapes from either
    provider.

    Confirmed working (tested earlier in this project):
      - Local provider: {"output": [{"type": "reasoning", ...}, {"type": "message", "content": [{"type": "output_text", "text": "..."}]}]}

    Handled defensively, not yet confirmed against a real response:
      - {"output_text": "..."}                     (OpenAI Responses API convenience field)
      - {"choices": [{"message": {"content": "..."}}]}   (Chat Completions shape —
        in case the Azure deployment responds this way instead of Responses-API style)
      - {"response": "..."} / {"text": "..."}

    If none match, raises with the raw payload so the error is debuggable
    instead of silently returning garbage — test with /debug/raw-llm first.
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

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        if isinstance(message.get("content"), str):
            return message["content"].strip()

    if isinstance(data.get("response"), str):
        return data["response"].strip()

    if isinstance(data.get("text"), str):
        return data["text"].strip()

    raise ValueError(f"Unrecognized response shape from LLM: {data}")
