# OCR_SERVICE_API_CONTRACT.md

#DOCS/DESIGN/OCR_SERVICE_API_CONTRACT.md

# OCR Service API Contract

## Purpose

This document defines the **stable API contract** between the ingestion service
and external OCR services.

The contract is:

- Engine-agnostic
- Text-only
- Minimal by design
- Forward-compatible with agentic OCR

---

## Design Principles

- OCR services are **stateless**
- OCR services do **not** perform ingestion logic
- OCR services do **not** persist data
- OCR services return **text only**
- Errors are explicit and deterministic

---

## Transport

- HTTP/JSON (initial)
- gRPC or async messaging may be added later
- Binary image data sent via multipart upload

---

## Endpoint: Extract Text

### `POST /ocr/extract`

#### Request

**Headers**
```

Content-Type: multipart/form-data

````

**Body**
- `file` (required): image binary
- `metadata` (optional, JSON string)

Example metadata:
```json
{
  "language": "en",
  "hint": "document",
  "trace_id": "optional"
}
````

---

#### Response (200 OK)

```json
{
  "text": "Extracted text from image",
  "engine": "paddleocr",
  "confidence": null,
  "warnings": []
}
```

---

#### Response (Empty OCR)

```json
{
  "text": "",
  "engine": "paddleocr",
  "warnings": ["no_text_detected"]
}
```

---

#### Error Responses

| Status | Meaning                  |
| ------ | ------------------------ |
| 400    | Invalid image or request |
| 422    | Unsupported image format |
| 500    | OCR engine failure       |
| 503    | OCR service unavailable  |

Example error:

```json
{
  "error": "OCR_ENGINE_FAILURE",
  "message": "Failed to load OCR model"
}
```

---

## Contract Guarantees

* `text` is always present (string)
* Empty text is a valid response
* No partial ingestion semantics
* No retries implied
* No OCR-specific internals leaked

---

## Ingestion Service Expectations

The ingestion service:

* Treats empty text as ingestion failure
* Does not retry automatically
* Does not interpret warnings
* Does not depend on OCR engine identity

---

## Versioning

* Contract is versioned implicitly via endpoint stability
* Breaking changes require a new endpoint or version prefix

---

## Security Considerations

* OCR services may run in trusted internal networks
* Authentication is optional initially
* Rate limiting handled at service boundary

---

## Future Extensions (Non-Binding)

* Async OCR (`202 Accepted`)
* Streaming OCR
* Bounding boxes (separate endpoint)
* Confidence-aware OCR (optional field)

---

## Summary

This contract ensures OCR remains:

* Replaceable
* Testable
* Scalable
* Independent of ingestion internals
