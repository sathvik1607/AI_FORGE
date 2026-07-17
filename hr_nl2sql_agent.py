"""
hr_nl2sql_agent.py — OpenAI-agentic NL->SQL pipeline for hr_db.

A lean LangGraph agent modelled on the allpets nl2sql pattern, pointed at the HR
database. Three nodes:

    generate_sql  → GPT writes a MySQL SELECT from the schema + question
                    (on a retry, it also sees the previous SQL + DB error)
    execute_sql   → runs it read-only; on error, loops back to generate_sql
    insights      → GPT writes a short business narrative from the rows

Entry point: run_agent(question) -> {generated_sql, analysis, insights, error}

The LLM is created lazily, so importing this module (and building the graph)
works even before OPENAI_API_KEY is set — only run_agent() actually calls OpenAI.
"""
from typing import Any, Dict, List, Optional, TypedDict

import config  # MUST be first — loads .env (DB + OPENAI_API_KEY) and builds the engine

from adapters.query import SCHEMA_FOR_CLAUDE, run_query

MAX_ATTEMPTS = 3   # SQL generation attempts before giving up

# ── lazy LLM singletons (so import works without a key) ───────────────────────
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to .env before using ask_analytics."
            )
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(
            model=config.OPENAI_MODEL,
            temperature=0,
            api_key=config.OPENAI_API_KEY,
            timeout=60,
        )
    return _llm


# ── graph state ───────────────────────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    question: str
    sql: str
    columns: List[str]
    rows: List[dict]
    row_count: int
    insights: Optional[str]
    error: Optional[str]
    attempts: int
    last_error: Optional[str]


# ── prompts ───────────────────────────────────────────────────────────────────
_SQL_SYSTEM = (
    "You are an expert MySQL analyst for an HR analytics database. "
    "Given the schema and a question, output ONE valid MySQL SELECT query that answers it. "
    "Rules: read-only SELECT/WITH only; never write/DDL. Respect the schema's pitfalls "
    "(CTC columns are in LAKHS — multiply by 100000 for rupees; the `month` column is text "
    "like 'Jan-2026', sort it with STR_TO_DATE(CONCAT('01-', month), '%d-%b-%Y')). "
    "Return ONLY the SQL — no explanation, no markdown fences."
)

_INSIGHTS_SYSTEM = (
    "You are an HR analytics assistant. Given a question and the query result rows, "
    "write a concise, business-friendly answer (2-4 sentences). Use ₹ with Indian number "
    "grouping for money (e.g. ₹2,64,947). State the key numbers plainly. Do not invent data."
)


def _strip_sql_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("sql"):
            t = t.lstrip()[3:]
    return t.strip().rstrip(";").strip()


# ── nodes ─────────────────────────────────────────────────────────────────────
def _generate_sql(state: AgentState) -> AgentState:
    from langchain_core.messages import HumanMessage, SystemMessage

    parts = [f"SCHEMA:\n{SCHEMA_FOR_CLAUDE}\n", f"QUESTION: {state['question']}"]
    if state.get("last_error") and state.get("sql"):
        parts.append(
            f"\nYour previous SQL failed:\n{state['sql']}\n\nDatabase error:\n{state['last_error']}\n"
            "Fix it and return corrected SQL only."
        )
    resp = _get_llm().invoke([SystemMessage(content=_SQL_SYSTEM),
                              HumanMessage(content="\n".join(parts))])
    return {**state,
            "sql": _strip_sql_fences(resp.content),
            "attempts": state.get("attempts", 0) + 1}


def _execute_sql(state: AgentState) -> AgentState:
    r = run_query(state["sql"])
    if r["error"]:
        return {**state, "last_error": r["error"]}
    return {**state,
            "columns": r["columns"], "rows": r["rows"],
            "row_count": r["row_count"], "last_error": None}


def _generate_insights(state: AgentState) -> AgentState:
    from langchain_core.messages import HumanMessage, SystemMessage

    sample = state.get("rows", [])[:50]
    user = (f"QUESTION: {state['question']}\n\nSQL: {state['sql']}\n\n"
            f"ROWS ({state.get('row_count', 0)} total, showing up to 50):\n{sample}")
    try:
        resp = _get_llm().invoke([SystemMessage(content=_INSIGHTS_SYSTEM),
                                  HumanMessage(content=user)])
        return {**state, "insights": resp.content.strip(), "error": None}
    except Exception as exc:
        return {**state, "insights": None, "error": None, "last_error": str(exc)}


def _route_after_execute(state: AgentState) -> str:
    if not state.get("last_error"):
        return "insights"
    if state.get("attempts", 0) < MAX_ATTEMPTS:
        return "generate_sql"
    return "give_up"


# ── graph (built once) ────────────────────────────────────────────────────────
def _build_graph():
    from langgraph.graph import END, StateGraph

    g = StateGraph(AgentState)
    g.add_node("generate_sql", _generate_sql)
    g.add_node("execute_sql", _execute_sql)
    g.add_node("insights", _generate_insights)
    g.set_entry_point("generate_sql")
    g.add_edge("generate_sql", "execute_sql")
    g.add_conditional_edges("execute_sql", _route_after_execute,
                            {"insights": "insights", "generate_sql": "generate_sql", "give_up": END})
    g.add_edge("insights", END)
    return g.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── public entry point ────────────────────────────────────────────────────────
def run_agent(question: str) -> Dict[str, Any]:
    """
    Answer a natural-language HR question end-to-end via the OpenAI agent.

    Returns: {generated_sql, analysis: {columns, rows, row_count}, insights, error}
    """
    final = _get_graph().invoke({"question": question, "attempts": 0})

    if final.get("rows") is None and final.get("last_error"):
        return {"generated_sql": final.get("sql"), "analysis": None,
                "insights": None, "error": final["last_error"]}

    return {
        "generated_sql": final.get("sql"),
        "analysis": {
            "columns":   final.get("columns", []),
            "rows":      final.get("rows", []),
            "row_count": final.get("row_count", 0),
        },
        "insights": final.get("insights"),
        "error": None,
    }


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Which department has the highest attrition rate?"
    from pprint import pprint
    pprint(run_agent(q))
