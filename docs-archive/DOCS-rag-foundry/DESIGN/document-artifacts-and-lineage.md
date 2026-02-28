# DOCS\DESIGN\document-artifacts-and-lineage.md
# Document Artifacts, Lineage, and Linking (MS4)

## 1. Overview

This document describes how documents (PDFs, images, text files) are represented, processed, and linked within the **RAG-Ingestion-Engine system** during **Milestone 4 (MS4)**.

MS4 focuses on:

* Structural extraction
* Deterministic association
* Provenance and lineage
* OCR integration for text recovery

**Semantic enrichment** (alt-text, captions, labeling, summaries) is **out of scope** for MS4. That work will be performed in the **Agentic-RAG-Platform**, which operates on MS4 artifacts.

---

## 2. Artifact Model

All extracted units are represented as **`ExtractedArtifact`** objects.

### Artifact Types

| Type  | Description                                                       |
| ----- | ----------------------------------------------------------------- |
| text  | Native text extracted from documents (PDF, image OCR, text files) |
| image | Binary image data extracted from PDFs or uploaded image files     |

### Common Fields

| Field         | Meaning                                    |
| ------------- | ------------------------------------------ |
| `type`        | `"text"` or `"image"`                      |
| `source_file` | Original filename                          |
| `page_number` | 1-based page index                         |
| `order_index` | Deterministic extraction order             |
| `bbox`        | Optional bounding box (for text)           |
| `text`        | Text content (for text artifacts only)     |
| `image_bytes` | Raw image bytes (for image artifacts only) |

Artifacts are **lossless**: nothing is interpreted or summarized. Images are stored as raw bytes; no alt-text or semantic labeling is added.

---

## 3. PDF Extraction (IS1-MS4)

### What Happens

* PDFs are parsed using PyMuPDF (CPU-only).
* Text blocks are extracted with bounding boxes.
* Embedded images are extracted as raw bytes.
* Page number and extraction order are preserved.

### What Does *Not* Happen

* No OCR is run on PDF-embedded images at this stage.
* No captions or alt-text are generated.
* No chunking occurs.

Artifacts are returned as a flat list.

---

## 4. Image–Text Association (IS2-MS4)

This stage introduces **document structure** without semantic interpretation.

### Association Heuristics

Associations are deterministic and reproducible:

* Same-page locality
* Extraction order proximity
* Bounding box overlap (optional)

### Output

A **document graph** is formed:

* Text nodes
* Image nodes
* Edges such as:

  * `image → nearby_text`
  * `image → page`

No captions, summaries, or inferred meaning are added.

---

## 5. Chunking & Lineage (IS3-MS4)

Chunking adapts existing logic to PDF- and image-derived artifacts.

### Chunk Metadata Includes

| Field                  | Description                    |
| ---------------------- | ------------------------------ |
| `source_file`          | PDF or text filename           |
| `page_numbers`         | One or more pages              |
| `artifact_ids`         | References to source artifacts |
| `associated_image_ids` | Linked images                  |
| `chunk_strategy`       | Chunking method used           |
| `ingestion_id`         | Ingestion request ID           |

### Key Principle

Chunks retain **traceability** back to:

* Original file
* Pages
* Text blocks
* Images

Downstream embedding works unchanged.

---

## 6. OCR Integration Hooks (IS4-MS4)

IS4 enables OCR for **PDF-extracted images** using existing OCR adapters (e.g., Tesseract).

### Key Rules

* OCR is applied via the **same abstraction used for uploaded images**.
* No PDF-specific OCR logic is introduced.
* OCR failures are isolated and logged; ingestion continues even if OCR fails.

### Output

OCR text is attached to image artifacts as **recovered text**, not as captions or semantic descriptions.

---

## 7. Captioning Contracts (IS5-MS4)

IS5 defines **contracts and interfaces** for future semantic enrichment.

* These contracts describe how semantic processors (Agentic-RAG-Platform) may consume MS4 artifacts.
* No semantic enrichment is performed within MS4.

Artifacts remain strictly structural and textual; contracts only prepare for:

* Alt-text generators
* Summaries and captions
* Semantic labeling

This is **preparatory only**; all semantic processing is deferred.

---

## 8. Semantic Boundary

MS4 ends at **text recovery and artifact linking**.

Out-of-scope for MS4:

* Alt-text or semantic labels for images
* Captioning or summarization
* Interpretation of embedded captions or metadata

All semantic work occurs **on top of MS4 artifacts** in the **Agentic-RAG-Platform**.

---

## 9. Summary

MS4 establishes a clean, deterministic foundation:

* Extract **text** and **image artifacts**
* Link images to nearby text deterministically
* Chunk artifacts while preserving **lineage and provenance**
* Recover text from images using OCR
* Define **contracts** for semantic enrichment (preparatory only)

The **Agentic-RAG-Platform** is responsible for:

* Alt-text and caption generation
* Semantic embedding strategies
* Cross-modal reasoning

MS4 ensures that downstream systems have **lossless, traceable, and fully linked artifacts** to operate on.
