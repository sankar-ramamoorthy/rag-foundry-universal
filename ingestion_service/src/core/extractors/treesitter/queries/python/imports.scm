; WP-L5 import candidates: `import x[.y][ as z]` and `from x import y[,
; z][ as w]`, including relative (`from . import`, `from ..pkg import`)
; and wildcard (`from x import *`) shapes — classified in Python since
; alias/level extraction needs field-level node inspection.
(import_statement) @node
(import_from_statement) @node
; `from __future__ import x` is its own grammar rule, distinct from
; import_from_statement (no `module_name` field — the module is always
; the literal `__future__`) — must be captured separately or it's
; silently dropped.
(future_import_statement) @node
