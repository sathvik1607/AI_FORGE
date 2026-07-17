"""
Tools: get_db_schema + run_db_query — the raw, no-LLM path (same as the Claude
variant). Kept alongside ask_analytics so callers can inspect the schema or run
exact SQL without incurring an OpenAI call.
"""
from mcp.server.fastmcp import FastMCP

import adapters.query as _adapter


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def get_db_schema() -> dict:
        """Return the hr_db schema (tables, columns, join keys, pitfalls). Call once before writing SQL."""
        return _adapter.get_schema()

    @mcp.tool()
    def run_db_query(sql: str) -> dict:
        """
        Execute a read-only SELECT/WITH query against hr_db (no OpenAI call).

        Rules: SELECT/WITH only; 500-row cap. Returns columns, rows, row_count, truncated, error.

        Args:
            sql: A valid MySQL SELECT statement.
        """
        return _adapter.run_query(sql)
