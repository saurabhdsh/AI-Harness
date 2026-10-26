# LangGraph Reference Agent (AD Code Engineering)

Primary demo agent for TCS AI Harness. Exposes LangGraph-style `/invoke` and `/runs`
endpoints and performs **real deterministic** analysis of code snippets (Python AST + heuristics).

Works fully offline — no API keys required.

## Quick start

```bash
cd examples/langgraph-agent
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

Docker:

```bash
docker build -t tcs-langgraph-agent .
docker run --rm -p 8080:8080 tcs-langgraph-agent
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/agents` | List agents |
| GET | `/agents/{id}` | Agent detail |
| POST | `/invoke` | Run analysis |
| POST | `/runs` | Alias for `/invoke` |

### Invoke body

```json
{
  "input": {
    "task": "analyze",
    "repo_snippet": "def foo(a,b,c,d,e,f):\n    pass\n",
    "instruction": "Focus on complexity"
  },
  "agent_id": "ad-code-engineering"
}
```

Use `"task": "improve"` for a unified-diff `proposed_patch`.  
Set `"use_sample": true` to analyze `sample_repo/snippet.py`.

### Demo curl

```bash
curl -s http://localhost:8080/invoke -H 'Content-Type: application/json' \
  -d '{"input":{"task":"improve","use_sample":true}}' | python -m json.tool
```
