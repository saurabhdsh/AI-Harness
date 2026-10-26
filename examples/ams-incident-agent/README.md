# AMS Incident Agent (Digital Twin)

Thin AMS wrapper that:

1. Emits synthetic incidents via `GET /twin/events`
2. Proxies analysis to `examples/rest-agent` (`REST_AGENT_URL`, default `http://127.0.0.1:8082`)
3. Falls back to inline keyword RCA if rest-agent is down

Default port **8084**.

```bash
# Terminal A — rest-agent
cd ../rest-agent && uvicorn main:app --port 8082

# Terminal B — twin
pip install -r requirements.txt
uvicorn main:app --port 8084
```

```bash
curl -s 'http://localhost:8084/twin/events?count=2' | python -m json.tool
curl -s http://localhost:8084/invoke -H 'Content-Type: application/json' \
  -d '{"input":{"from_twin":true}}'
```
