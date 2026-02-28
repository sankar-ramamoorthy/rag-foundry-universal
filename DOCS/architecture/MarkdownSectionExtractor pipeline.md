+------------------------------------+
|         Markdown File (.md)        |
|------------------------------------|
| README.md                          |
| + Introduction                     |
| + Installation                     |
|   - Docker Setup                   |
|   - Manual Setup                   |
| + Usage                            |
+------------------------------------+
               |
               v
+------------------------------------+
|      MarkdownSectionExtractor      |
|------------------------------------|
| 1. Parse file with markdown-it-py  |
| 2. Iterate tokens                  |
| 3. Detect headings and levels      |
| 4. Maintain heading_stack          |
| 5. Slice section text              |
+------------------------------------+
               |
               v
+------------------------------------+
|       SECTION Artifact Nodes       |
|------------------------------------|
| MODULE: README.md                  |
| SECTION: README.md#introduction    |
| SECTION: README.md#installation    |
|   SECTION: README.md#installation.docker_setup |
|   SECTION: README.md#installation.manual_setup |
| SECTION: README.md#usage           |
+------------------------------------+
               |
               v
+------------------------------------+
|      Unified Artifact Graph        |
|------------------------------------|
| Nodes: MODULE, SECTION             |
| Relationships: parent_id links     |
| Metadata: level, lineno, text      |
+------------------------------------+
               |
               v
+------------------------------------+
| SymbolTable (optional future step) |
|------------------------------------|
| symbol_name -> canonical_id mapping|
| Allows linking sections to code    |
+------------------------------------+
