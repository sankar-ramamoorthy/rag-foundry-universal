; WP-L4 call-expression candidates. `object_creation_expression`
; (`new Foo(...)`) is captured alongside `method_invocation` so
; JavaExtractor can lower it to a CALL against `Foo.<init>` — reusing the
; same qualified-call resolution path as any other `receiver.method()`
; call, no new GraphAssembler logic needed.
(method_invocation) @node
(object_creation_expression) @node
