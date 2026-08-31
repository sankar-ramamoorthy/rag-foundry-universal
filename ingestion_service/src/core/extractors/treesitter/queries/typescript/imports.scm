; WP-L2 import candidates: ESM imports and re-exports-from. A plain
; `export class X {}` (no `from` clause) also matches export_statement;
; TypeScriptExtractor filters those out by checking for a `source` field.
(import_statement) @node
(export_statement) @node
