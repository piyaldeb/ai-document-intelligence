# Database schema

PostgreSQL 16 with the `vector` (pgvector) and `pg_trgm` extensions. The schema is managed by Alembic (`backend/alembic/versions/0001_initial_schema.py`); the full DDL generated from a live database is in [`schema.sql`](schema.sql).

```mermaid
erDiagram
    documents ||--o{ document_pages : "has pages / sheets"
    documents ||--o{ invoices : "contains"
    documents ||--o{ validation_issues : "document-level issues"
    documents ||--o{ processing_events : "processing history"
    documents ||--o{ chunks : "search index"
    documents |o--o{ documents : "duplicate_of"
    invoices ||--o{ line_items : "has"
    invoices ||--o{ validation_issues : "has"
    invoices ||--o{ corrections : "audit trail"
    invoices |o--o{ chunks : "summary chunk"
    reconciliations ||--o{ reconciliation_items : "has"
    documents ||--o{ reconciliations : "left / right"
    invoices |o--o{ reconciliation_items : "left / right"

    documents {
        uuid id PK
        text original_filename
        varchar file_type "pdf|image|xlsx|xls|csv"
        varchar mime_type
        bigint size_bytes
        varchar sha256 "indexed, duplicate-file detection"
        text storage_path "UUID name on the storage volume"
        varchar status "queued|processing|completed|needs_review|failed"
        varchar stage "current pipeline stage"
        int progress "0..100"
        int page_count
        int invoice_count
        varchar error_code
        text error_message
        int attempts
        uuid duplicate_of_id FK
        varchar extraction_provider "anthropic|rules"
        jsonb meta "ocr_pages, sheets, warnings, repaired"
        timestamptz created_at
        timestamptz processing_started_at
        timestamptz processing_finished_at
        int processing_ms
    }
    document_pages {
        bigint id PK
        uuid document_id FK
        int page_number "unique per document"
        text sheet_name
        varchar method "text_layer|ocr|spreadsheet"
        text text "layout-preserving extracted text"
        float ocr_confidence
        int char_count
        jsonb warnings
        tsvector tsv "GENERATED, GIN index"
    }
    invoices {
        uuid id PK
        uuid document_id FK
        int sequence
        jsonb source_ref "pages / sheet / rows"
        int page_start
        int page_end
        text invoice_number
        text invoice_number_norm "duplicate key"
        date invoice_date
        text supplier_name "trigram index"
        text supplier_norm "duplicate key"
        text customer_name
        numeric subtotal "18,2"
        numeric tax "18,2"
        numeric total "18,2"
        varchar currency "ISO 4217"
        jsonb field_confidence
        varchar extraction_method "anthropic|rules|spreadsheet"
        varchar model
        jsonb raw_extraction "evidence, rejected values, notes"
        text source_text
        varchar review_status "ok|needs_review|approved"
        bool needs_review
        int error_count
        int warning_count
        tsvector tsv "GENERATED, GIN index"
    }
    line_items {
        bigint id PK
        uuid invoice_id FK
        int position
        text description
        numeric quantity "18,4"
        numeric unit_price "18,4"
        numeric amount "18,2"
    }
    validation_issues {
        bigint id PK
        uuid document_id FK
        uuid invoice_id FK "null = document-level"
        varchar code "TOTAL_MISMATCH, DUPLICATE_INVOICE, ..."
        varchar severity "error|warning|info"
        varchar field
        text message
        jsonb details
    }
    processing_events {
        bigint id PK
        uuid document_id FK
        int attempt
        varchar stage
        varchar status "started|completed|failed|info"
        text message
        int duration_ms
        jsonb details
        timestamptz created_at
    }
    corrections {
        bigint id PK
        uuid invoice_id FK
        varchar field
        jsonb old_value
        jsonb new_value
        text reason
        varchar corrected_by
        timestamptz created_at
    }
    chunks {
        bigint id PK
        uuid document_id FK
        uuid invoice_id FK
        int page_number
        varchar kind "invoice|page"
        text content
        vector embedding "384-d, HNSW cosine index"
    }
    reconciliations {
        uuid id PK
        uuid left_document_id FK
        uuid right_document_id FK
        jsonb summary
        jsonb params
        timestamptz created_at
    }
    reconciliation_items {
        bigint id PK
        uuid reconciliation_id FK
        text match_key
        varchar status "matched|mismatch|missing_in_left|missing_in_right"
        uuid left_invoice_id FK
        uuid right_invoice_id FK
        jsonb differences
    }
```

## Design notes

* **Money** is `NUMERIC(18,2)` (quantities and unit prices `NUMERIC(18,4)`) and `Decimal` in Python: no floating-point drift in validation arithmetic. The API serializes these as JSON numbers.
* **Normalized keys** (`invoice_number_norm`: alphanumerics upper-cased; `supplier_norm`: lower-case, accents and legal suffixes such as *Ltd/Limited/GmbH* removed) power duplicate detection and cross-verification matching. They are indexed together.
* **Generated `tsvector` columns** keep keyword search in sync without triggers. Page text uses the `simple` configuration, so invoice numbers and codes are not stemmed.
* **Evidence and provenance** (`raw_extraction.evidence`, `raw_extraction.rejected`, `field_confidence`, `source_ref`, `model`) make every extracted value traceable to its source and extractor.
* **Audit trail:** every manual change and approval writes a `corrections` row (old → new, who, why). Human-corrected fields get confidence 1.0.
* **Processing history:** `processing_events` holds every stage of every attempt, so reprocessing keeps the previous attempts' history.
* **Cascade deletes:** deleting a document removes its pages, invoices, issues, events, chunks and reconciliations.
