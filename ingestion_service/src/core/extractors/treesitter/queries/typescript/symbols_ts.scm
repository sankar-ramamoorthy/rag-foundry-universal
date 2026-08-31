; WP-L2 symbol candidates for the TypeScript/TSX grammars. Each pattern
; captures a node type that MAY be symbol-bearing; TypeScriptExtractor's
; _classify() applies the precise per-spec rules (e.g. "only a
; named-binding arrow function, not an anonymous one") that tree-sitter
; query syntax can't express cleanly. `public_field_definition` is this
; grammar's name for a class-property declaration (the plain JavaScript
; grammar calls the same construct `field_definition` — see symbols_js.scm
; — the two grammars reject each other's node-type names at Query compile
; time, hence two files).
(class_declaration) @node
(interface_declaration) @node
(function_declaration) @node
(method_definition) @node
(public_field_definition) @node
(variable_declarator) @node

; Raw arrow/function expressions, captured so the extractor can tell named
; bindings (already covered above via their variable_declarator/field
; wrapper) apart from anonymous ones, which produce no symbol but are
; counted in the enclosing symbol's metadata (FR-002).
(arrow_function) @node
(function_expression) @node
