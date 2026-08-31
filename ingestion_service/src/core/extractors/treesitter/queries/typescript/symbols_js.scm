; WP-L2 symbol candidates for the plain JavaScript grammar. No
; `interface_declaration` (JS has no interfaces) and the class-property
; node is named `field_definition` here, not `public_field_definition`
; (TypeScript's name for the same construct — see symbols_ts.scm; the two
; grammars reject each other's node-type names at Query compile time,
; hence two files).
(class_declaration) @node
(function_declaration) @node
(method_definition) @node
(field_definition) @node
(variable_declarator) @node

; Raw arrow/function expressions, captured so the extractor can tell named
; bindings (already covered above via their variable_declarator/field
; wrapper) apart from anonymous ones, which produce no symbol but are
; counted in the enclosing symbol's metadata (FR-002).
(arrow_function) @node
(function_expression) @node
