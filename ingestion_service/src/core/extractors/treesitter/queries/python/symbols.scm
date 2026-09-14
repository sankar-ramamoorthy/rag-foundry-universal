; WP-L5 symbol candidates for the Python grammar. Matches regardless of
; decorator wrapping (`decorated_definition` is transparent here — its
; inner class_definition/function_definition is still captured directly).
; PythonTreeSitterExtractor classifies FUNCTION vs. METHOD and builds
; symbol_path in Python, mirroring PythonASTExtractor's scope-stack rules
; exactly (including its nearest-class-ancestor quirk for nested classes).
(class_definition) @node
(function_definition) @node
