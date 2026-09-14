; WP-L3 call-expression candidates. `macro_invocation` nodes (e.g.
; `format!(...)`) are queried separately by RustExtractor for
; metadata-only counting — they are never CallSite evidence (issue #130:
; "skip macro bodies, record macro_invocation metadata counts").
(call_expression) @node
