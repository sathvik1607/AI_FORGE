# HR MCP — OpenAI Agent variant

Same HR database (`hr_db`), different querying model. Where the sibling `HR_MCP`
project lets **Claude** write the SQL, this variant runs a **server-side GPT-4o
agent** that does NL→SQL end to end.

## How it differs from HR_MCP

| | HR_MCP (Claude variant) | HR_MCP_openai (this) |
|---|---|---|
| Who writes SQL | the MCP client's model (Claude) | a GPT-4o agent inside the server |
| Headline tool | `run_db_query` | `ask_analytics` |
| OpenAI key | not needed | **required** (`OPENAI_API_KEY`) |
| Runs standalone | no | yes (`python hr_nl2sql_agent.py "..."`) |

## The agent (`hr_nl2sql_agent.py`)

A LangGraph pipeline:

```
generate_sql  → GPT writes a MySQL SELECT from schema + question
execute_sql   → runs it read-only; on error loops back to generate_sql (up to 3 tries)
insights      → GPT writes a short business narrative from the rows
```

`run_agent(question)` → `{generated_sql, analysis:{columns,rows,row_count}, insights, error}`

## Tools

| Tool | Uses OpenAI? | Purpose |
|---|---|---|
| `ask_analytics(question)` | yes | Full NL→SQL→answer agent |
| `get_db_schema()` | no | Return schema for manual SQL |
| `run_db_query(sql)` | no | Run exact read-only SQL |

## Setup

```bash
pip install -r requirements.txt
# .env already holds DB creds + OPENAI_API_KEY (gitignored)
```

## Run

```bash
python hr_nl2sql_agent.py "Which department has the highest attrition rate?"   # standalone
python server.py                                                              # MCP stdio
python -m mcp dev server.py                                                   # inspector
```

### Claude Desktop config
```json
{
  "mcpServers": {
    "hr-openai": {
      "command": "C:/Users/sathv/AppData/Local/Programs/Python/Python311/python.exe",
      "args": ["C:/Users/sathv/Desktop/HR_MCP_openai/server.py"]
    }
  }
}
```

## Layout

```
HR_MCP_openai/
├── config.py             .env + shared engine + OpenAI settings
├── hr_nl2sql_agent.py    the LangGraph GPT-4o NL->SQL agent
├── adapters/
│   ├── query.py          schema text + run_query (read-only, shared)
│   └── analytics.py      safe wrapper around run_agent
├── tools/
│   ├── analytics.py      ask_analytics
│   └── query.py          get_db_schema + run_db_query
├── server.py             FastMCP "hr-openai"; registers all tools
└── requirements.txt
```

Data lives in `hr_db` — loaded by the sibling `HR_MCP/load_data.py`. This project reads only.
