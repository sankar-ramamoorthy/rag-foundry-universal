; WP-L2 call-expression candidates. `require(...)` calls are handled by
; TypeScriptExtractor as CommonJS imports rather than CallSite evidence —
; classified in Python code, not filtered here, since a query predicate
; on the callee's literal text is unnecessary complexity for one string
; comparison.
(call_expression) @node
