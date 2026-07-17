"""
hr_mcp_openai — MCP server for HR analytics, OpenAI-agent variant.

Headline tool: ask_analytics — a server-side GPT-4o NL->SQL agent (LangGraph)
that reads the schema, writes+runs SQL (self-correcting), and narrates results.
Also exposes get_db_schema + run_db_query for the raw, no-LLM path.

Requires OPENAI_API_KEY in .env for ask_analytics.

Run:
    python server.py                 # stdio transport (Claude Desktop, local)
    python -m mcp dev server.py      # MCP dev inspector
    python hr_nl2sql_agent.py "..."  # run the agent standalone (no MCP)
"""
import builtins
import sys

_real_print = builtins.print
def _stderr_print(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    _real_print(*args, **kwargs)
builtins.print = _stderr_print

import config  # MUST be first real import — loads .env + builds engine

from mcp.server.fastmcp import FastMCP

from tools import analytics as analytics_tools
from tools import query as query_tools

_INSTRUCTIONS = (
    "You are connected to an HR analytics database (hr_db). Prefer ask_analytics for "
    "natural-language questions — it runs a server-side GPT-4o agent that writes and "
    "executes the SQL and returns data plus a narrative. Use get_db_schema + run_db_query "
    "when you want to inspect the schema or run exact SQL yourself without an OpenAI call. "
    "All money is Indian Rupees (₹); CTC columns are in lakhs (×100000 for rupees)."
)

mcp = FastMCP(name="hr-openai", json_response=True, instructions=_INSTRUCTIONS)

analytics_tools.register(mcp)   # ask_analytics  (GPT-4o agent)
query_tools.register(mcp)       # get_db_schema + run_db_query

if __name__ == "__main__":
    mcp.run(transport="stdio")
