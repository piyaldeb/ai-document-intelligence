-- Generated with: pg_dump --schema-only (PostgreSQL 16 + pgvector), after `alembic upgrade head`.
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;
COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';
CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);
CREATE TABLE public.chunks (
    id bigint NOT NULL,
    document_id uuid NOT NULL,
    invoice_id uuid,
    page_number integer,
    kind character varying(32) NOT NULL,
    content text NOT NULL,
    embedding public.vector(384),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.chunks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.chunks_id_seq OWNED BY public.chunks.id;
CREATE TABLE public.corrections (
    id bigint NOT NULL,
    invoice_id uuid NOT NULL,
    field character varying(64) NOT NULL,
    old_value jsonb,
    new_value jsonb,
    reason text,
    corrected_by character varying(128),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.corrections_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.corrections_id_seq OWNED BY public.corrections.id;
CREATE TABLE public.document_pages (
    id bigint NOT NULL,
    document_id uuid NOT NULL,
    page_number integer NOT NULL,
    sheet_name text,
    method character varying(32) NOT NULL,
    text text NOT NULL,
    ocr_confidence double precision,
    char_count integer NOT NULL,
    warnings jsonb NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, "left"(COALESCE(text, ''::text), 500000))) STORED
);
CREATE SEQUENCE public.document_pages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.document_pages_id_seq OWNED BY public.document_pages.id;
CREATE TABLE public.documents (
    id uuid NOT NULL,
    original_filename text NOT NULL,
    file_type character varying(16) NOT NULL,
    mime_type character varying(128) NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 character varying(64) NOT NULL,
    storage_path text NOT NULL,
    status character varying(32) NOT NULL,
    stage character varying(64),
    progress integer NOT NULL,
    page_count integer,
    invoice_count integer NOT NULL,
    error_code character varying(64),
    error_message text,
    attempts integer NOT NULL,
    duplicate_of_id uuid,
    extraction_provider character varying(32),
    meta jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    processing_started_at timestamp with time zone,
    processing_finished_at timestamp with time zone,
    processing_ms integer
);
CREATE TABLE public.invoices (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    sequence integer NOT NULL,
    source_ref jsonb NOT NULL,
    page_start integer,
    page_end integer,
    invoice_number text,
    invoice_number_norm text,
    invoice_date date,
    supplier_name text,
    supplier_norm text,
    customer_name text,
    subtotal numeric(18,2),
    tax numeric(18,2),
    total numeric(18,2),
    currency character varying(3),
    field_confidence jsonb NOT NULL,
    extraction_method character varying(32) NOT NULL,
    model character varying(64),
    raw_extraction jsonb NOT NULL,
    source_text text NOT NULL,
    review_status character varying(32) NOT NULL,
    needs_review boolean NOT NULL,
    error_count integer NOT NULL,
    warning_count integer NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, ((((COALESCE(invoice_number, ''::text) || ' '::text) || COALESCE(supplier_name, ''::text)) || ' '::text) || COALESCE(customer_name, ''::text)))) STORED,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.line_items (
    id bigint NOT NULL,
    invoice_id uuid NOT NULL,
    "position" integer NOT NULL,
    description text,
    quantity numeric(18,4),
    unit_price numeric(18,4),
    amount numeric(18,2)
);
CREATE SEQUENCE public.line_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.line_items_id_seq OWNED BY public.line_items.id;
CREATE TABLE public.processing_events (
    id bigint NOT NULL,
    document_id uuid NOT NULL,
    attempt integer NOT NULL,
    stage character varying(64) NOT NULL,
    status character varying(16) NOT NULL,
    message text,
    duration_ms integer,
    details jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.processing_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.processing_events_id_seq OWNED BY public.processing_events.id;
CREATE TABLE public.reconciliation_items (
    id bigint NOT NULL,
    reconciliation_id uuid NOT NULL,
    match_key text,
    status character varying(32) NOT NULL,
    left_invoice_id uuid,
    right_invoice_id uuid,
    differences jsonb NOT NULL
);
CREATE SEQUENCE public.reconciliation_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.reconciliation_items_id_seq OWNED BY public.reconciliation_items.id;
CREATE TABLE public.reconciliations (
    id uuid NOT NULL,
    left_document_id uuid NOT NULL,
    right_document_id uuid NOT NULL,
    summary jsonb NOT NULL,
    params jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.validation_issues (
    id bigint NOT NULL,
    document_id uuid NOT NULL,
    invoice_id uuid,
    code character varying(64) NOT NULL,
    severity character varying(16) NOT NULL,
    field character varying(64),
    message text NOT NULL,
    details jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.validation_issues_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.validation_issues_id_seq OWNED BY public.validation_issues.id;
ALTER TABLE ONLY public.chunks ALTER COLUMN id SET DEFAULT nextval('public.chunks_id_seq'::regclass);
ALTER TABLE ONLY public.corrections ALTER COLUMN id SET DEFAULT nextval('public.corrections_id_seq'::regclass);
ALTER TABLE ONLY public.document_pages ALTER COLUMN id SET DEFAULT nextval('public.document_pages_id_seq'::regclass);
ALTER TABLE ONLY public.line_items ALTER COLUMN id SET DEFAULT nextval('public.line_items_id_seq'::regclass);
ALTER TABLE ONLY public.processing_events ALTER COLUMN id SET DEFAULT nextval('public.processing_events_id_seq'::regclass);
ALTER TABLE ONLY public.reconciliation_items ALTER COLUMN id SET DEFAULT nextval('public.reconciliation_items_id_seq'::regclass);
ALTER TABLE ONLY public.validation_issues ALTER COLUMN id SET DEFAULT nextval('public.validation_issues_id_seq'::regclass);
ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);
ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.corrections
    ADD CONSTRAINT corrections_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.document_pages
    ADD CONSTRAINT document_pages_document_id_page_number_key UNIQUE (document_id, page_number);
ALTER TABLE ONLY public.document_pages
    ADD CONSTRAINT document_pages_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.line_items
    ADD CONSTRAINT line_items_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.processing_events
    ADD CONSTRAINT processing_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.reconciliation_items
    ADD CONSTRAINT reconciliation_items_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.reconciliations
    ADD CONSTRAINT reconciliations_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.validation_issues
    ADD CONSTRAINT validation_issues_pkey PRIMARY KEY (id);
CREATE INDEX ix_chunks_document_id ON public.chunks USING btree (document_id);
CREATE INDEX ix_chunks_embedding_hnsw ON public.chunks USING hnsw (embedding public.vector_cosine_ops);
CREATE INDEX ix_chunks_invoice_id ON public.chunks USING btree (invoice_id);
CREATE INDEX ix_corrections_invoice_id ON public.corrections USING btree (invoice_id);
CREATE INDEX ix_document_pages_document_id ON public.document_pages USING btree (document_id);
CREATE INDEX ix_document_pages_tsv ON public.document_pages USING gin (tsv);
CREATE INDEX ix_documents_created_at ON public.documents USING btree (created_at);
CREATE INDEX ix_documents_file_type ON public.documents USING btree (file_type);
CREATE INDEX ix_documents_sha256 ON public.documents USING btree (sha256);
CREATE INDEX ix_documents_status ON public.documents USING btree (status);
CREATE INDEX ix_invoices_currency ON public.invoices USING btree (currency);
CREATE INDEX ix_invoices_document_id ON public.invoices USING btree (document_id);
CREATE INDEX ix_invoices_dup_key ON public.invoices USING btree (supplier_norm, invoice_number_norm);
CREATE INDEX ix_invoices_invoice_date ON public.invoices USING btree (invoice_date);
CREATE INDEX ix_invoices_invoice_number_norm ON public.invoices USING btree (invoice_number_norm);
CREATE INDEX ix_invoices_needs_review ON public.invoices USING btree (needs_review);
CREATE INDEX ix_invoices_review_status ON public.invoices USING btree (review_status);
CREATE INDEX ix_invoices_supplier_trgm ON public.invoices USING gin (supplier_name public.gin_trgm_ops);
CREATE INDEX ix_invoices_total ON public.invoices USING btree (total);
CREATE INDEX ix_invoices_tsv ON public.invoices USING gin (tsv);
CREATE INDEX ix_line_items_invoice_id ON public.line_items USING btree (invoice_id);
CREATE INDEX ix_processing_events_document_id ON public.processing_events USING btree (document_id);
CREATE INDEX ix_reconciliation_items_reconciliation_id ON public.reconciliation_items USING btree (reconciliation_id);
CREATE INDEX ix_validation_issues_code ON public.validation_issues USING btree (code);
CREATE INDEX ix_validation_issues_document_id ON public.validation_issues USING btree (document_id);
CREATE INDEX ix_validation_issues_invoice_id ON public.validation_issues USING btree (invoice_id);
CREATE INDEX ix_validation_issues_severity ON public.validation_issues USING btree (severity);
ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.corrections
    ADD CONSTRAINT corrections_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.document_pages
    ADD CONSTRAINT document_pages_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_duplicate_of_id_fkey FOREIGN KEY (duplicate_of_id) REFERENCES public.documents(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.line_items
    ADD CONSTRAINT line_items_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.processing_events
    ADD CONSTRAINT processing_events_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.reconciliation_items
    ADD CONSTRAINT reconciliation_items_left_invoice_id_fkey FOREIGN KEY (left_invoice_id) REFERENCES public.invoices(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.reconciliation_items
    ADD CONSTRAINT reconciliation_items_reconciliation_id_fkey FOREIGN KEY (reconciliation_id) REFERENCES public.reconciliations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.reconciliation_items
    ADD CONSTRAINT reconciliation_items_right_invoice_id_fkey FOREIGN KEY (right_invoice_id) REFERENCES public.invoices(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.reconciliations
    ADD CONSTRAINT reconciliations_left_document_id_fkey FOREIGN KEY (left_document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.reconciliations
    ADD CONSTRAINT reconciliations_right_document_id_fkey FOREIGN KEY (right_document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.validation_issues
    ADD CONSTRAINT validation_issues_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.validation_issues
    ADD CONSTRAINT validation_issues_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE CASCADE;
