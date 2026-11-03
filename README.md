# UWACA MCP — one-use Render Free demo

This folder is an independent deployment artifact: **only these three files**:
`server.py`, `requirements.txt`, `README.md`. It imports no UWACA code. It offers
exactly one tool, `uwaca_status`, with empty arguments and read-only annotations.
Its fixed JSON TextContent is:

```json
{"project":"UWACA_DEMO","poc_version":"demo_only","status":"simulated","read_only":true,"connected_to_local_uwaca":false}
```

No source reader, shell, journal, resources, prompts, OAuth, database, user data,
credentials, laptop connection, or filesystem-serving route exists. This does not
deploy the UWACA Coding Agent. Local Core/Bridge/PoCs are untouched.

## Local check before any upload

From the UWACA workspace, reuse the already isolated MCP SDK venv:

```powershell
.\mcp_status\.venv\Scripts\python.exe -B -X utf8 render_status_demo/server.py --self-test
```

This starts real HTTP only on 127.0.0.1, uses the official MCP client with a fake
Render Host header, then stops the server. It tests handshake 2025-11-25, discovery,
JSON TextContent, invalid arguments/tools/JSON, allowed and rejected origins/hosts,
body/call/request limits, expiry and fail-closed configuration. No hosting or
Google access occurs. Without --self-test, startup requires explicit Render
environment configuration; it does not publish anything by itself.

For a clean copy elsewhere, install `requirements.txt` in a fresh venv. The demo
does not require the UWACA workspace or its existing venv after packaging.

## Manual Render setup — do not deploy until explicitly ready

1. Create a **new empty temporary repository**, with no Git history copied from
   UWACA. Upload only the three allowlisted files from this folder at its root.
   Inspect the complete file list first. Never upload the workspace, parent
   directories, .git, .venv, .env, SQLite, logs, argon-response.json or personal files.
   Do not point Render at the UWACA repository or use a workspace Docker build context.
2. In Render choose **New > Web Service > Public Git Repository**, enter the URL
   of that isolated public demo. This route does not give Render Git-provider
   credentials or access to UWACA. The code is intentionally public and dummy-only.
   If the UI insists on broad repository access, stop; do not authorize it.
3. Select **Free instance only**. Do not add a card, payment method, paid workspace,
   disk, database or other service. If Free is unavailable or payment is required,
   stop. The application cannot enforce Render billing choices for you.
4. Set these values:

   | Setting | Value |
   | --- | --- |
   | Runtime | Python 3 |
   | Build command | `pip install -r requirements.txt` |
   | Start command | `python -B server.py` |
   | Instance | Free, one instance |
   | Python environment variable | `PYTHON_VERSION=3.13.17` |
   | Port environment variable | `PORT=10000` |
   | Required environment variable | `EXPIRES_AT`: fixed UTC timestamp generated below |
   | Health check | Default TCP; do not configure an HTTP health path |

   Set PORT explicitly as above; Render supplies `RENDER=true` and `RENDER_EXTERNAL_HOSTNAME`. The app
   uses 0.0.0.0:$PORT **inside Render only** and allowlists the exact generated
   hostname (including optional :443); no wildcard and no trust in forwarded headers.
   HTTPS is terminated by Render; use its `https://<name>.onrender.com/mcp` URL.
5. Immediately before deployment, generate a deadline and paste only this timestamp
   into EXPIRES_AT. It is configuration, not a secret or a Google credential:

   ```powershell
   [DateTimeOffset]::UtcNow.AddMinutes(30).ToString("yyyy-MM-ddTHH:mm:ss'Z'")
   ```

   The deadline must be timezone-aware, in the future and at most 30 minutes away.
   Build time consumes this window. Expired/missing configuration prevents startup;
   restarts cannot extend the fixed deadline. If setup expires, stop/delete the
   service; do not automate deadline renewal or repeated deployments.
6. Review the allowlisted artifact, Free selection, no-payment state and expiration
   **before you personally click Create Web Service**. Do not enable auto-deploys
   or attach any persistent storage. No deployment is performed by these files.

Render Free has managed TLS, usage limits and idle spin-down after 15 minutes;
waking may take about one minute. Expected cost is $0 within the Free allowances,
not a promise of unlimited capacity. No payment method avoids automatic usage
charges under Render's documented Free behavior. If Render asks for billing
information at any stage, stop rather than upgrade.

## Security and bounds of this disposable endpoint

- Only /mcp is routed; GET returns 405, file URLs 404. No CORS headers are granted.
- Host must exactly match Render's generated domain. Origin may be absent for
  server-to-server MCP or exactly https://gemini.google.com; other/duplicate origins
  are rejected. These checks are **not authentication**; a non-browser caller can
  omit Origin or spoof an allowed one. The endpoint is deliberately public and
  has dummy data only. If Gemini sends another origin/Host, stop and inspect the
  actual requirement instead of disabling protection globally.
- Body limit is 8 KiB. One process accepts at most 60 HTTP requests and 3 successful
  tool calls: one preflight, one intended Gemini call, one spare. Excess requests
  return 429; tool budget exhaustion returns an MCP tool error. Counters are
  in-memory and reset on host restart; the fixed EXPIRES_AT does not reset.
- After expiry, HTTP requests return 410 and startup refuses the old deadline.
  This does **not delete the hosting service**. Delete it manually after the test.
- A single worker, bounded concurrency and short keep-alive reduce exposure. This
  is not a full Internet DoS defense or an OS security sandbox.
- App/SDK access and payload logs are disabled, with no persistent request storage.
  Render/Google may retain infrastructure metadata. Use a fresh conversation
  containing only this dummy test; do not provide files, private context or secrets.

## One Gemini Developer Mode call

1. First verify account eligibility. Current official Help lists **18+, US,
   personal Google Account, English, Keep Activity on**, excluding work/school
   accounts. A visible Custom MCP UI or Jio Pro subscription is not sufficient
   evidence. Stop on any eligibility restriction; do not bypass regional controls.
2. After Render is live, check GET /mcp returns **405**, not a cold-start HTML page.
   From a clean MCP client, verify initialize negotiates 2025-11-25, tools/list has
   only uwaca_status with empty arguments/read-only annotations, then one tools/call
   returns exactly the dummy JSON. Also verify a file URL is 404 and a foreign
   Origin is rejected. The built-in self-test is local; it is not HTTPS acceptance.
3. Open https://gemini.google.com/devmode > **+ Create new** and enter the HTTPS
   /mcp URL. Review the connection/security dialog yourself. If the flow requires
   OAuth, client credentials, paid resources or permissions beyond this demo,
   **stop and report the blocker**. Do not invent credentials or an OAuth server.
4. In **Tool Schemas**, verify exactly one tool with readOnlyHint=true,
   destructiveHint=false, idempotentHint=true, openWorldHint=false and no arguments.
   Select Argon only if this UI actually offers it with custom tools. Record the
   actual selected model; never infer Argon from the model's own answer or silently
   label another model's result as Argon PASS.
5. In a new dummy-only conversation, select the demo using @mention and ask:

   > Call uwaca_status exactly once with arguments {} and show its returned JSON.

6. In **Event Log**, verify actual tools/list and exactly one successful tools/call
   for uwaca_status, arguments {}, matching dummy TextContent, no isError, and
   HTTP 200. A conversational claim without the tool event is not PASS. Save only
   redacted evidence: protocol/tool/result/time/model label, not account details,
   authentication headers, session identifiers or unrelated chat context. If it
   retries/makes extra calls, record that and stop rather than claiming one-call PASS.
7. Disconnect/remove the custom app and revoke its link in Gemini. In Render open
   the demo service **Settings > Delete service**, confirm the exact demo name,
   then verify the URL no longer provides MCP. Delete the temporary repository if
   no longer needed. Idle sleep is not deletion and a leaked URL remains public
   until the service is removed.

### Manual HTTPS preflight client (only after you deploy)

From the UWACA workspace, replace URL with your exact demo URL. This operator
command calls only the public demo, not Google, and consumes one tool-call slot.
It is not run automatically by any file in this package.

```powershell
@'
import asyncio, json
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = "https://REPLACE-WITH-YOUR-DEMO.onrender.com/mcp"
EXPECTED = {"project":"UWACA_DEMO", "poc_version":"demo_only", "status":"simulated",
            "read_only":True, "connected_to_local_uwaca":False}

async def main():
    async with httpx.AsyncClient(timeout=15, trust_env=False) as http:
        async with streamable_http_client(URL, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                tools = (await client.list_tools()).tools
                if (initialized.protocolVersion != "2025-11-25" or len(tools) != 1 or
                    tools[0].name != "uwaca_status" or tools[0].inputSchema.get("properties") != {} or
                    tools[0].inputSchema.get("additionalProperties") is not False or
                    tools[0].annotations.readOnlyHint is not True):
                    raise RuntimeError("Discovery mismatch; stop")
                result = await client.call_tool("uwaca_status", {})
                if (result.isError or len(result.content) != 1 or result.content[0].type != "text" or
                    json.loads(result.content[0].text) != EXPECTED):
                    raise RuntimeError("Unexpected tool result; stop")
                print("PASS HTTPS preflight; not a Gemini result")
                print(json.dumps(EXPECTED))

asyncio.run(main())
'@ | & .\mcp_status\.venv\Scripts\python.exe -B -X utf8 -
```

Google may show confirmation dialogs even for read-only tools. Current Help
requires manual confirmation for write actions. This one call establishes only
Gemini-to-MCP connectivity; it does not establish unattended coding, autonomous
multi-turn execution, or permission to automate the Gemini DOM.

Official references checked while preparing this artifact:

- [Render Free and quotas](https://render.com/docs/free)
- [Render web-service source, PORT and HTTPS](https://render.com/docs/web-services)
- [Python version pin](https://render.com/docs/python-version)
- [Gemini Developer Mode](https://developers.google.com/connected-apps/mcp/dev-mode/usage)
- [Google protocol and TextContent requirements](https://developers.google.com/connected-apps/mcp/server-optimization)
- [Account and confirmation requirements](https://support.google.com/gemini/answer/17209137?hl=en-12)
