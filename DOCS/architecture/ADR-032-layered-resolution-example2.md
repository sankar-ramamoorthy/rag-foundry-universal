# ADR-032: Layered Resolution — Example Flow

This example demonstrates the layered resolution model implemented in **MS3-IS1 / MS3-IS2**:

- `RepoGraphBuilder` extracts Python artifacts (MODULE, CLASS, FUNCTION, METHOD, IMPORT, CALL).  
- `SymbolTable` indexes symbol names → canonical IDs.  
- CALLs are resolved using the SymbolTable. Unresolved CALLs are marked `EXTERNAL`.  
- Each CALL carries its `parent_id` for context.

---

## Sample Artifacts Extracted (RepoGraph)

| Artifact Type | Canonical ID / Name                 |
|---------------|-----------------------------------|
| MODULE        | `core/config.py`                   |
| CLASS         | `core/chunks.py#Chunk`            |
| FUNCTION      | `core/config.py#get_settings`      |
| METHOD        | `core/config.py#Settings.__init__`|
| IMPORT        | `from dataclasses import field`   |
| CALL          | `Settings()`                       |

---

## Sample CALL Resolution



CALL Name → Resolved Canonical ID (Parent)

ErrorResponse → api/v1/models.py#ErrorResponse (api/errors.py#register_error_handlers)
exc.errors → EXTERNAL (api/errors.py#register_error_handlers)
JSONResponse → EXTERNAL (api/errors.py#register_error_handlers)
error.model_dump → EXTERNAL (api/errors.py#register_error_handlers)
app.exception_handler → EXTERNAL (api/errors.py#register_error_handlers)
APIRouter → EXTERNAL (api/health.py)
router.get → EXTERNAL (api/health.py#health_check)
field → EXTERNAL (core/chunks.py#Chunk)
SettingsConfigDict → EXTERNAL (core/config.py#Settings)
Settings → core/config.py#Settings (core/config.py#get_settings)
get_settings.cache_clear → EXTERNAL (core/config.py#reset_settings_cache)


> Notes:
> - Resolved CALLs are linked to canonical IDs in the repo.  
> - Unresolved CALLs are marked `EXTERNAL`.  
> - Parent ID helps trace the context where the call occurs.

---

## Summary

- **Total artifacts collected:** 839  
- **Total symbols in table:** 123  
- **Total CALLs:** 372  
- **CALLs resolved using SymbolTable:** 49  
- **CALLs unresolved (EXTERNAL):** 323  

This flow demonstrates the **layered resolution approach**, laying a foundation for future phases (multi-pass resolution, contextual binding, or MS4 enhancements).

