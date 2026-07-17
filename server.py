"""
hr_mcp_openai — MCP server for HR analytics, OpenAI-agent variant.

Headline tool: ask_analytics — a server-side GPT-4o NL->SQL agent (LangGraph)
that reads the schema, writes+runs SQL (self-correcting), and narrates results.
Also exposes get_db_schema + run_db_query for the raw, no-LLM path.

Requires OPENAI_API_KEY in .env for ask_analytics.

Run:
    python server.py                 # local: stdio transport (Claude Desktop)
    python -m mcp dev server.py      # MCP dev inspector
    python nl2sql.py "..."           # run the agent standalone (no MCP)

When the RENDER env var is set (i.e. running on Render), server.py instead
serves Streamable HTTP at /mcp on $PORT with a /health check — see the
"Deploy on Render" section of the README.
"""
import builtins
import os
import sys

_real_print = builtins.print
def _stderr_print(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    _real_print(*args, **kwargs)
builtins.print = _stderr_print

import config  # MUST be first real import — loads .env + builds engine

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from tools import analytics as analytics_tools
from tools import query as query_tools

# On Render, allow the public hostname (RENDER_EXTERNAL_URL, auto-set by Render)
# plus any extra hosts in ALLOWED_HOSTS (comma-separated, no scheme). Locally
# there is no such env var, so this collapses to localhost.
_render_host = os.getenv("RENDER_EXTERNAL_URL", "").replace("https://", "").strip("/")
_extra_hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
_all_hosts   = list({h for h in [_render_host, *_extra_hosts] if h})
_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=_all_hosts or ["localhost"],
    allowed_origins=[f"https://{h}" for h in _all_hosts] or ["http://localhost"],
)

_INSTRUCTIONS = (
    "You are connected to an HR analytics database (hr_db). Prefer ask_analytics for "
    "natural-language questions — it runs a server-side GPT-4o agent that writes and "
    "executes the SQL and returns data plus a narrative. Use get_db_schema + run_db_query "
    "when you want to inspect the schema or run exact SQL yourself without an OpenAI call. "
    "All money is Indian Rupees (₹); CTC columns are in lakhs (×100000 for rupees)."
)

mcp = FastMCP(
    name="hr-openai",
    json_response=True,
    instructions=_INSTRUCTIONS,
    transport_security=_TRANSPORT_SECURITY,
)

analytics_tools.register(mcp)   # ask_analytics  (GPT-4o agent)
query_tools.register(mcp)       # get_db_schema + run_db_query

if __name__ == "__main__":
    # ── Render (Streamable HTTP) ────────────────────────────────────────────────
    if os.getenv("RENDER"):
        import uvicorn
        from starlette.requests import Request
        from starlette.responses import PlainTextResponse, Response
        from starlette.routing import Route

        port = int(os.getenv("PORT", "8000"))

        # streamable_http_app() carries its own lifespan (it starts the HTTP
        # session manager), so inject /health into ITS router — don't wrap it in
        # an outer app, which would drop that lifespan and break /mcp.
        app = mcp.streamable_http_app()

        async def health(request: Request) -> Response:
            return PlainTextResponse("OK")

        app.router.routes.insert(0, Route("/health", endpoint=health, methods=["GET"]))

        print(f"Starting HR OpenAI MCP on port {port} (Streamable HTTP at /mcp)")
        uvicorn.run(app, host="0.0.0.0", port=port)

    # ── Local dev (stdio) ───────────────────────────────────────────────────────
    else:
        mcp.run(transport="stdio")
