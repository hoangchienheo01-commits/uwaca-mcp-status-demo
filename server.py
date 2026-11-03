"""Disposable Render demo: one MCP tool, fixed dummy data, no local UWACA connection."""

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
import re
import time

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
import uvicorn

BODY_LIMIT = 8192
REQUEST_LIMIT = 60
TOOL_CALL_LIMIT = 3  # One client preflight + one Gemini call, with one spare.
ORIGIN = "https://gemini.google.com"
STATUS = {"project": "UWACA_DEMO", "poc_version": "demo_only", "status": "simulated",
          "read_only": True, "connected_to_local_uwaca": False}
TOOL = types.Tool(name="uwaca_status", description="Return a fixed, non-sensitive UWACA demo status.",
    inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=False))


def utc_now():
    return time.time()


def configuration(env):
    """Cloud startup is explicit and fail-closed. Never derive expiry from startup time."""
    if env.get("RENDER") != "true":
        raise ValueError("Render startup only; use --self-test locally")
    hostname = env.get("RENDER_EXTERNAL_HOSTNAME", "")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.onrender\.com", hostname):
        raise ValueError("Expected an exact Render hostname")
    try:
        port = int(env["PORT"])
        expiry = datetime.fromisoformat(env["EXPIRES_AT"].replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            raise ValueError()
        deadline = expiry.timestamp()
        if not 1024 <= port <= 65535 or not 0 < deadline - utc_now() <= 1800:
            raise ValueError()
    except (KeyError, ValueError, OverflowError):
        raise ValueError("Require PORT and a timezone-aware EXPIRES_AT within the next 30 minutes") from None
    return port, hostname, deadline


def quiet_logs():
    # SDK errors can contain caller-supplied strings. Do not log request data/headers.
    for name in ("mcp", "uvicorn", "httpx", "httpcore"):
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False


def create_app(port, hostname, deadline):
    server = Server("UWACA Demo", version="0.1.0", instructions="Provides simulated demo status only.")
    calls = 0

    @server.list_tools()
    async def list_tools():
        return [TOOL]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        nonlocal calls
        if name != "uwaca_status" or arguments != {}:
            raise ValueError("Only uwaca_status with empty arguments is supported")
        if utc_now() >= deadline or calls >= TOOL_CALL_LIMIT:
            raise ValueError("Demo expired or tool-call budget exhausted")
        calls += 1
        return [types.TextContent(type="text", text=json.dumps(STATUS))]

    hosts = [hostname, hostname + ":443"]
    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True,
        max_request_body_size=BODY_LIMIT, security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=[ORIGIN]))

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    class Endpoint:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)

    app = Starlette(routes=[Route("/mcp", Endpoint(), methods=["POST", "DELETE"])], lifespan=lifespan)

    class Guard:
        """Small per-instance budget; absolute expiry remains effective across restarts."""
        def __init__(self):
            self.requests = 0

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await app(scope, receive, send)
            headers = [(k.lower(), v.decode("latin-1")) for k, v in scope["headers"]]
            host_values = [v for k, v in headers if k == b"host"]
            origins = [v for k, v in headers if k == b"origin"]
            if len(host_values) != 1 or host_values[0] not in hosts:
                response = PlainTextResponse("Invalid host", status_code=421)
            elif len(origins) > 1 or (origins and origins[0] != ORIGIN):
                response = PlainTextResponse("Invalid origin", status_code=403)
            elif utc_now() >= deadline:
                response = PlainTextResponse("Demo expired", status_code=410)
            elif self.requests >= REQUEST_LIMIT:
                response = PlainTextResponse("Demo request budget exhausted", status_code=429)
            else:
                self.requests += 1  # Single worker; no await between check and increment.
                return await app(scope, receive, send)
            await response(scope, receive, send)

    return Guard()


async def self_test():
    """Real loopback HTTP using a simulated Render Host header, never the Internet."""
    import socket
    import threading
    from unittest.mock import patch
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    quiet_logs()
    passed = []

    def check(name, value):
        if not value:
            raise RuntimeError("FAIL: " + name)
        passed.append(name)

    hostname = "uwaca-demo-test.onrender.com"
    deadline = int(utc_now()) + 1200
    env = {"RENDER": "true", "PORT": "10000", "RENDER_EXTERNAL_HOSTNAME": hostname,
           "EXPIRES_AT": datetime.fromtimestamp(deadline, timezone.utc).isoformat()}
    check("render_configuration", configuration(env) == (10000, hostname, deadline))
    for key, value in (("RENDER", "false"), ("PORT", "0"), ("RENDER_EXTERNAL_HOSTNAME", "*.onrender.com"),
                       ("EXPIRES_AT", "2000-01-01T00:00:00Z"), ("EXPIRES_AT", "2099-01-01T00:00:00Z"),
                       ("EXPIRES_AT", "2099-01-01T00:00:00")):
        try:
            configuration(dict(env, **{key: value}))
        except ValueError:
            check("reject_config_" + key + "_" + str(len(passed)), True)
        else:
            raise RuntimeError("Unsafe configuration accepted")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}/mcp"
        runner = uvicorn.Server(uvicorn.Config(create_app(port, hostname, deadline), host="127.0.0.1",
            port=port, log_config=None, access_log=False, proxy_headers=False))
        thread = threading.Thread(target=runner.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            start = time.monotonic()
            while not runner.started:
                if not thread.is_alive() or time.monotonic() - start > 10:
                    raise RuntimeError("Local test server failed to start")
                await asyncio.sleep(0.02)
            async with httpx.AsyncClient(headers={"Host": hostname}, trust_env=False, timeout=5) as http:
                async with streamable_http_client(url, http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as client:
                        initialized = await client.initialize()
                        check("initialize_2025_11_25", initialized.protocolVersion == "2025-11-25")
                        listed = await client.list_tools()
                        check("exactly_one_read_only_tool", len(listed.tools) == 1 and
                              listed.tools[0].model_dump() == TOOL.model_dump())
                        check("no_resources_or_prompts", initialized.capabilities.resources is None and
                              initialized.capabilities.prompts is None)
                        result = await client.call_tool("uwaca_status", {})
                        check("fixed_dummy_json_text", not result.isError and len(result.content) == 1 and
                              result.content[0].type == "text" and json.loads(result.content[0].text) == STATUS)
                        check("extra_arguments_rejected", (await client.call_tool("uwaca_status", {"path": "x"})).isError)
                        check("unknown_tool_rejected", (await client.call_tool("read_file", {})).isError)
                        for _ in range(TOOL_CALL_LIMIT - 1):
                            check("within_tool_budget_" + str(len(passed)), not
                                  (await client.call_tool("uwaca_status", {})).isError)
                        check("tool_budget_enforced", (await client.call_tool("uwaca_status", {})).isError)
                check("get_405", (await http.get(url)).status_code == 405)
                check("no_source_serving", (await http.get(url.replace("/mcp", "/server.py"))).status_code == 404)
                check("wrong_host_rejected", (await http.get(url, headers={"Host": "other.invalid"})).status_code == 421)
                check("wrong_origin_rejected", (await http.get(url, headers={"Origin": "https://other.invalid"})).status_code == 403)
                check("allowed_origin", (await http.get(url, headers={"Origin": ORIGIN})).status_code == 405)
                headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
                check("body_limit", (await http.post(url, content=" " * (BODY_LIMIT + 1), headers=headers)).status_code == 413)
                check("malformed_json", (await http.post(url, content="{", headers=headers)).status_code == 400)
                for _ in range(REQUEST_LIMIT + 1):
                    response = await http.get(url)
                    if response.status_code == 429:
                        break
                check("request_budget_enforced", response.status_code == 429)
                # Move only this module's clock; the ASGI/SDK clocks remain real.
                with patch(__name__ + ".utc_now", return_value=deadline + 1):
                    check("fixed_expiry_enforced", (await http.get(url)).status_code == 410)
                    check("restart_cannot_renew_expiry", _configuration_rejected(env))
            return {"overall": "PASS", "checks_passed": len(passed), "checks": passed,
                    "protocol": initialized.protocolVersion, "tool_result": json.loads(result.content[0].text),
                    "internet_deployed": False, "gemini_tested": False}
        finally:
            runner.should_exit = True
            await asyncio.to_thread(thread.join, 5)
            if thread.is_alive():
                raise RuntimeError("Local test server did not stop")


def _configuration_rejected(env):
    try:
        configuration(env)
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    quiet_logs()
    if args.self_test:
        print(json.dumps(asyncio.run(self_test()), indent=2))
    else:
        try:
            port, hostname, deadline = configuration(os.environ)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        uvicorn.run(create_app(port, hostname, deadline), host="0.0.0.0", port=port,
                    log_config=None, access_log=False, proxy_headers=False,
                    workers=1, limit_concurrency=8, timeout_keep_alive=3)
