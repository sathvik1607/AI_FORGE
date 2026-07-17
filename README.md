# HR Analytics MCP — OpenAI Agent

An MCP server for HR analytics over `hr_db`, powered by a **server-side GPT-4o
agent** that does NL→SQL end to end: it reads the schema, writes and runs the
SQL (self-correcting on errors), and returns the data plus a short narrative.

Headline tool: **`ask_analytics`**. Requires an `OPENAI_API_KEY`. Can also run
standalone (`python nl2sql.py "..."`) with no MCP client.

## The agent (`nl2sql.py`)

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
python nl2sql.py "Which department has the highest attrition rate?"   # standalone
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

## Deploy on Render

The server auto-detects Render (via the `RENDER` env var Render sets for you):
locally it speaks **stdio**; on Render it serves **Streamable HTTP** at `/mcp`
on `$PORT`, with a `/health` check. Remote MCP clients connect to
`https://<your-service>.onrender.com/mcp`.

**1. Push to a Git repo.** Render deploys from GitHub/GitLab. `.env` is
git-ignored — never commit it; the secrets go in the dashboard (step 3).

**2. Create the service** — either way uses the committed [`render.yaml`](render.yaml):
- *Blueprint (recommended):* Render dashboard → **New → Blueprint** → pick the repo.
  It reads `render.yaml` (web service, `pip install -r requirements.txt`,
  `python server.py`, health check `/health`).
- *Manual:* **New → Web Service** → Build `pip install -r requirements.txt`,
  Start `python server.py`, Health check path `/health`.

**3. Set the secret env vars** in the Render dashboard (they are `sync: false`
in `render.yaml`, so their **values** are never committed):

| Variable | |
|---|---|
| `OPENAI_API_KEY` | your OpenAI key (required for `ask_analytics`) |
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` | the `hr_db` RDS credentials |

`DB_NAME` (`hr_db`), `DB_PORT` (`3306`), and `OPENAI_MODEL` (`gpt-4o`) are
committed as non-secret defaults. Render injects `RENDER`, `PORT`, and
`RENDER_EXTERNAL_URL` automatically — `RENDER_EXTERNAL_URL` is added to the
allowed-hosts list so DNS-rebinding protection stays on. To allow additional
hostnames, set `ALLOWED_HOSTS` (comma-separated, no scheme).

**4. Deploy.** Watch the log for `Starting HR OpenAI MCP on port … (Streamable HTTP at /mcp)`,
then verify `https://<your-service>.onrender.com/health` returns `OK`.

> **Free tier** sleeps after ~15 min idle → a ~50 s cold start on the next
> request. For always-on, set `plan: starter` (~$7/mo) in `render.yaml`.
> **Cost note:** every `ask_analytics` call is ~2 GPT‑4o calls — the free
> `run_db_query` path stays available for zero-cost exact SQL.

## Layout

```
HR_MCP_openai/
├── config.py             .env + shared engine + OpenAI settings
├── nl2sql.py             the LangGraph GPT-4o NL->SQL agent
├── adapters/
│   ├── query.py          schema text + run_query (read-only, shared)
│   └── analytics.py      safe wrapper around run_agent
├── tools/
│   ├── analytics.py      ask_analytics
│   └── query.py          get_db_schema + run_db_query
├── server.py             FastMCP "hr-openai"; stdio locally, HTTP on Render
├── render.yaml           Render deploy config (web service + /health)
├── requirements.txt
└── .gitignore            keeps .env (OPENAI_API_KEY + DB creds) out of git
```

Data lives in `hr_db` (MySQL on AWS RDS). This project is read-only.
