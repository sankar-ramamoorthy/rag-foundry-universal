; WP-L3: macro invocations (`format!(...)`, `vec![...]`, etc.) — bodies
; are skipped entirely (issue #130); only a per-owner count is recorded
; in SymbolRecord.metadata["macro_invocations"], mirroring how WP-L2
; counts anonymous callbacks.
(macro_invocation) @node
