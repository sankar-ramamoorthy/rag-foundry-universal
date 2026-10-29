---
title: "E1 held-out set: review package for the independent second reviewer"
date: 2026-10-28
type: experiment-record
status: approved-manifest-frozen
tags: [held-out, review, adr-054, evidence-delivery]
related:
  - "[Issue #281](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/281)"
  - "[Stratification declaration](/DOCS/evaluations/code-evidence-held-out/stratification.md)"
  - "[Selection record](/DOCS/evaluations/code-evidence-held-out/selection-record.md)"
  - "[Review record](/DOCS/evaluations/code-evidence-held-out/review.md)"
  - "[Frozen manifest](/DOCS/evaluations/code-evidence-held-out/manifest.json)"
---

# E1 held-out set: review package

Roadmap phase: Phase 6, workstream E. Tracked by #281. **Frozen on 2026-10-28.** Round 1:
the reviewer accepted six cases and asked for six rewrites (see the
[review record](/DOCS/evaluations/code-evidence-held-out/review.md)); the reviewer then approved the
rewrites and the freeze (see the review record).

## How the cases were produced

- **Slots, by deterministic rule** (declared before authoring, applied mechanically): per
  repository, **A** = longest module-level function that is not a purely declarative option
  builder (long, spread); **B** = module-level function with the largest signature (>= 8 lines)
  that calls a same-file function (multi-function); **C** = module-level function under 40 lines
  with the most distinct control-flow kinds (short, narrow); **D** = module-level function of
  40-119 lines with the most distinct control-flow kinds, not already used (natural-language
  question). No method was chosen.
- **Not used:** oracle byte costs (never computed), any retrieval, control or candidate output
  (none exists for these repositories), expected results.
- **Mechanical checks** (`scripts/held_out_manifest_build.py`, re-run after round 1): every
  expression is a verbatim substring of its function and its line occurs exactly once; 4-5
  operations and 3-4 dependencies per case; quotas below.
- **Source text** is the function as found in the pinned clone (first decorator to last line),
  not the stored `DocumentNode.text`; that comparison happens at ingestion time.

## Quota check (declaration section 6; unchanged by round 1)

| Quota | Required | Measured |
| --- | --- | --- |
| Cases / repositories / per repository | 12 / 3 / 4 each | 12 / 3 / hatch=4, pdfminer.six=4, werkzeug=4 |
| Q1 multi-function with a long signature | >= 2 | 3 |
| Q2 long function, wide witness spread | >= 3 | 3 |
| Q3 short function, narrow witnesses | >= 2 | 4 |
| Q4 witnesses in an else/elif | >= 3 | 12 |
| Q4 witnesses in try/except/finally | >= 2 | 9 |
| Q4 witnesses in a loop or with | >= 2 | 10 |
| Q5 methods as the key function | <= 2 | 0 |
| Q6 natural-language questions | >= 4 | 4 |

Per repository, cases counted in Q1 / Q2 / Q3 (each <= 2, at least one in total): pypa/hatch: 1 / 1 / 1; pdfminer/pdfminer.six: 1 / 1 / 2; pallets/werkzeug: 1 / 1 / 1.

## Evaluation limitations (recorded; selected functions are not replaced because of them)

- Concentration: three of pypa/hatch's four cases (H1, H2, H4) are `hatch env` click commands with decorator-heavy signatures; the fourth (H3) is a release script. Hatch results characterise those commands, not the repository broadly.
- Overlap: P2 and P4 both live in tools/dumppdf.py and both involve dumpxml, so they are not independent observations.
- Narrow coverage: three of pdfminer.six's four cases are command-line utilities under tools/, not library modules.
- Training-data exposure: pallets/werkzeug is very likely well represented in model training data despite its star count.
- Source text is the pinned function source, not the stored DocumentNode.text; that comparison happens at ingestion time.

## The 12 cases

Each operation and dependency carries *needed for*, the clause of the question that makes it necessary, where the item was part of a rewrite. File line numbers are in the pinned source file.

### H1  (pypa/hatch, slot A, explicit question) - REVISED - approved by the reviewer

**Functions:** `src/hatch/cli/env/show.py#show`

**Strata:** primary function 196 lines, signature 16 lines; largest witness spread 172 lines; 1 function(s) needed; witness contexts: else_elif, loop_with, try.

**What changed (reviewer: "feature normalization and invalid-dependency handling must be explicitly relevant"):** Question now asks explicitly about feature-name and dependency normalization, including invalid dependency strings. Required evidence unchanged; a needed_for mapping was added. The question was then tightened to say the normalization applies to matrix environments, which is what the code does.

**Question:** Explain how the `hatch env show` command, implemented by `show` in `src/hatch/cli/env/show.py`, works: which environments it lists (standalone, matrix and internal ones, and how requested names filter them), how the JSON and internal-environment options change what it does, how the features and dependencies of matrix environments are normalized for display (including what happens to a dependency string that is not a valid requirement), and how it renders its result.

**Required operations:**

1. JSON mode covers regular and internal environments - in `show`: `for environments in (app.project.config.envs, app.project.config.internal_envs):` (file line 36). *Needed for:* which environments it lists; how the JSON option changes what it does.
2. JSON mode prints one compact JSON document - in `show`: `app.display(json.dumps(contextual_config, separators=(",", ":")))` (file line 70). *Needed for:* how the JSON option changes what it does.
3. Table mode chooses the internal or regular environment sets - in `show`: `target_standalone_envs = app.project.config.internal_envs` (file line 77); `target_standalone_envs = app.project.config.envs` (file line 80). *Needed for:* how the internal-environment option changes what it does.
4. Unknown requested names abort the command - in `show`: `app.abort(f"Environment `{env_name}` is not defined by project config")` (file line 85). *Needed for:* how requested names filter the listing.
5. Output is a Standalone table and a Matrices table with optional titles - in `show`: `"" if hide_titles else "Standalone",` (file line 201); `"" if hide_titles else "Matrices",` (file line 208). *Needed for:* how it renders its result.

**Required dependency expressions:**

1. Matrix member environments are left out of the standalone list unless names were given - in `show`: `matrix_envs.update(matrix_data["envs"])` (file line 101); `if env_names or env_name not in matrix_envs` (file line 161). *Needed for:* how matrix and standalone environments are listed.
2. A requested-name filter applies to matrices and to standalone environments - in `show`: `if env_names and matrix_name not in env_names:` (file line 103); `if env_names and env_name not in env_names:` (file line 164). *Needed for:* how requested names filter them.
3. Feature names are normalized only when ambiguous features are not allowed - in `show`: `if app.project.metadata.hatch.metadata.allow_ambiguous_features:` (file line 112); `sorted({normalize_project_name(f) for f in config["features"]})` (file line 116). *Needed for:* how the features of matrix environments are normalized for display.
4. Invalid dependency strings are kept as written and valid ones are normalized - in `show`: `except InvalidDependencyError:` (file line 129); `normalized_dependencies.add(dependency)` (file line 130); `normalized_dependencies.add(get_normalized_dependency(req))` (file line 132). *Needed for:* how the dependencies of matrix environments are normalized, including invalid ones.

### H2  (pypa/hatch, slot B, explicit question) - accepted, unchanged

**Functions:** `src/hatch/cli/env/lock.py#lock`; `src/hatch/cli/env/lock.py#run_lock_workflow`

**Strata:** primary function 112 lines, signature 12 lines; largest witness spread 37 lines; 2 function(s) needed; witness contexts: else_elif, loop_with, try.

**Question:** Explain how `hatch env lock`, implemented by `lock` in `src/hatch/cli/env/lock.py`, decides which environments to lock, and how the shared `run_lock_workflow` it hands off to treats incompatible environments, chooses where each lockfile is written, and behaves in check mode.

**Required operations:**

1. The two export options are mutually exclusive - in `lock`: `app.abort("Cannot use both `--export` and `--export-all`")` (file line 217).
2. A named environment is expanded (a matrix name expands to its members) - in `lock`: `env_names = app.project.expand_environments(env_name)` (file line 224).
3. With no arguments and nothing marked locked the command aborts - in `lock`: `app.abort("No environments are configured with `locked = true`")` (file line 241).
4. An incompatible environment is skipped or aborts the run - in `run_lock_workflow`: `incompatible[env] = str(e)` (file line 106); `app.abort(f"Environment `{env}` is incompatible: {e}")` (file line 109).
5. The lockfile path is the export path, a per-environment file under the export-all directory, or the default - in `run_lock_workflow`: `filename = "pylock.toml" if environment.name == "default" else f"pylock.{safe_name}.toml"` (file line 122); `output_path = Path(export_all_path) / filename` (file line 123); `output_path = resolve_lockfile_path(environment)` (file line 125).

**Required dependency expressions:**

1. Whether incompatible environments are tolerated depends on how the environment was selected and is passed down - in `lock`: `skip_incompatible = env_name in app.project.config.matrices` (file line 228); `skip_incompatible_envs=skip_incompatible,` (file line 254).
2. An explicitly named environment that is not marked locked is refused unless an export option is given - in `run_lock_workflow`: `if explicit_env is not None and not environment.locked and not export_path and not export_all_path:` (file line 111).
3. Environments that resolve to the same lockfile path are grouped and merged into one lock - in `run_lock_workflow`: `lockfile_groups.setdefault(output_path, []).append(env)` (file line 134); `environment, merged_deps, merged_extras, merged_groups, display_name = merge_environment_lock_inputs(` (file line 137).
4. In check mode a missing lockfile aborts; otherwise environments with nothing to lock are skipped with a warning - in `run_lock_workflow`: `app.abort(f"Lockfile does not exist: {output_path}")` (file line 129); `elif not environment_has_lock_inputs(environment):` (file line 130); `app.display_warning(f"Environment `{env}` has no dependencies to lock")` (file line 131).

### H3  (pypa/hatch, slot C, explicit question) - REVISED - approved by the reviewer

**Functions:** `release/unix/make_scripts_portable.py#main`

**Strata:** primary function 37 lines, signature 1 lines; largest witness spread 24 lines; 1 function(s) needed; witness contexts: else_elif, loop_with.

**What changed (reviewer: "clarify file selection and modification versus preservation"):** Question now asks separately which entries are considered, which files are modified (and how) and which are preserved or not written back. Operation names and a needed_for mapping state the same three roles. Expressions unchanged. On re-reading the code the question was made exact: a file whose first line points at another interpreter is rewritten (header copied through, leading blank lines dropped), not left untouched; only non-files, binaries and no-content files are left untouched on disk.

**Question:** In `release/unix/make_scripts_portable.py`, explain what `main` does with each entry of the interpreter's scripts directory so the scripts keep working when the Python distribution is moved: which entries it considers at all; which files it rewrites with a new header and exactly how (including what happens to blank lines at the top of a file); which files it rewrites but keeps the original first line for (a first line that points at another interpreter); and which entries it leaves untouched on disk (non-files, binaries, and anything that produces no content).

**Required operations:**

1. Selection: only regular files are considered; other directory entries are skipped (left untouched) - in `main`: `if not script.is_file():` (file line 17). *Needed for:* which entries it considers at all; non-files are left untouched.
2. Modification: leading blank lines are ignored, so they are not written back to a rewritten file - in `main`: `if not line.strip():` (file line 24). *Needed for:* what happens to blank lines at the top of a file.
3. Left untouched: a file whose first non-blank line is not a comment is treated as a binary and yields no content - in `main`: `if not line.startswith(b"#"):` (file line 28). *Needed for:* which entries it leaves untouched on disk (binaries).
4. Modification: a header naming this interpreter is replaced by the portable shebang - in `main`: `data.write(portable_shebang if executable == interpreter else line)` (file line 33). *Needed for:* which files it modifies and how.
5. Left untouched: a file that produced no content is not written back - in `main`: `if not contents:` (file line 41). *Needed for:* which entries it leaves untouched on disk (no content).

**Required dependency expressions:**

1. Only first lines naming a path under the interpreter's own directory are examined; any other first line is copied through unchanged and the file is still rewritten - in `main`: `if line.startswith(b"#!%s" % interpreter.parent):` (file line 31); `data.write(line)` (file line 35). *Needed for:* which files it rewrites but keeps the original first line for.
2. The executable named in the header is resolved and compared with this interpreter before the header is replaced - in `main`: `executable = Path(line[2:].rstrip().decode()).resolve()` (file line 32). *Needed for:* when a file is modified.
3. The rest of the file after the header is appended unchanged, and the result is collected before the emptiness check - in `main`: `data.write(f.read())` (file line 37); `contents = data.getvalue()` (file line 40). *Needed for:* what happens to the rest of a modified file.

### H4  (pypa/hatch, slot D, natural question) - accepted, unchanged

**Functions:** `src/hatch/cli/env/run.py#run`

**Strata:** primary function 111 lines, signature 22 lines; largest witness spread 49 lines; 1 function(s) needed; witness contexts: else_elif, loop_with, try.

**Earlier correction:** Question rewritten before review to remove the CLI command name (the symbol's name) from a natural-language question. No expression changed.

**Question:** When I execute a command in project environments with hatch and combine environment names, matrix include/exclude variables and a JSON filter, how does hatch decide which environments the command is actually executed in, and in which situations does it refuse to continue?

**Required operations:**

1. A duplicated included matrix variable aborts - in `run`: `app.abort(f"Duplicate included variable: {e}")` (file line 85).
2. With no environment named the current default environment is used - in `run`: `env_names = (app.env,)` (file line 97).
3. Named environments are de-duplicated while keeping their order - in `run`: `ordered_env_names = list(dict.fromkeys(env_names))` (file line 108).
4. A matrix name expands to its environments, narrowed by the include and exclude variables - in `run`: `environments.extend(select_environments(env_data, included_variables, excluded_variables))` (file line 119).
5. If nothing was selected the command aborts - in `run`: `app.abort("No environments were selected")` (file line 133).

**Required dependency expressions:**

1. The special system environment is defined on the fly when it is requested - in `run`: `elif "system" in env_names:` (file line 98); `"type": "system",` (file line 101).
2. A matrix with no variables defined aborts - in `run`: `app.abort(f"No variables defined for matrix: {env_name}")` (file line 117).
3. A JSON filter must be a mapping and then replaces the selection - in `run`: `app.abort("The --filter/-f option must be a JSON mapping")` (file line 128); `environments[:] = filter_environments(project.config.envs, filter_data)` (file line 130).
4. Include/exclude variables are rejected when no matrix was selected - in `run`: `elif not matrix_selected and (included_variables or excluded_variables):` (file line 134).

### P1  (pdfminer/pdfminer.six, slot A, explicit question) - REVISED - approved by the reviewer

**Functions:** `pdfminer/high_level.py#extract_text_to_fp`

**Strata:** primary function 120 lines, signature 18 lines; largest witness spread 65 lines; 1 function(s) needed; witness contexts: else_elif, loop_with.

**What changed (reviewer: "remove incidental debug/image-writer requirements or make them explicitly relevant"):** Removed the debug-logging and image-writer operations. The question no longer asks 'which options it honours'; it asks about device choice, stream and resource-manager preparation, scale/layout/rotation and page processing. Rotation and the stdout buffer moved from dependencies to operations; a tag-extractor binary-stream dependency was added so there are 5 operations and 3 dependencies.

**Question:** Explain how `extract_text_to_fp` in `pdfminer/high_level.py` converts a PDF into output: how it chooses the output device for each output type and what happens for an unsupported type, how it prepares the output stream and the resource manager (including caching), how the scale, layout and rotation options take effect, and how it processes the pages and finishes.

**Required operations:**

1. The output device is a text, XML, HTML or hOCR converter depending on the output type - in `extract_text_to_fp`: `device = TextConverter(` (file line 86); `device = XMLConverter(` (file line 95); `device = HTMLConverter(` (file line 105); `device = HOCRConverter(` (file line 116). *Needed for:* how it chooses the output device for each output type.
2. An unsupported output type raises a value error - in `extract_text_to_fp`: `raise PDFValueError(msg)` (file line 130). *Needed for:* what happens for an unsupported type.
3. Standard output is replaced by its binary buffer when a non-text output type is written to it - in `extract_text_to_fp`: `if output_type != "text" and outfp == sys.stdout:` (file line 82); `outfp = sys.stdout.buffer` (file line 83). *Needed for:* how it prepares the output stream.
4. The requested rotation is added to each page's own rotation modulo 360 - in `extract_text_to_fp`: `page.rotate = (page.rotate + rotation) % 360` (file line 141). *Needed for:* how the rotation option takes effect.
5. Every selected page is interpreted and the device is closed at the end - in `extract_text_to_fp`: `interpreter.process_page(page)` (file line 142); `device.close()` (file line 144). *Needed for:* how it processes the pages and finishes.

**Required dependency expressions:**

1. Caching is controlled by one flag that feeds both the resource manager and the page loader - in `extract_text_to_fp`: `rsrcmgr = PDFResourceManager(caching=not disable_caching)` (file line 79); `caching=not disable_caching,` (file line 139). *Needed for:* how it prepares the resource manager (including caching).
2. Scale and layout mode only influence the HTML converter - in `extract_text_to_fp`: `scale=scale,` (file line 109); `layoutmode=layoutmode,` (file line 110). *Needed for:* how the scale and layout options take effect.
3. For tag output the stream is cast to a binary stream before it is given to the tag extractor - in `extract_text_to_fp`: `device = TagExtractor(rsrcmgr, cast(BinaryIO, outfp), codec=codec)` (file line 126). *Needed for:* how it prepares the output stream (binary stream for tag output).

### P2  (pdfminer/pdfminer.six, slot B, explicit question) - accepted, unchanged

**Functions:** `tools/dumppdf.py#dumpallobjs`; `tools/dumppdf.py#dumppdf`; `tools/dumppdf.py#dumptrailers`

**Strata:** primary function 33 lines, signature 11 lines; largest witness spread 16 lines; 3 function(s) needed; witness contexts: else_elif, loop_with, try.

**Question:** Explain how `dumppdf` in `tools/dumppdf.py` decides what to dump from a PDF file: how object ids, page numbers, the dump-all option and the codec interact, what `dumpallobjs` and `dumptrailers` contribute, and how fallback cross-reference tables and missing objects are handled.

**Required operations:**

1. Requested object ids are fetched from the document and dumped as XML - in `dumppdf`: `obj = doc.getobj(objid)` (file line 266).
2. For selected pages a codec dumps the page content streams, otherwise the page attributes - in `dumppdf`: `obj = stream_value(obj)` (file line 273); `dumpxml(outfp, page.attrs)` (file line 276).
3. The dump-all option dumps every object in the document - in `dumppdf`: `dumpallobjs(outfp, doc, codec, show_fallback_xref)` (file line 278).
4. With nothing requested only the trailers are dumped - in `dumppdf`: `if (not objids) and (not pagenos) and (not dumpall):` (file line 279); `dumptrailers(outfp, doc, show_fallback_xref)` (file line 280).
5. The full dump skips objects it has already seen and reports objects that cannot be found - in `dumpallobjs`: `if objid in visited:` (file line 132); `except PDFObjectNotFound as e:` (file line 142).

**Required dependency expressions:**

1. A trailing newline is written unless the codec is raw or binary - in `dumppdf`: `if codec not in ("raw", "binary"):` (file line 281).
2. Trailers of fallback cross-reference tables are shown only on request - in `dumptrailers`: `if not isinstance(xref, PDFXRefFallback) or show_fallback_xref:` (file line 108).
3. A warning is logged when the file has no real cross-reference table and fallback tables are hidden - in `dumptrailers`: `no_xrefs = all(isinstance(xref, PDFXRefFallback) for xref in doc.xrefs)` (file line 112); `if no_xrefs and not show_fallback_xref:` (file line 113); `logger.warning(msg)` (file line 119).
4. The full dump is wrapped in a pdf element and ends with the trailers - in `dumpallobjs`: `out.write("<pdf>")` (file line 129); `dumptrailers(out, doc, show_fallback_xref)` (file line 144); `out.write("</pdf>")` (file line 145).

### P3  (pdfminer/pdfminer.six, slot C, explicit question) - accepted, unchanged

**Functions:** `tools/pdf2txt.py#extract_text`

**Strata:** primary function 39 lines, signature 18 lines; largest witness spread 16 lines; 1 function(s) needed; witness contexts: else_elif, loop_with.

**Question:** In `tools/pdf2txt.py`, explain how `extract_text` drives the conversion: what it requires from the caller, how the output type is decided from the output file name, and how its behaviour differs between writing to standard output and writing to a file.

**Required operations:**

1. Calling it without input files is an error - in `extract_text`: `raise PDFValueError("Must provide files to work upon!")` (file line 50).
2. The output type is overridden by the output file's extension - in `extract_text`: `for override, alttype in OUTPUT_TYPES:` (file line 53); `output_type = alttype` (file line 55).
3. Writing to standard output uses the stdout stream - in `extract_text`: `outfp: AnyIO = sys.stdout` (file line 58).
4. Standard output forces the UTF-8 codec - in `extract_text`: `codec = "utf-8"` (file line 60).
5. Writing to a file opens the output in binary mode - in `extract_text`: `with open(outfile, "wb") as outfp:` (file line 66).

**Required dependency expressions:**

1. The extension override only applies when the default text type is in use and the output is a file - in `extract_text`: `if output_type == "text" and outfile != "-":` (file line 52).
2. The override is chosen by matching the file name suffix - in `extract_text`: `if outfile.endswith(override):` (file line 54).
3. A dash as the output file name selects the standard output path - in `extract_text`: `if outfile == "-":` (file line 57).
4. The codec is forced only when standard output reports an encoding - in `extract_text`: `if sys.stdout.encoding is not None:` (file line 59).

### P4  (pdfminer/pdfminer.six, slot D, natural question) - accepted, unchanged

**Functions:** `tools/dumppdf.py#dumpoutline`

**Strata:** primary function 57 lines, signature 10 lines; largest witness spread 39 lines; 1 function(s) needed; witness contexts: else_elif, loop_with, try.

**Question:** How does pdfminer's command-line dump tool print a document's outline (its bookmarks): how does it map each entry to a page number, how does it deal with destinations given as names, references or actions, and what happens when the document has no outline?

**Required operations:**

1. A table from page object ids to page numbers is built first - in `dumpoutline`: `for (pageno, page) in enumerate(PDFPage.create_pages(doc), 1)` (file line 163).
2. Named destinations are looked up in the document, whether given as a string or a literal - in `dumpoutline`: `dest = resolve1(doc.get_dest(dest))` (file line 168); `dest = resolve1(doc.get_dest(dest.name))` (file line 170).
3. A dictionary destination is unwrapped to its D entry - in `dumpoutline`: `dest = dest["D"]` (file line 172).
4. A GoTo action supplies the destination when there is no direct one - in `dumpoutline`: `if subtype and repr(subtype) == "/'GoTo'" and action.get("D"):` (file line 189).
5. A document without an outline is handled silently - in `dumpoutline`: `except PDFNoOutlines:` (file line 202).

**Required dependency expressions:**

1. Actions are only consulted when an entry has no direct destination - in `dumpoutline`: `elif a:` (file line 185).
2. Indirect object references are resolved to the object they point to - in `dumpoutline`: `if isinstance(dest, PDFObjRef):` (file line 173); `dest = dest.resolve()` (file line 174).
3. The destination and the page number are written only when they were found - in `dumpoutline`: `if dest is not None:` (file line 194); `if pageno is not None:` (file line 198).
4. Titles are escaped before they are written into the XML attribute - in `dumpoutline`: `s = escape(title)` (file line 192).

### W1  (pallets/werkzeug, slot A, natural question) - accepted, unchanged

**Functions:** `src/werkzeug/utils.py#send_file`

**Strata:** primary function 246 lines, signature 16 lines; largest witness spread 129 lines; 1 function(s) needed; witness contexts: else_elif, try.

**Question:** In Werkzeug, when a file or a path is served back to the client as a WSGI response, how are the download name and content type worked out, which headers are produced for downloading, caching and conditional or range requests, and which invalid inputs cause errors?

**Required operations:**

1. A text-mode file object is rejected - in `send_file`: `raise ValueError("File must be in binary mode, or 'BytesIO'.")` (file line 430).
2. A non-ASCII download name produces both a plain and an RFC 5987 encoded filename - in `send_file`: `names = {"filename": simple, "filename*": f"UTF-8''{quoted}"}` (file line 478).
3. An attachment without any name is rejected - in `send_file`: `"No name provided for attachment. Either pass 'download_name', or"` (file line 484).
4. X-Sendfile mode hands the path to the server and empties the body - in `send_file`: `rv.headers["X-Sendfile"] = path` (file line 500).
5. Conditional and range handling is applied, and the response is closed if it fails - in `send_file`: `rv.apply_conditions(request)` (file line 545); `rv.apply_range(request)` (file line 546); `rv.close()` (file line 548).

**Required dependency expressions:**

1. A content encoding header is only sent when the file is not an attachment - in `send_file`: `mimetype, encoding = mimetypes.guess_type(download_name)` (file line 460); `if encoding is not None and not as_attachment:` (file line 467).
2. For a path the size and modification time come from stat; for a file object they come from seeking, falling back to its file descriptor - in `send_file`: `stat = os.stat(path)` (file line 419); `size = file.seek(0, os.SEEK_END)` (file line 436); `fileno = file.fileno()` (file line 441); `except OSError:` (file line 442).
3. Responses default to no-cache; a positive max age makes them public and sets an expiry - in `send_file`: `cache_control.no_cache = True` (file line 510); `cache_control.public = True` (file line 520); `rv.expires = int(time() + max_age)` (file line 523).
4. An ETag given as a string is used as is; otherwise it is built from modification time and size - in `send_file`: `if isinstance(etag, str):` (file line 527); `rv.etag = "-".join(parts)` (file line 541).

### W2  (pallets/werkzeug, slot B, explicit question) - REVISED - approved by the reviewer

**Functions:** `src/werkzeug/serving.py#is_running_from_reloader`; `src/werkzeug/serving.py#make_server`; `src/werkzeug/serving.py#run_simple`

**Strata:** primary function 168 lines, signature 18 lines; largest witness spread 54 lines; 3 function(s) needed; witness contexts: else_elif, try.

**What changed (reviewer: "resolve the startup-banner dependency"):** Removed the startup-banner dependency. Its governing condition (`if not is_running_from_reloader():`) occurs twice in the function, so it cannot be evidenced by a single-occurrence expression, and the question did not ask about the banner. Added two dependencies the question does ask about: which hosts the debugger trusts (the wildcard condition) and making the socket inheritable. The question now says so explicitly.

**Question:** Explain how `run_simple` in `src/werkzeug/serving.py` starts the development server: how it validates its arguments, how it wraps the application for static files and for the debugger (including which hosts the debugger trusts), how it picks the kind of server to build through `make_server`, and how it behaves differently when the reloader is enabled or when it is itself running inside the reloader (including how the listening socket is handed over).

**Required operations:**

1. The port must be an integer - in `run_simple`: `raise TypeError("port must be an integer")` (file line 1072). *Needed for:* how it validates its arguments.
2. Static file mappings wrap the application in shared-data middleware - in `run_simple`: `application = SharedDataMiddleware(application, static_files)` (file line 1077). *Needed for:* how it wraps the application for static files.
3. The debugger wraps the application and the chosen hostname is added to its trusted hosts - in `run_simple`: `application = DebuggedApplication(application, evalex=use_evalex)` (file line 1082); `application.trusted_hosts.append(hostname)` (file line 1087). *Needed for:* how it wraps the application for the debugger.
4. A threaded and a multi-process server cannot be combined - in `make_server`: `raise ValueError("Cannot have a multi-thread and multi-process server.")` (file line 926). *Needed for:* how it picks the kind of server (invalid combination).
5. The server class is threaded, forking or plain depending on the arguments - in `make_server`: `return ThreadedWSGIServer(` (file line 929); `return ForkingWSGIServer(` (file line 934); `return BaseWSGIServer(` (file line 945). *Needed for:* how it picks the kind of server.

**Required dependency expressions:**

1. The hostname is added to the debugger's trusted hosts unless it is a wildcard address - in `run_simple`: `if hostname not in {"0.0.0.0", "[::]"}:` (file line 1086). *Needed for:* which hosts the debugger trusts.
2. A process running inside the reloader reuses the listening socket handed down through an environment variable; the parent makes the socket inheritable and publishes it - in `run_simple`: `fd = int(os.environ["WERKZEUG_SERVER_FD"])` (file line 1092); `srv.socket.set_inheritable(True)` (file line 1105); `os.environ["WERKZEUG_SERVER_FD"] = str(srv.fileno())` (file line 1106). *Needed for:* how the listening socket is handed over.
3. Whether the process is a reloader child is decided from an environment variable - in `is_running_from_reloader`: `return os.environ.get("WERKZEUG_RUN_MAIN") == "true"` (file line 956). *Needed for:* when it is itself running inside the reloader.
4. With the reloader on the server runs under it and is always closed; otherwise it simply serves forever - in `run_simple`: `run_with_reloader(` (file line 1116); `srv.server_close()` (file line 1124); `srv.serve_forever()` (file line 1126). *Needed for:* how it behaves when the reloader is enabled.

### W3  (pallets/werkzeug, slot C, explicit question) - REVISED - approved by the reviewer

**Functions:** `src/werkzeug/_reloader.py#run_with_reloader`

**Strata:** primary function 30 lines, signature 7 lines; largest witness spread 18 lines; 1 function(s) needed; witness contexts: else_elif, loop_with, try.

**What changed (reviewer: "resolve the terminal-echo dependency"):** Removed the `ensure_echo_on()` dependency. The function only calls a helper whose behaviour (restoring terminal echo) is not visible in `run_with_reloader`, and the question does not ask about it. Three dependencies and five operations remain; every expression is otherwise unchanged and the witness window is still 18 lines.

**Question:** In `src/werkzeug/_reloader.py`, explain how `run_with_reloader` runs an application under the reloader: how the reloader implementation is chosen, how the process behaves differently when it is the reloaded child versus the original parent, how the application and the reloader loop run together, and how it exits on a termination signal and on Ctrl+C.

**Required operations:**

1. A termination signal makes the process exit cleanly - in `run_with_reloader`: `signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))` (file line 400). *Needed for:* how it exits on a termination signal.
2. The reloader implementation is looked up by the requested type - in `run_with_reloader`: `reloader = reloader_loops[reloader_type](` (file line 401). *Needed for:* how the reloader implementation is chosen.
3. In the child the application runs in a daemon thread - in `run_with_reloader`: `t = threading.Thread(target=main_func, args=())` (file line 408); `t.daemon = True` (file line 409). *Needed for:* how the application runs in the reloaded child.
4. The reloader update loop runs alongside the application thread - in `run_with_reloader`: `reloader.run()` (file line 415). *Needed for:* how the application and the reloader loop run together.
5. The original parent process restarts itself under the reloader and exits with its status - in `run_with_reloader`: `sys.exit(reloader.restart_with_reloader())` (file line 417). *Needed for:* how it behaves as the original parent.

**Required dependency expressions:**

1. Child versus parent is decided from an environment variable - in `run_with_reloader`: `if os.environ.get("WERKZEUG_RUN_MAIN") == "true":` (file line 406). *Needed for:* how the process behaves as the reloaded child versus the original parent.
2. The application thread is started only after the reloader context has been entered - in `run_with_reloader`: `with reloader:` (file line 413); `t.start()` (file line 414). *Needed for:* how the application and the reloader loop run together.
3. Ctrl+C ends the run quietly - in `run_with_reloader`: `except KeyboardInterrupt:` (file line 418). *Needed for:* how it exits on Ctrl+C.

### W4  (pallets/werkzeug, slot D, natural question) - REVISED - approved by the reviewer

**Functions:** `src/werkzeug/test.py#run_wsgi_app`

**Strata:** primary function 74 lines, signature 3 lines; largest witness spread 36 lines; 1 function(s) needed; witness contexts: else_elif, loop_with, try.

**What changed (reviewer: "resolve the environment-copy requirement"):** Removed the `environ = _get_environ(environ).copy()` operation: the question does not ask whether the caller's environment is protected. Four operations and four dependencies remain; the question is unchanged.

**Question:** How does Werkzeug's test machinery execute a WSGI application and return its response: what happens when the application raises through start_response or uses the old write callable, how is the response iterator handled and closed, and what changes when the caller asks for the output to be buffered?

**Required operations:**

1. An exc_info passed to start_response is re-raised with its traceback - in `run_wsgi_app`: `raise exc_info[1].with_traceback(exc_info[2])` (file line 1268). *Needed for:* what happens when the application raises through start_response.
2. The write callable returned by start_response appends to a buffer - in `run_wsgi_app`: `return buffer.append` (file line 1273). *Needed for:* what happens when the application uses the old write callable.
3. Buffered mode turns the iterator into a list and closes the application early - in `run_wsgi_app`: `app_iter = list(app_iter)` (file line 1283); `close_func()` (file line 1286). *Needed for:* what changes when the output is buffered.
4. Unbuffered mode iterates only until a response has started and chains what was already read - in `run_wsgi_app`: `if response is not None:` (file line 1294); `app_iter = chain(buffer, app_iter)` (file line 1298). *Needed for:* how the response iterator is handled.

**Required dependency expressions:**

1. The application's close callable is discovered up front - in `run_wsgi_app`: `close_func = getattr(app_rv, "close", None)` (file line 1276). *Needed for:* how the iterator is closed.
2. A close callable is restored on the chained iterator only when the iterator was replaced - in `run_wsgi_app`: `if close_func is not None and app_iter is not app_rv:` (file line 1300); `app_iter = ClosingIterator(app_iter, close_func)` (file line 1301). *Needed for:* how the iterator is closed.
3. The exc_info reference is always cleared after re-raising - in `run_wsgi_app`: `exc_info = None` (file line 1270). *Needed for:* what happens when the application raises through start_response.
4. The status and headers come from the recorded response and are returned with the iterator - in `run_wsgi_app`: `status, headers = response` (file line 1303); `return app_iter, status, Headers(headers)` (file line 1304). *Needed for:* how the response is returned.

## Reviewer checklist (declaration section 9)

(a) the question is answerable from the pinned source as written; (b) every expression is
verbatim, unambiguous and necessary; (c) the operations and dependencies are genuinely required
for the answer, not incidental; (d) the question does not leak an expression or the answer;
(e) the stratum labels are correct; (f) license and attribution are recorded (`licenses/`).

The reviewer approved the six revisions and the freeze on 2026-10-28; see the review record.
