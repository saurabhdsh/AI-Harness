# AD OpenAI Code Engineer (LangGraph)

Real LangGraph `StateGraph` agent:

`ingest → static_analysis → llm_review (OpenAI or Azure OpenAI) → synthesize`

## Credentials

**Option A — Azure OpenAI** (same as `test_llm.py` on your other Mac):

```bash
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
export AZURE_OPENAI_API_VERSION=2025-04-01-preview
export AZURE_OPENAI_DEPLOYMENT=gpt-5-mini   # Azure deployment name
export OPENAI_MODEL=gpt-5-mini
```

**Option B — OpenAI public API:**

```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-4o-mini
```

If Azure vars are set, they take priority. No mock LLM fallback.

## Run

```bash
cd examples/langgraph-openai-agent
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8090
```

## Invoke

```bash
curl -s http://127.0.0.1:8090/health
curl -s http://127.0.0.1:8090/invoke -H 'Content-Type: application/json' \
  -d '{"input":{"task":"improve","use_sample":true}}'
```
