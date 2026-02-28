#DOCS/DESIGN/OCR_SERVICE_API_CONTRACT.md
## Purpose
Define the minimum stable interface between ingestion and any external OCR engine.

# OCR Service API Contract

## Overview
This document defines the contract between the ingestion service and external OCR services.

The contract is engine-agnostic and supports:
- CPU or GPU OCR
- Synchronous or internally async processing
- Future agentic orchestration

## Transport
- HTTP/JSON (initial)
- RPC or message-based transports are explicitly allowed in future revisions

## Endpoint: POST /ocr/extract

### Request
- Content-Type: multipart/form-data

Fields:
- file: image binary (required)
- metadata: JSON (optional)
  - language
  - engine_hints
  - trace_id
  - ingestion_id

### Response (200)
```
{
  "text": "extracted text",
  "confidence": 0.87,
  "engine": "paddleocr",
  "language": "en"
}
```
Error Responses

400: invalid input

422: unsupported image

500: OCR engine failure

503: engine unavailable

Non-Goals

OCR result validation

Chunking

Embedding

📌 **Important**
- Keep it **small**
- Do not mention PaddleOCR by name in the contract
- The ingestion service treats this as a *best-effort text extractor*

---
