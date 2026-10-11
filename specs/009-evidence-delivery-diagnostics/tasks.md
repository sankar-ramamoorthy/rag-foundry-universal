# Issue #254 checkpoint

- [x] Specify discovery and selection diagnostics separately.
- [x] Reproduce disconnected indexed-symbol discovery misses synthetically.
- [x] Verify a resolved CALL control and generation-change rejection.
- [x] Add optional chunk exclusion tracing without changing selection.
- [x] Isolate per-document, global, filter, and byte/token limits in tests.
- [x] Check trace-on/off context parity through the service pipeline.
- [ ] Replay pinned R1/R2 with the new diagnostic code locally; record the
  runtime difference and verify generation before and after each request.
- [ ] Attribute the actual replay loss rule and competing allocation; retain
  the historical global-cap explanation as an inference unless separately
  established for that historical run.
- [ ] Review whether a bounded discovery or retention correction is justified.
- [ ] Implement and evaluate an approved correction, including frozen #240
  regression checks and a separately frozen fresh held-out protocol.

No deployment, PR, merge, live re-ingestion, or issue closure at this checkpoint.
