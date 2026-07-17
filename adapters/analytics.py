"""
Adapter: wraps hr_nl2sql_agent.run_agent for the ask_analytics tool.
Never leaks tracebacks to the client — returns a safe error message instead.
"""
import config  # MUST be first

from hr_nl2sql_agent import run_agent as _run_agent


def run_agent(question: str) -> dict:
    try:
        return _run_agent(question)
    except RuntimeError as exc:
        # e.g. missing OPENAI_API_KEY — surface this one clearly, it's actionable
        return {"generated_sql": None, "analysis": None, "insights": None, "error": str(exc)}
    except Exception:
        return {"generated_sql": None, "analysis": None, "insights": None,
                "error": "An unexpected error occurred while answering. Please try again."}
