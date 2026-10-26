# Weave — Knowledge Fabric adapter

**Status:** Contract stub — blocked on real Weave API credentials/contract.

Harness will use Weave for knowledge context, retrieval, grounding, and provenance.  
Do **not** recreate Weave inside Harness.

Configure via `WEAVE_API_URL` + `WEAVE_API_TOKEN`. Until set, callers must surface an integration-unavailable error (no mock knowledge responses).
