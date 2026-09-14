; WP-L3 symbol candidates for the Rust grammar. Each pattern captures a
; node type that MAY be symbol-bearing; RustExtractor's _classify() +
; _container_kind() apply the precise rules tree-sitter query syntax can't
; express (e.g. "only a function_item directly inside an impl/trait/mod
; body or at file scope, not one nested inside another function's block").
(struct_item) @node
(enum_item) @node
(trait_item) @node
(impl_item) @node
(function_item) @node
(mod_item) @node
