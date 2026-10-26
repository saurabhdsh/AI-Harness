# REST AMS Incident Agent

Rule-based incident analysis on port **8082**.

```bash
pip install -r requirements.txt
uvicorn main:app --port 8082
```

```bash
curl -s http://localhost:8082/invoke -H 'Content-Type: application/json' \
  -d '{"input":{"title":"API timeouts","logs":"connection refused to payments-db","severity":"high"}}'
```

OpenAPI: `GET /openapi.json`
