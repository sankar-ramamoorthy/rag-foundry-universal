# ingestion_service/src/core/codebase/module_conventions.py
"""
ModulePathConvention: how one language maps file paths to importable
module names (WP-L1, DOCS/audit/03-Multi-Language-Graph-Plan.md §2).
GraphAssembler is parameterized by one of these instead of hard-coding
Python's rules, so a future language only needs its own convention, not
changes to import resolution itself.
"""
from __future__ import annotations

import posixpath
from typing import Dict, List, Optional, Protocol, Tuple


class ModulePathConvention(Protocol):
    """A fourth, OPTIONAL method exists outside this Protocol on purpose:
    `implicit_bindings(relative_path, module_map) -> Dict[str, dict]`
    (WP-L4) — bindings available WITHOUT an explicit import statement
    (e.g. Java's same-package visibility — `Caller.java` can reference
    `Animal` from the same package with no `import`). It's deliberately
    NOT part of this Protocol: most conventions (Python/TS/Rust) don't
    need it, and Protocol methods are structurally required, not
    defaultable, for unrelated concrete classes. GraphAssembler probes
    for it duck-typed via `getattr(..., "implicit_bindings", None)` and
    no-ops if absent — see JavaModuleConvention below for the one
    convention that implements it, and
    GraphAssembler._seed_implicit_bindings for the call site. When
    present, `module_map` is dotted_path -> MODULE canonical_id for every
    file in the repo (the same map _resolve_imports already builds), and
    the returned dict is name -> binding, the same shape as one entry of
    graph.import_bindings[relative_path] — applied as a base layer before
    explicit imports, which still take priority per name."""

    def dotted_path(self, relative_path: str) -> Optional[str]:
        """`pkg/util.py` -> `pkg.util`, or None if not a module file."""
        ...

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        """Resolve a possibly-relative import base to an absolute
        dotted path. `level` is the language's relative-import depth
        (0 = already absolute)."""
        ...


class PythonModuleConvention:
    def dotted_path(self, relative_path: str) -> Optional[str]:
        if not relative_path.endswith(".py"):
            return None
        parts = relative_path[:-3].split("/")
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        if not level:
            return base
        pkg_parts = relative_path.split("/")[:-1]
        drop = level - 1
        pkg_parts = pkg_parts[: len(pkg_parts) - drop] if drop else pkg_parts
        if base:
            pkg_parts = pkg_parts + base.split(".")
        return ".".join(pkg_parts)


_TS_MODULE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


class TypeScriptModuleConvention:
    """WP-L2: relative-path-based module identity for TS/JS. Unlike
    Python's dotted names, the map keys here are extension-less,
    index-collapsed, slash-separated relative paths (`src/util.ts` ->
    `src/util`, `src/sub/index.ts` -> `src/sub`) — GraphAssembler's import
    resolution never assumes a dot-separated key shape, only exact-string
    matches on whatever dotted_path() returns (DOCS/audit/
    03-Multi-Language-Graph-Plan.md §3 WP-L2 research)."""

    def dotted_path(self, relative_path: str) -> Optional[str]:
        if not relative_path.endswith(_TS_MODULE_SUFFIXES):
            return None
        return self._collapse(relative_path)

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        # `level` has no meaning for TS/JS relative specifiers (no
        # dot-counted relative-import depth) — resolution is entirely
        # driven by whether `base` itself starts with "." / "..".
        if not base.startswith("."):
            return base  # bare specifier: left as-is for the external-
                          # module fallback in GraphAssembler
        base_dir = posixpath.dirname(relative_path)
        joined = posixpath.normpath(posixpath.join(base_dir, base))
        joined = joined.replace("\\", "/")
        return self._collapse(joined, has_suffix=False)

    def _collapse(self, path: str, has_suffix: bool = True) -> str:
        stripped = path
        if has_suffix:
            for suffix in _TS_MODULE_SUFFIXES:
                if stripped.endswith(suffix):
                    stripped = stripped[: -len(suffix)]
                    break
        parts = stripped.split("/")
        if parts and parts[-1] == "index":
            parts = parts[:-1]
        return "/".join(parts) if parts else stripped


class RustModuleConvention:
    """WP-L3: crate-qualified dotted-path convention for Rust `.rs` files
    (DOCS/audit/03-Multi-Language-Graph-Plan.md §3 WP-L3). Dotted paths use
    "." as the separator (not "::") on purpose: GraphAssembler.
    _resolve_import_target's `as_module = f"{dotted_base}.{name}"` check
    (the "is the imported name itself a submodule" case) hardcodes "."
    between a resolved module path and an imported name — using "." here
    makes that check work for Rust exactly as it already does for Python,
    with zero GraphAssembler changes.

    File->module rules (plan doc): `src/lib.rs`/`src/main.rs` = crate
    root, `foo/mod.rs` == `foo.rs`, and a multi-crate workspace gets one
    namespace prefix per crate (each `Cargo.toml` directory) so same-named
    modules in different crates never collide — `RepoGraphBuilder` builds
    the `crate_roots` map once per build() call via a pre-scan, since
    (unlike Python/TS) Rust's module identity isn't derivable from one
    file's path in isolation.

    v1 limitation (matches WP-L2's "no tsconfig paths" precedent): only
    the standard file-path-based module convention is modeled. `#[path]`
    attribute overrides and non-standard `mod` remapping are not
    supported — a `mod foo;` declaration is assumed to always point at
    `foo.rs`/`foo/mod.rs` next to the declaring file. A bare `use`
    (leading segment neither `crate`/`self`/`super`) is left exactly as
    written (level 0) — an external crate, or a same-named local crate,
    are not disambiguated in v1.
    """

    def __init__(self, crate_roots: Optional[Dict[str, str]] = None):
        # {crate_root_relative_dir: crate_name}; "" is a valid key (repo
        # root itself is a crate root). Falls back to a single implicit
        # crate named "crate" when no Cargo.toml was found anywhere, so
        # single-crate repos/fixtures work without one.
        self._crate_roots = crate_roots or {}

    def _crate_for(self, relative_path: str) -> Tuple[str, str]:
        best_root = ""
        best_name = self._crate_roots.get("", "crate")
        for root, name in self._crate_roots.items():
            if not root:
                continue
            if relative_path == root or relative_path.startswith(root + "/"):
                if len(root) > len(best_root):
                    best_root, best_name = root, name
        return best_root, best_name

    def _module_parts(self, relative_path: str) -> List[str]:
        crate_root, _ = self._crate_for(relative_path)
        within = relative_path
        if crate_root:
            within = within[len(crate_root):].lstrip("/")
        if within.startswith("src/"):
            within = within[len("src/"):]
        stripped = within[:-3] if within.endswith(".rs") else within
        parts = [p for p in stripped.split("/") if p]
        if parts and parts[-1] in ("lib", "main", "mod"):
            parts = parts[:-1]
        return parts

    def dotted_path(self, relative_path: str) -> Optional[str]:
        if not relative_path.endswith(".rs"):
            return None
        _, crate_name = self._crate_for(relative_path)
        segments = [crate_name] + self._module_parts(relative_path)
        return ".".join(segments)

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        if level == 0:
            return base  # bare path: external crate, or same-name local
                          # crate reference — left as-written (v1)
        _, crate_name = self._crate_for(relative_path)
        if level == 1:  # `crate::`
            return f"{crate_name}.{base}" if base else crate_name
        own = self.dotted_path(relative_path) or crate_name
        if level == 2:  # `self::`
            return f"{own}.{base}" if base else own
        # level >= 3: `super::` repeated (level - 2) times
        parts = own.split(".")
        supers = level - 2
        parts = parts[: max(1, len(parts) - supers)]
        prefix = ".".join(parts)
        return f"{prefix}.{base}" if base else prefix


_JAVA_SOURCE_ROOT_PREFIXES = ("src/main/java/", "src/test/java/")


class JavaModuleConvention:
    """WP-L4: package-qualified dotted-path convention for Java `.java`
    files (DOCS/audit/03-Multi-Language-Graph-Plan.md §3 WP-L4). Unlike
    Rust (RustModuleConvention), this needs no repo-wide pre-scan — the
    Maven/Gradle `src/main/java/`-rooted directory layout is a
    near-universal, purely path-derivable convention, so this stays
    stateless per file exactly like PythonModuleConvention.

    Dotted paths use "." (matching Java's own import syntax and, not
    incidentally, the "." GraphAssembler._resolve_import_target already
    hardcodes between a resolved module path and an imported name).

    v1 limitation: only the standard `src/main/java/`-rooted (or
    unrooted, package-directories-from-repo-root) layout is modeled — a
    project with a non-standard source root is not detected."""

    def dotted_path(self, relative_path: str) -> Optional[str]:
        if not relative_path.endswith(".java"):
            return None
        within = relative_path
        for prefix in _JAVA_SOURCE_ROOT_PREFIXES:
            if within.startswith(prefix):
                within = within[len(prefix):]
                break
        stripped = within[: -len(".java")]
        parts = [p for p in stripped.split("/") if p]
        return ".".join(parts) if parts else None

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        # Java imports are always fully qualified — no relative-import
        # concept, so `level` is unused and `base` is already the
        # dotted path to resolve (same shape PythonModuleConvention
        # returns for level=0).
        return base

    def implicit_bindings(
        self, relative_path: str, module_map: Dict[str, str]
    ) -> Dict[str, dict]:
        """Every other same-package file's short class name is usable
        without an import — this is the common case for intra-package
        references in real Java code (e.g. `new Animal(...)` from
        `Caller.java`, same package, no `import` statement). Bound as a
        "symbol" (not "module") binding: the file IS the class (Java's
        one-top-level-type-per-file convention), so the short name
        resolves to the type symbol itself via symbol_table.
        lookup_in_file, exactly like an explicit single-class import."""
        own = self.dotted_path(relative_path)
        if not own or "." not in own:
            return {}
        own_package = own.rsplit(".", 1)[0]
        bindings: Dict[str, dict] = {}
        for dotted, module_cid in module_map.items():
            if module_cid == relative_path or "." not in dotted:
                continue
            package, _, short_name = dotted.rpartition(".")
            if package == own_package:
                bindings[short_name] = {
                    "kind": "symbol", "module_cid": module_cid, "symbol": short_name,
                }
        return bindings


class CompositeModuleConvention:
    """WP-L2: dispatches to a per-suffix ModulePathConvention so one repo
    can mix languages (e.g. Python + TypeScript) in a single ingestion run
    without either language's import resolution corrupting the other's
    module map (DOCS/audit/03-Multi-Language-Graph-Plan.md §3 WP-L2 —
    the necessary, additive alternative to WP-L1's single hardcoded
    PythonModuleConvention)."""

    def __init__(self, by_suffix: Dict[str, ModulePathConvention]):
        self._by_suffix = by_suffix

    def _convention_for(self, relative_path: str) -> Optional[ModulePathConvention]:
        for suffix, convention in self._by_suffix.items():
            if relative_path.endswith(suffix):
                return convention
        return None

    def dotted_path(self, relative_path: str) -> Optional[str]:
        convention = self._convention_for(relative_path)
        return convention.dotted_path(relative_path) if convention else None

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        convention = self._convention_for(relative_path)
        if convention is None:
            return base
        return convention.absolute_import_base(relative_path, base, level)

    def implicit_bindings(
        self, relative_path: str, module_map: Dict[str, str]
    ) -> Dict[str, dict]:
        convention = self._convention_for(relative_path)
        if convention is None:
            return {}
        fn = getattr(convention, "implicit_bindings", None)
        return fn(relative_path, module_map) if fn else {}
