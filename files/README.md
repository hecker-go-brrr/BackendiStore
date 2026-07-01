# Chennai Math iStore Assistant — Phase 1 Setup (Conversational MVP)

This gets you texting the bot and getting real LLM replies through SalesIQ.
Commerce/inventory is stubbed until Zoho Commerce access exists (see
`commerce.py` and the Phase 2 notes in `zobot_message_handler.deluge`).

## 1. Push this code to GitHub

Create a new repo (e.g. `istore-rkm-backend`) and push these 5 files:
`main.py`, `router.py`, `llm.py`, `commerce.py`, `requirements.txt`
(don't push `.env.example` with a real key filled in — keep secrets out of git).

## 2. Deploy on Render

1. Go to https://render.com → sign up/log in (no credit card needed for the free tier).
2. **New +** → **Web Service** → connect your GitHub repo.
3. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free (upgrade to the $7/mo tier later to avoid cold-start delays once this is customer-facing)
4. **Environment** tab → **Add Environment Variable**, add these three:
   | Key | Value |
   |---|---|
   | `LLM_BASE_URL` | `https://rkmmai-33.localcan.dev` |
   | `LLM_API_KEY` | your full key (the one you pasted, un-redacted) |
   | `LLM_MODEL` | `qwen3.6-35b-a3b-nvfp4` |

   **This is where the LLM API key goes** — never in the code itself.
5. Click **Deploy**. Once live, you'll get a URL like `https://istore-rkm-backend.onrender.com`.

## 3. Verify the LLM connection before wiring up SalesIQ

The exact JSON shape your local endpoint returns isn't confirmed yet. Test it directly:

```bash
curl -X POST https://istore-rkm-backend.onrender.com/debug/raw-llm \
  -H "Content-Type: application/json" \
  -d '{"message": "What books do you have on Vivekananda?"}'
```

This returns the **raw, unprocessed** JSON from the model. Paste that output back to
Claude — `llm.py`'s `extract_output_text()` handles a few likely shapes already, but
if the real shape doesn't match, it'll raise a clear error here (in `/debug/raw-llm`,
harmlessly) rather than break silently in the live chat.

Once that's confirmed, test the real endpoint:

```bash
curl -X POST https://istore-rkm-backend.onrender.com/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What books do you have on Vivekananda?"}'
```

You should get back `{"reply": "..."}` with an actual generated answer.

## 4. Set up the SalesIQ Zobot

1. In SalesIQ: **Settings → Bot → Zobot → Add**.
2. Name it (e.g. "iStore Assistant"), choose platform **SalesIQ Scripts**, choose your brand.
3. In the Deluge code builder, select **Message Handler** from the dropdown.
4. Paste in `zobot_message_handler.deluge`, replacing `YOUR_RENDER_URL` with your
   actual Render URL from step 2.
5. **Save** → **Publish**.
6. Open your website's chat widget (or the SalesIQ test/preview chat) and send a message.
   You should get a real LLM-generated reply within a few seconds.

## 5. Where the Zoho Commerce Connection goes (for later, once you have access)

You don't have Zoho Commerce API credentials yet, so skip this until you do. When
you're ready:

1. SalesIQ: **Settings → Developers → Plugs**.
2. Open the plug tied to your Zobot (or create one) → select **Connections** in the
   bottom-left of the screen.
3. **Create Connection** → since Zoho Commerce isn't a pre-registered default service,
   choose **Custom Service**:
   - **Service Name**: Zoho Commerce
   - **Authentication Type**: OAuth2
   - **Client ID / Client Secret**: from your Zoho API Console self-client
   - **Authorize URL**: `https://accounts.zoho.in/oauth/v2/auth` (use `.com`/`.eu`/etc.
     to match your data center)
   - **Access Token URL**: `https://accounts.zoho.in/oauth/v2/token`
   - **Scopes**: the Commerce scopes you need (e.g. `ZohoCommerce.storefront.READ`)
4. Give it a **Connection Link Name** (e.g. `zoho_commerce_conn`) — this is the string
   you'll reference in the Deluge `invokeUrl [... connection: "zoho_commerce_conn"]`
   block that's already stubbed out (commented) in `zobot_message_handler.deluge`.
5. **Create and Connect**, authorize with the Zoho Commerce account credentials.

Once that's done, tell me and I'll un-comment and wire up the product-fetch code in
the Deluge script, plus the RapidFuzz matching in `commerce.py`.

## Known constraints to keep in mind

- SalesIQ's `invokeUrl` task times out at **40 seconds**; the whole message handler
  times out at **90 seconds**. `llm.py` defaults to `reasoning_effort: "low"` to stay
  well inside that — raise it later once you've measured real latency.
- Render's free tier sleeps after 15 minutes idle and takes ~30-60s to wake on the
  next request. Fine for testing; upgrade to the $7/mo tier before this is customer-facing.
