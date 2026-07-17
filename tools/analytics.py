"""
Tool: ask_analytics — the OpenAI-agentic NL->SQL entry point.
"""
from mcp.server.fastmcp import FastMCP

import adapters.analytics as _adapter


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def ask_analytics(question: str) -> dict:
        """
        Ask any natural-language question about the HR data (hr_db).

        Runs a GPT-4o NL->SQL agent server-side: it reads the schema, writes a
        MySQL query, executes it (self-correcting on errors), and returns the
        data plus a short narrative. Use for headcount, payroll, attendance,
        performance, attrition, org-hierarchy, and cross-table questions.

        Returns:
        - generated_sql: the SQL the agent ran
        - analysis:      {columns, rows, row_count}
        - insights:      plain-language summary
        - error:         null on success, message on failure

        Args:
            question: A plain-language HR analytics question.
        """
        return _adapter.run_agent(question)
