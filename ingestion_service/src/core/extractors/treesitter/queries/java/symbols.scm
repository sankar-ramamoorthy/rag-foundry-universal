; WP-L4 symbol candidates for the Java grammar. Each pattern captures a
; node type that MAY be symbol-bearing; JavaExtractor's _classify() +
; overload-grouping in _build_symbols() apply the precise rules tree-
; sitter query syntax can't express (e.g. collapsing method_declaration
; nodes that share a name into one overload-aware METHOD symbol).
(class_declaration) @node
(interface_declaration) @node
(enum_declaration) @node
(record_declaration) @node
(method_declaration) @node
(constructor_declaration) @node
