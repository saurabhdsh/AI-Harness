# QE Test Agent

Port **8083** — generates pytest stubs from requirements text and validates test structure.

```bash
pip install -r requirements.txt
uvicorn main:app --port 8083
```

Generate:

```bash
curl -s http://localhost:8083/invoke -H 'Content-Type: application/json' \
  -d '{"input":{"action":"generate","requirements":"- Login succeeds with valid credentials\n- Login fails with bad password"}}'
```

Validate:

```bash
curl -s http://localhost:8083/invoke -H 'Content-Type: application/json' \
  -d '{"input":{"action":"validate","source":"import pytest\n\ndef test_ok():\n    assert True\n"}}'
```
