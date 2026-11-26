# Rubric-Grounded Essay Feedback with Evidence Citation

## Implementation Plan (Architecture Review Revision)

**Status:** Phases 1–9 are implemented. Phase 10 remains planned; the scope amendment below governs the remaining work.

**Product goal:** A local learning, academic-demonstration, and portfolio project that evaluates student essays against instructor-defined rubrics, validates exact evidence excerpts and locations, and supports faculty review.

The original production-scale architecture remains below as historical context. The scope amendment is authoritative for remaining phases and removes infrastructure/features that are unnecessary for a local demonstration.

Real AI evaluation, transparent labeled mock demonstrations, and verified citations are separate modes/features. Mock scores or excerpts must never be presented as real AI output.

---

## 0. How to read this document

| Section | Purpose |
| --- | --- |
| 1 | Original requirements; apply the scope amendment's exclusions |
| 2 | Full system architecture |
| 2.5 | **MVP vs production enhancements** |
| 2.6 | **Simplified local development workflow** |
| 3 | Database ER diagram, constraints, score preservation |
| 4 | Original backend folder proposal (reference only) |
| 5 | Original frontend folder proposal (reference only) |
| 6 | API endpoints |
| 7 | AI evaluation workflow (scoring, validation, prompts) |
| 8 | Evidence retrieval, exact quote validation, offsets, and review boundary |
| 9 | Security architecture |
| 10 | Completed implementation history and revised remaining roadmap |
| 11 | Status machine (evaluation lifecycle) |
| 12 | Testing strategy + **synthetic fixture plan** (§12.1) |
| 13 | Functional product guarantees |
| 14–15 | Original Redis/ARQ and Windows setup proposal (superseded) |
| 16 | Changelog of this review |

---

## Scope amendment (2026-11-25) — authoritative for remaining work

This project is not a production SaaS. Keep completed phases and their implementation history intact; do not add enterprise infrastructure or rewrite working code. The revised roadmap replaces the original Phases 7–13.

### Revised remaining-phase roadmap

| Phase | Scope |
| --- | --- |
| 7 — Evidence-grounded evaluation and explicit mock mode | **Implemented.** Local lexical retrieval over existing essay chunks; exact quote verification and source locations; persisted mock/real provenance. Mock results are labeled in API responses and records; UI labeling is part of Phase 9. OpenAI remains available when explicitly configured. |
| 8 — Faculty review and approval | **Implemented.** Course-scoped review queue, notes, separate faculty score/feedback overrides, review-event history, and approve/reject/request-changes transitions. Students see scores and feedback only after approval. |
| 9 — Functional React demonstration | **Implemented.** Connected login/session handling, student course/essay upload, published rubric selection, evaluation status/results, citation highlights/locations, mock-mode labels, and course-scoped faculty review/approval to existing APIs. |
| 10 — Local demo data and end-to-end verification | Add clearly synthetic, repeatable demo users/course/rubric/essay data and local run instructions. Verify mock mode end-to-end without credits; optionally verify OpenAI mode when a key is configured. Remove unused Redis/ARQ/Gemini/embedding setup from the local demo configuration and documentation. |

### Keep, simplify, and remove

- **Keep:** FastAPI, React/Vite, PostgreSQL, existing authentication/RBAC, safe PDF/DOCX/TXT handling, course-scoped rubrics and immutable versions, local file storage, and the Phase 6 OpenAI provider/evaluation path.
- **Simplify:** Run evaluation synchronously for the small local demo. Retrieve candidate evidence with a lightweight local lexical ranker over `EssayChunk` records; do not add a vector database, embeddings, FAISS, or an NLI model. Exact substring validation proves that a quote exists and offsets identify its location; it does not by itself prove semantic support, so show the source and leave final approval to faculty.
- **Mock mode:** Make it an explicit demo provider, never a fallback for OpenAI errors. Persist and return a mode/source field, display a prominent “MOCK — NOT AI-GENERATED” label, and use only deterministic, synthetic demo responses. Do not copy mock output into a record represented as OpenAI output.
- **Remove from remaining scope:** Redis, ARQ, Celery, distributed workers, Kubernetes, cloud storage/services, multi-provider support, embeddings/FAISS, independent entailment-model infrastructure, analytics dashboards, PDF report generation, and production monitoring/deployment. Existing Redis configuration is legacy and is not required by the current application.
- **Keep basic security:** retain authentication, authorization, ownership/course checks, request validation, safe uploads, secret handling, and privacy boundaries. Training/demo use is not a reason to weaken these controls.

### Existing gaps and prerequisites

- Phase 6 supports configured OpenAI evaluation, but the latest safe environment check found no non-empty `OPENAI_API_KEY`; therefore a real provider request has not been verified.
- The local database had no active published test rubric with valid weighted criteria during the latest check.
- Evidence retrieval and quote-location verification are implemented. Verified citations are stored in `criterion_scores.claims_json`; revision `0008_evidence_citations_mock` adds this field and `evaluations.evaluation_mode`.
- Explicit mock mode and persisted provenance are implemented. No real OpenAI request was made for Phase 7; automated tests exercise provider behavior without a live API key.
- Phase 9 connects student and faculty workflows to the existing API. It does not include faculty rubric authoring or an admin dashboard; rubric authoring remains available through the existing API.
- The frontend route contract was checked against the backend OpenAPI document. No live authenticated browser workflow was exercised as part of Phase 9.
- `testdata/` currently contains only its README, not the promised synthetic essay/rubric fixtures.
- Redis references remain in the Compose file, `.env.example`, README, and historical plan sections. They are unused by the Phase 1–6 application and should be removed from the local demo setup in Phase 10.
- DOCX/TXT extractors do not provide physical page numbers; citations can still use stable character offsets, while page locations are available for PDFs.

### Local demonstration flow

Run the existing local PostgreSQL service, apply Alembic migrations, and start FastAPI with Uvicorn. A student using synthetic inputs uploads an essay and selects a published course rubric. Evaluation uses real OpenAI only when explicitly configured; otherwise the operator explicitly selects mock mode and every mock result remains labeled. The backend retrieves candidate passages locally, verifies exact quotes against the submitted essay, and returns character offsets plus available paragraph/page locations. Repeated quotes within a cited passage are rejected as ambiguous; a quote in another passage is only accepted when the provider identifies that source passage. Course-enrolled faculty inspect the evidence, add notes or separate feedback corrections, then approve, reject, or request changes. Students see criterion feedback only after approval. No cloud account, queue service, or external data set is required.

---

## 1. Requirements analysis

### 1.1 Functional requirements

| ID | Requirement | Primary actors |
| --- | --- | --- |
| FR-01 | Register/login; JWT sessions; roles `student`, `faculty`, `admin` | All |
| FR-02 | Students upload essays as PDF, DOCX, or TXT (validated type/size) | Student |
| FR-03 | Extract, preprocess, sentence-split; persist original text, normalized text, and consistent offsets | System |
| FR-04 | Faculty create/edit/version/publish rubrics and weighted criteria | Faculty |
| FR-05 | Student (or faculty) selects a published rubric version and requests evaluation | Student, Faculty |
| FR-06 | AI scores each criterion independently; score must be inside `[min_score, max_score]` or the output is **rejected and retried** (never silently clamped) | System |
| FR-07 | AI produces explanations, strengths, weaknesses, improvement suggestions | System |
| FR-08 | Retrieve supporting passages; return exact quotations with offsets | System |
| FR-09 | Verify quotes exist in the essay by **exact quotation matching** (mandatory) | System |
| FR-10 | Show the verified excerpt in context; exact matching does not by itself prove support, which remains a faculty judgment | System, Faculty |
| FR-11 | Flag unsupported feedback claims; never invent quotations | System |
| FR-12 | Faculty review, edit scores/feedback, approve or reject | Faculty |
| FR-13 | Preserve original AI scores separately from faculty-modified scores | System |
| FR-14 | Student and faculty dashboards; submission/evaluation history | All |
| FR-15 | Performance analytics (cohort, rubric, criterion) — out of scope for the local demo | — |
| FR-16 | Downloadable feedback report (PDF + JSON) — out of scope for the local demo | — |
| FR-17 | Basic application/security logging; no enterprise audit pipeline | System |

### 1.2 Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-01 | Modular FastAPI backend; React/Vite frontend; PostgreSQL source of truth |
| NFR-02 | Structured LLM JSON only; schema-validated before persistence |
| NFR-03 | Prompt-injection resistance: essay text never treated as instructions |
| NFR-04 | Object-level authorization |
| NFR-05 | Secrets only via environment variables |
| NFR-06 | Evaluation is synchronous for small local demonstrations |
| NFR-07 | Safe, understandable errors and evaluation status in the UI |
| NFR-08 | Local PostgreSQL + API + frontend; Docker is optional |
| NFR-09 | Automated tests at each phase; labeled fixtures for scoring and evidence |
| NFR-10 | Explicit OpenAI or mock mode; mock output is labeled and persisted as such |

### 1.3 Original non-goals and retained foundations

The following remain outside the revised portfolio scope:

- Real-time collaborative rubric editing
- LMS (Canvas/Moodle) LTI
- Web-corpus plagiarism detection
- Multi-tenant billing / Stripe
- Native mobile apps

Courses and enrollments remain lightweight foundations for existing authorization and the planned faculty review queue; this is not a full LMS.

### 1.4 Credentials the operator must provide

No API keys will be hardcoded. The API can start without an OpenAI key; an OpenAI evaluation request fails closed with `LLM_NOT_CONFIGURED`. Phase 7 mock mode must be explicitly selected.

| Variable | Required for | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Always | PostgreSQL SQLAlchemy URL |
| `JWT_SECRET_KEY` | Always | HS256; min 32 random bytes |
| `JWT_REFRESH_SECRET_KEY` | Always | Separate from access secret |
| `FILE_STORAGE_DIR` | Always | Local disk path |
| `MAX_UPLOAD_MB` | Upload | Default `10`; accepted range `1`–`50` |
| `MAX_EXTRACTED_CHARS` | Upload | Default `500000`; accepted range `1`–`2000000` |
| `LLM_PROVIDER` | Evaluation | Explicitly select `openai` or `mock` |
| `OPENAI_API_KEY` | If `LLM_PROVIDER=openai` | OpenAI evaluation requests |
| `OPENAI_CHAT_MODEL` | Optional | Default `gpt-4o-mini` |
| `CORS_ORIGINS` | Always | e.g. `http://localhost:5173` |

The existing `.env.example` still contains legacy Redis/Gemini/embedding entries; Phase 10 removes unused demo configuration. Do not add a second live provider or use mock mode as a fallback for OpenAI errors.

---

## 2. System architecture

### 2.1 Local demo architecture (scope revision)

```
React + Vite SPA
    │ HTTP / JSON
FastAPI (auth, RBAC, validation, uploads, rubrics, synchronous evaluation)
    ├── PostgreSQL 18 (SQLAlchemy + Alembic)
    └── Local private file storage
```

**Execution:** the demonstration uses synchronous evaluation for small synthetic essays. No queue, worker, cloud service, vector store, or production deployment is required.

Use the already-installed local PostgreSQL service. Docker Compose may remain an optional PostgreSQL-only convenience, but the normal demo path does not require Docker.

**Document pipeline:** PyMuPDF / python-docx / TXT → `extracted_text` → versioned normalizer → `normalized_text` + offset alignment → sentence chunks with dual offsets → lightweight local lexical retrieval.

### 2.2 High-level module map

| Module | Backend package | Frontend surfaces |
| --- | --- | --- |
| AuthZ/AuthN | `app/api/auth`, `app/core/security` | Login, register, session |
| Student dashboard | `app/api/dashboard` | `/student` |
| Faculty dashboard | `app/api/dashboard` | `/faculty` |
| Essay upload | `app/api/essays` | Upload + history |
| Document processing | `app/services/documents` | Parse status |
| Rubric management | `app/api/rubrics` | Rubric CRUD + versions |
| Criterion-wise AI eval | Existing evaluation/LLM services | Synchronous evaluate + results |
| Evidence retrieval/verification | Phase 7 addition | Exact excerpts + locations |
| Faculty review | Phase 8 addition | Review, edit, approve |
| History | Existing evaluation data + Phase 9 UI | Student/faculty history |
| Admin | Existing role/auth foundation | No analytics console in revised scope |

### 2.3 Architectural principles

1. PostgreSQL is the source of truth; essay chunks remain durable and retrieval uses local lexical ranking.
2. Published rubric versions are immutable. Evaluations pin `rubric_version_id`.
3. Two-score model: `ai_score` write-once; `faculty_score` nullable until review.
4. **Exact quotation matching is mandatory** for a citation to be shown as a quote.
5. **Match ≠ support.** Exact verification proves quote existence only; it is not semantic proof. Faculty review provides the final judgment.
6. **Invalid scores are rejected and retried**, never clamped.
7. Essay text is untrusted user content, never concatenated into the system prompt.
8. Use real OpenAI only when configured or an explicitly selected, labeled mock provider.

### 2.4 Decisions for remaining scope

| Decision | Choice |
| --- | --- |
| Monorepo | `backend/`, `frontend/`, `docs/`, `testdata/`, `infra/` |
| Auth | Access JWT 15m + httpOnly refresh cookie 7d |
| Passwords | Argon2id |
| Evaluation execution | Synchronous FastAPI request for small local demos |
| Storage | Existing private local disk storage |
| Sentence split | spaCy `en_core_web_sm` |
| Evidence retrieval | Local lexical ranking over existing essay chunks |
| Admin role | Yes |
| Courses | Lightweight `courses` + `enrollments` |
| Student scores | Hidden until faculty `approved` |
| Register | Students self-register; faculty/admin seeded |
| LLM modes | OpenAI when configured; explicit, provenance-labeled mock mode for demos |

### 2.5 MVP vs production enhancements

The portfolio MVP is the local workflow defined in the scope amendment; it does not include every original SaaS feature.

#### Keep in the local demonstration

- Existing authentication, course authorization, uploads, rubric authoring, immutable rubric versions, and Phase 6 OpenAI evaluation
- Exact quote existence checks and source offsets/page metadata
- Explicit mock demo mode with persisted provenance and visible labeling
- Basic faculty review/approval and the student/faculty UI needed to demonstrate it
- Synthetic local fixtures and focused backend/frontend tests

#### Explicitly out of scope

- Redis, ARQ, Celery, distributed workers, Kubernetes, cloud storage/services, and recurring hosted infrastructure
- Embeddings, FAISS/vector search, a separate NLI model, multiple LLM providers, analytics dashboards, PDF reports, and production monitoring
- Production deployment, autoscaling, and enterprise audit/operations features

### 2.6 Simplified initial development workflow

**Goal:** run the complete demonstration locally with PostgreSQL, the API, and Vite—without Redis, ARQ, or Docker.

**Daily loop:**

1. Start the existing local PostgreSQL service.
2. Apply Alembic migrations and run FastAPI with Uvicorn.
3. Run Vite in another terminal.
4. Use synthetic seed users, course, rubric, and essay fixtures.
5. Select real OpenAI mode only when credentials are configured; otherwise explicitly choose visibly labeled mock mode.

**Do not require:**

- Docker, Redis, or a worker process
- Cloud accounts, API credits for the mock demonstration, or real student data
- Gemini, embeddings, NLI model downloads, S3, or CI infrastructure

**Revised phase grouping:**

| Dev batch | Phases | You can exercise |
| --- | --- | --- |
| Completed foundation | 1–6 | Auth, uploads, rubrics, synchronous OpenAI evaluation |
| Evidence + review | 7–8 | Verified excerpts, mock labeling, faculty approval |
| Demonstration | 9–10 | Student/faculty UI, synthetic data, local end-to-end checks |

Tests still run **at the end of each phase**, not only at batch end.

---

## 3. Original database design reference (not a migration checklist)

This ERD records the original broader proposal. Inspect current models and migrations before any change. Remaining phases should add only genuinely required citation/provenance/review schema; do not create queue, embedding, analytics, or report tables from this historical proposal.

### 3.1 Mermaid ERD

```mermaid
erDiagram
    users ||--o{ enrollments : "student or faculty"
    courses ||--o{ enrollments : has
    courses ||--o{ rubrics : owns
    users ||--o{ rubrics : creates
    users ||--o{ essays : submits
    courses ||--o{ essays : "optional course"
    essays ||--o{ essay_chunks : split_into
    essays ||--o{ evaluations : evaluated_by
    rubrics ||--o{ rubric_versions : versions
    rubric_versions ||--o{ rubric_criteria : contains
    rubric_versions ||--o{ evaluations : used_by
    evaluations ||--o{ criterion_scores : scores
    rubric_criteria ||--o{ criterion_scores : scored_as
    criterion_scores ||--o{ evidence_citations : cites
    essay_chunks ||--o{ evidence_citations : "optional chunk"
    evaluations ||--|| evaluation_feedback : summarizes
    evaluations ||--o{ faculty_reviews : reviewed
    users ||--o{ faculty_reviews : reviewer
    users ||--o{ audit_logs : actor
    evaluations ||--o{ evaluation_jobs : processed_as

    users {
        uuid id PK
        string email UK
        string password_hash
        string full_name
        enum role
        bool is_active
        timestamptz created_at
        timestamptz updated_at
    }

    courses {
        uuid id PK
        string name
        string code
        uuid created_by_id FK
        bool is_active
        timestamptz created_at
    }

    enrollments {
        uuid id PK
        uuid course_id FK
        uuid user_id FK
        enum role
        timestamptz created_at
    }

    essays {
        uuid id PK
        uuid student_id FK
        uuid course_id FK
        string original_filename
        string stored_path
        string content_type
        int size_bytes
        enum parse_status
        text extracted_text
        text normalized_text
        string normalizer_version
        jsonb offset_alignment
        jsonb page_map
        string extractor_name
        string extractor_version
        string sha256
        timestamptz created_at
    }

    essay_chunks {
        uuid id PK
        uuid essay_id FK
        int chunk_index
        int sentence_index
        int char_start
        int char_end
        int extracted_char_start
        int extracted_char_end
        int page_start
        int page_end
        text text
        vector_ref embedding_path
    }

    rubrics {
        uuid id PK
        uuid course_id FK
        uuid created_by_id FK
        string title
        text description
        enum status
        timestamptz created_at
    }

    rubric_versions {
        uuid id PK
        uuid rubric_id FK
        int version_number
        bool is_published
        timestamptz published_at
        jsonb snapshot
    }

    rubric_criteria {
        uuid id PK
        uuid rubric_version_id FK
        string name
        text description
        text levels_json
        numeric max_score
        numeric min_score
        numeric weight
        int sort_order
    }

    evaluations {
        uuid id PK
        uuid essay_id FK
        uuid rubric_version_id FK
        uuid requested_by_id FK
        enum status
        numeric ai_total_score
        numeric faculty_total_score
        bool has_unsupported_flags
        timestamptz started_at
        timestamptz completed_at
    }

    criterion_scores {
        uuid id PK
        uuid evaluation_id FK
        uuid criterion_id FK
        numeric ai_score
        numeric faculty_score
        text ai_rationale
        text faculty_rationale
        jsonb strengths
        jsonb weaknesses
        jsonb suggestions
        enum evidence_status
    }

    evidence_citations {
        uuid id PK
        uuid criterion_score_id FK
        uuid chunk_id FK
        text quoted_text
        int char_start
        int char_end
        int extracted_char_start
        int extracted_char_end
        bool lexical_verified
        float retrieval_similarity
        enum entailment_label
        float entailment_confidence
        enum verification_status
        text claim_span
        text reason
    }

    evaluation_feedback {
        uuid id PK
        uuid evaluation_id FK
        text ai_summary
        text faculty_summary
        jsonb overall_strengths
        jsonb overall_improvements
        bool download_ready
    }

    faculty_reviews {
        uuid id PK
        uuid evaluation_id FK
        uuid reviewer_id FK
        enum decision
        text comments
        timestamptz decided_at
    }

    evaluation_jobs {
        uuid id PK
        uuid evaluation_id FK
        enum status
        int attempt
        text error_message
        jsonb progress
        timestamptz updated_at
    }

    audit_logs {
        uuid id PK
        uuid actor_id FK
        string action
        string entity_type
        uuid entity_id
        jsonb metadata
        inet ip
        timestamptz created_at
    }
```

### 3.2 Normalization and constraints

- **Users:** unique email; `role IN ('student','faculty','admin')`.
- **Enrollments:** unique `(course_id, user_id)`.
- **Essays:** `parse_status IN ('parsed','failed')`; SHA-256 of stored file; `extracted_text` is raw extract; `normalized_text` is verification source of truth; `normalizer_version` identifies the exact transform; `offset_alignment` maps normalized indices to extracted indices; `page_map` preserves available source-page spans. Invalid or unparseable uploads are rejected before storage.
- **Chunks:** unique `(essay_id, chunk_index)`; `char_start/char_end` into `normalized_text`; `extracted_char_start/extracted_char_end` into `extracted_text`; page ranges are populated when the extractor provides physical page boundaries; `char_end > char_start`.
- **Rubrics:** course-scoped; unique `(rubric_id, version_number)`; published versions immutable in the service layer.
- **Criteria:** `min_score < max_score`; `weight > 0`; fractional weights sum to `1.0` per version (tolerance `0.000001`); weights and score-level descriptors are validated per version.
- **Evaluations:** preserve the existing uniqueness/idempotency behavior; do not add a job table or queued lifecycle.
- **Criterion scores:** unique `(evaluation_id, criterion_id)`; `ai_score` stored **only** if inside `[min_score, max_score]`; same for `faculty_score` when set.
- **Citations (Phase 7 design):** persist exact quote, source chunk, provenance, and server-computed normalized/extracted offsets; do not represent exact-match validation as proof of claim support.
- **Indexes:** add only indexes required by actual query patterns in the revised scope; no job/vector/analytics indexes.

### 3.3 Score preservation

`ai_score` / `ai_total_score` are set once after a **valid** AI run. Faculty writes `faculty_*` only. API returns both. Official student reports use faculty values when present, else AI, and only after `approved`. Faculty UI always shows AI originals.

---

## 4. Original backend folder proposal (reference only)

This is not a request to create every listed module. Reuse the current backend layout and add only code needed for the revised phases; do not add `jobs/`, embeddings/FAISS, entailment, analytics, PDF-report, or multi-provider modules.

```
backend/
  alembic/
    env.py
    versions/
  app/
    __init__.py
    main.py
    worker.py
    api/
      deps.py
      router.py
      v1/
        auth.py
        users.py
        courses.py
        essays.py
        rubrics.py
        evaluations.py
        reviews.py
        analytics.py
        reports.py
        dashboard.py
        admin.py
    core/
      config.py
      logging.py
      security.py
      rbac.py
    db/
      base.py
      session.py
      models/
        user.py
        course.py
        essay.py
        rubric.py
        evaluation.py
        review.py
        audit.py
    schemas/
    services/
      auth.py
      documents/
        extractor.py
        preprocessor.py
        alignment.py
        chunker.py
      storage.py
      embeddings.py
      faiss_index.py
      llm/
        base.py
        openai_client.py
        gemini_client.py
        factory.py
        json_schema.py
        prompts.py
        injection_guard.py
      evaluation/
        pipeline.py
        criterion_scorer.py
        score_validator.py
        aggregator.py
      evidence/
        retriever.py
        quotation.py
      verification/
        lexical.py
        entailment.py
        claim_support.py
        calibration.py
      feedback/
        generator.py
        report_pdf.py
      analytics.py
      audit.py
    jobs/
      evaluation_job.py
    scripts/
      seed.py
    utils/
      files.py
      text.py
  tests/
    conftest.py
    unit/
    integration/
    api/
    verification/
      test_calibration.py
  requirements.txt
  requirements-dev.txt
  Dockerfile
  alembic.ini
  pyproject.toml
```

---

## 5. Original frontend folder proposal (reference only)

Phase 9 should connect the existing frontend shell to the required student/faculty workflows. Analytics, charts, PDF reports, and other listed surfaces are out of scope.

```
frontend/
  index.html
  vite.config.ts
  tailwind.config.js
  package.json
  src/
    main.tsx
    App.tsx
    api/
      client.ts
      auth.ts
      essays.ts
      rubrics.ts
      evaluations.ts
      reviews.ts
      analytics.ts
      reports.ts
    auth/
      AuthProvider.tsx
      ProtectedRoute.tsx
      roles.ts
    components/
      layout/AppShell.tsx
      ui/
      evidence/CitationCard.tsx
      evaluation/ScoreEditor.tsx
      charts/
    pages/
      auth/LoginPage.tsx
      auth/RegisterPage.tsx
      student/StudentDashboard.tsx
      student/EssayUploadPage.tsx
      student/SubmissionHistoryPage.tsx
      student/EvaluationReportPage.tsx
      faculty/FacultyDashboard.tsx
      faculty/RubricListPage.tsx
      faculty/RubricEditorPage.tsx
      faculty/SubmissionsPage.tsx
      faculty/EvaluationReviewPage.tsx
      faculty/AnalyticsPage.tsx
    hooks/
    types/
    utils/
  tests/
  Dockerfile
```

Visual language: academic SaaS — navy/slate palette, readable report typography, status badges (`queued`, `running`, `needs_review`, `approved`, `rejected`, `changes_requested`, `failed`). `has_unsupported_flags` renders as a warning indicator on the evaluation card. Cards on mobile; tables on desktop.

---

## 6. API endpoints

Base path: `/api/v1`. All endpoints except register/login/refresh/logout require `Authorization: Bearer <access>`. Refresh and logout require the HttpOnly refresh cookie.

### 6.1 Auth

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| POST | `/auth/register` | Public | Student self-register |
| POST | `/auth/login` | Public | Refresh cookie + access token |
| POST | `/auth/refresh` | Cookie | New access token |
| POST | `/auth/logout` | Refresh cookie | Revoke refresh |
| GET | `/auth/me` | Auth | Current user |
| GET | `/users/{id}` | Owner/admin | Read own profile; admin may read any profile |
| GET/POST | `/admin/users` | Admin | List users / provision a user with an assigned role |

Faculty/admin: seed script or admin-created.

### 6.2 Courses and users

| Method | Path | Access |
| --- | --- | --- |
| GET/POST | `/courses` | Faculty/admin create; members list |
| GET | `/courses/{id}` | Enrolled |
| POST | `/courses/{id}/enrollments` | Faculty/admin |
| GET | `/users/me/dashboard` | Auth |

### 6.3 Essays

| Method | Path | Access |
| --- | --- | --- |
| POST | `/essays` | Student (multipart: file, `course_id`) |
| GET | `/essays` | Student: own; faculty: course submissions |
| GET | `/essays/{id}` | Owner or course faculty |
| GET | `/essays/{id}/text` | Same (`extracted_text` + `normalized_text`) |
| GET | `/essays/{id}/chunks` | Faculty |
| DELETE | `/essays/{id}` | Owner if no approved eval; else faculty/admin |

### 6.4 Rubrics

| Method | Path | Access |
| --- | --- | --- |
| POST | `/rubrics` | Faculty enrolled in the course |
| GET | `/rubrics` | Faculty: enrolled courses; student: published in enrolled courses; admin: all |
| GET | `/rubrics/{id}` | Same visibility as list |
| PATCH | `/rubrics/{id}` | Owner faculty; draft metadata only |
| POST | `/rubrics/{id}/versions` | Owner faculty |
| GET | `/rubrics/{id}/versions` | Faculty: course; student: published versions in enrolled courses; admin: all |
| GET | `/rubric-versions/{id}` | Authorized course member; students only published versions; admin: all |
| PUT | `/rubric-versions/{id}/criteria` | Owner faculty; unpublished version only |
| POST | `/rubric-versions/{id}/publish` | Owner faculty |
| POST | `/rubrics/{id}/archive` | Owner faculty |

### 6.5 Evaluations and jobs

The evaluation API supports synchronous create and authorized retrieval by ID. Phase 8 adds the faculty review queue and review actions; Phase 9 adds student history and connects the workflow to the UI.

| Method | Path | Access |
| --- | --- | --- |
| POST | `/essays/{id}/evaluations` | Owner student or faculty | `{ rubric_version_id }` → synchronous evaluation |
| GET | `/evaluations` | Phase 9 addition: authorized student/faculty history |
| GET | `/evaluations/{id}` | Authorized |
| GET | `/evaluations/{id}/job` | Superseded; no job progress in the local workflow |
| POST | `/evaluations/{id}/rerun` | Not required for the portfolio demonstration |

### 6.6 Faculty review

Implemented in Phase 8. Faculty access is limited to evaluations for courses where they have faculty enrollment. The existing evaluation detail endpoint returns AI results, evidence citations, faculty overrides, and review history to authorized faculty.

| Method | Path | Access |
| --- | --- | --- |
| GET | `/reviews/queue` | Course faculty; pending and changes-requested |
| POST | `/evaluations/{id}/review-notes` | Course faculty; append a note |
| PATCH | `/evaluations/{id}/criterion-scores/{sid}` | Course faculty; separate faculty score/feedback overrides |
| POST | `/evaluations/{id}/review` | Course faculty | `approved` \| `rejected` \| `changes_requested` |

### 6.7 Reports, analytics, audit

The routes below belonged to the original SaaS proposal and are not part of the revised remaining scope.

| Method | Path | Access |
| --- | --- | --- |
| GET | `/evaluations/{id}/report.pdf` | Authorized; students only if approved |
| GET | `/evaluations/{id}/report.json` | Same |
| GET | `/analytics/overview` | Faculty/admin |
| GET | `/analytics/rubrics/{id}` | Faculty |
| GET | `/analytics/courses/{id}` | Faculty |
| GET | `/admin/audit-logs` | Admin |

### 6.8 Error contract

`{ "detail": "...", "code": "INVALID_SCORE", "request_id": "..." }` with HTTP 400/401/403/404/409/413/422/503.

---

## 7. AI evaluation workflow

### 7.1 Preconditions

- Essay `parse_status=parsed`; `extracted_text` and `normalized_text` non-empty; alignment present; chunks valid.
- Rubric version published with ≥1 criterion.
- OpenAI mode requires a configured API key; otherwise return a safe `LLM_NOT_CONFIGURED` error. Mock mode is available only when explicitly selected.

### 7.2 Evaluation pipeline (synchronous)

The evaluation path evaluates criteria synchronously and persists validated scores. Phase 7 adds local evidence retrieval and quote validation; it does not add a queue or worker.

```
1. Authenticate and authorize the essay and same-course published rubric.
2. Load normalized essay text, offset alignment, chunks, and criteria.
3. Rank a small set of existing chunks locally using lexical overlap.
4. For each criterion independently, call the explicitly selected provider.
5. Validate structured output, score range/precision, and each quoted excerpt.
6. Compute the weighted total and persist complete criterion results/citations.
7. Set status=needs_review; faculty review/approval is Phase 8.
```

**Independence:** a criterion call does not include other criteria’s scores.

**Provider/network retries:** exponential backoff on 429/5xx; max 3 transport attempts, separate from score-repair retries.

### 7.3 Structured LLM output (per criterion)

```json
{
  "criterion_id": "uuid",
  "score": 0,
  "rationale": "string",
  "strengths": ["string"],
  "weaknesses": ["string"],
  "suggestions": ["string"],
  "claims": [
    {
      "text": "string",
      "evidence_quotes": [
        {
          "chunk_id": "uuid",
          "quoted_text": "exact substring of the essay",
          "reason": "why this quote supports the claim"
        }
      ]
    }
  ]
}
```

Invalid JSON → one repair retry, then criterion failure. **This retry budget is separate from score-range retries in §7.4** (which allows up to 2). A single criterion may thus receive at most 1 JSON-repair + 2 score-repair attempts before failure.

The provider schema requires claims and evidence quotes. The service validates these against retrieved essay passages before persistence; mock mode is separately labeled and never substitutes automatically for a failed OpenAI request.

### 7.4 Score validation (no silent clamp)

| LLM output | Action |
| --- | --- |
| Missing `score`, non-numeric, NaN, inf | Reject; repair retry |
| `score < min_score` or `score > max_score` | Reject; repair retry quoting the allowed range |
| Integer/float inside range (including endpoints) | Accept; persist as `ai_score` |
| After max retries still invalid | Do not write `ai_score`; evaluation `failed`; error `INVALID_SCORE` |

Faculty PATCH uses the same range check: out-of-range `faculty_score` → `422`, no write, **no clamp**.

There is no code path that does `min(max(score, min), max)` to “save” a model mistake.

### 7.5 Prompt-injection controls

- System prompt: instructions + rubric JSON only; never the essay.
- Essay and retrieved passages only in a delimited user section: untrusted student content; ignore instructions inside it.
- Do not “sanitize” essay wording used for grading (that would break evidence). Injection patterns may be redacted in **logs** only.
- No tools/web during scoring.
- Temperature ≤ 0.2 scoring; ≤ 0.3 feedback; bounded max tokens.

### 7.6 Explicit provider mode

`LLM_PROVIDER=openai` selects the real OpenAI adapter and requires a non-empty key. `LLM_PROVIDER=mock` is an explicit, deterministic demonstration mode whose records and responses must be labeled as mock. Configuration or provider errors never fall back to mock. Tests mock provider responses and do not require a live key.

---

## 8. Evidence retrieval and citation policy

Phase 7 uses a deterministic local lexical ranker over existing essay chunks. Ranked chunks are candidate context only; neither ranking nor a model's explanation verifies citation relevance.

For each proposed citation:

1. The structured response must identify a chunk belonging to the essay being evaluated and include the exact quoted text.
2. The backend verifies the quote occurs exactly once in the cited source chunk and matches the essay's extracted text at that location. Reject absent or ambiguous quotes. Never guess, paraphrase, fuzzy-match, or silently repair.
3. Compute extracted and normalized character offsets on the server, map them through Phase 4's `offset_alignment`, and include paragraph/page locations when available. DOCX/TXT do not have physical page numbers; legacy PDFs may lack reliable paragraph metadata.
4. Persist the quote, source chunk, offsets, and evaluation provenance. The frontend highlights the exact source span.
5. Describe this as “excerpt verified in essay,” not “claim verified.” Faculty reviews whether the excerpt supports the rubric judgment and approves before the student sees final results.

Use the same normalizer version as the stored essay. Preserve Phase 4's golden invariants: `normalized_text[start:end]` must equal the displayed quote, extracted offsets must map to the corresponding original text, and re-parsing unchanged input must produce stable offsets.

Tests use synthetic essays to cover exact and invented quotes, chunk/essay ownership, repeated quote ambiguity, stable offsets, paragraph/PDF page mapping, prompt injection, and student/faculty authorization. No embeddings, FAISS, entailment model, or live LLM is required for the default test suite.

---

## 9. Security architecture

| Layer | Control |
| --- | --- |
| Secrets | pydantic-settings; `.env.example` committed; `.env` gitignored |
| Passwords | Argon2id; login rate limit |
| Session | Access 15m; refresh rotated; logout revokes stored hash |
| RBAC | `require_role` + `can_access_essay` |
| Uploads | MIME + magic bytes; extension allowlist; size cap |
| Storage | UUID names; no path traversal; non-executable dir |
| Injection | §7.5 |
| IDOR | Authorize every GET/PATCH by ownership or course role |
| CORS | Explicit origins |
| Headers | Basic security headers; no enterprise security stack |
| Audit | Basic security-relevant application events; no enterprise audit pipeline |
| LLM | Essay goes only to the explicitly selected provider; never log secrets |

---

## 10. Phased implementation plan

Each phase: real code, tests, README notes. Later phases must not replace logic with stubs.

### Phase 1 — Repository setup

Layout, `.gitignore`, `.env.example`, Compose **postgres + redis**, FastAPI `/health`, Vite+Tailwind+Router shell, root README pointing at Windows setup (§15).

**Tests:** health; frontend mount smoke.

### Phase 2 — Backend foundation and database

SQLAlchemy foundation, PostgreSQL connection/session management, Alembic, settings, logging, and errors. Implement the `users` model and migration. Per the approved Phase 2 request, also deliver student registration, login, Argon2id password hashing, JWT access-token authentication, role dependencies, admin provisioning, first-admin bootstrap, and owner/admin profile authorization (auth subset originally listed in Phase 3). Other domain models remain with their feature phases.

**Tests:** user constraints and Argon2id persistence; registration/login; invalid credentials; unauthenticated access; role/ownership authorization; `alembic upgrade head` against PostgreSQL.

### Phase 3 — Authentication and authorization

**Implemented:** validated registration and login, Argon2id hashing, JWT access-token validation, rotating opaque refresh sessions, refresh-token family reuse detection/revocation, logout revocation, student/faculty/admin authorization, owner-scoped profile access, auth rate limits, and interactive seeding for missing role accounts. Alembic revision `0003_refresh_session_families` adds and backfills the refresh-session family ID without recreating existing tables.

**Tests:** registration validation, invalid credentials, token expiration, refresh rotation and family reuse revocation, logout family revocation, seed behavior, and role authorization.

### Phase 4 — Essay upload and document processing

**Implemented:** authenticated PDF/DOCX/UTF-8 TXT upload; extension/MIME/signature and request-size validation; bounded local storage using generated filenames; PDF/DOCX structural and active-content checks; PyMuPDF/python-docx/TXT extraction; versioned NFC/newline/smart-punctuation/whitespace normalization with compact reversible offset alignment; PDF page spans; spaCy sentence chunks with dual offsets; PostgreSQL persistence and student/course-faculty/admin authorization. Minimal course/enrollment associations are included only to scope faculty access. OCR, antivirus scanning, rubric evaluation, embeddings, and evidence retrieval are deferred.

**Tests:** generated PDF/DOCX/TXT fixtures; extraction accuracy; deterministic text/offset invariants; malformed, empty, unsupported, active-content, MIME/signature, and oversized file rejection; ownership/course authorization; storage failure handling.

### Phase 5 — Rubric management

**Implemented:** course-scoped faculty rubric creation, draft metadata editing, rubric/version retrieval, criterion replacement, and archival. Rubrics start with version 1 in draft. A new version copies the latest published criteria, and only one unpublished version may be open at a time. Publishing requires 1–100 valid criteria, `min_score < max_score`, unique criterion names and sort orders, score-level descriptors inside the score range, positive fractional weights summing to `1.0` (tolerance `0.000001`), then records an immutable metadata/criteria snapshot. Published versions are never edited; archive hides a rubric from students without deleting its versions. Students see only published versions for enrolled courses; faculty reads are course-scoped and mutations require rubric ownership. Admins have read-only global access. Rubric scoring and AI integration remain deferred.

**Tests:** course/owner authorization; draft editing; weight, score-range, level, and criterion-set validation; version cloning; publish snapshots and immutability; archive behavior; students see published versions only.

### Phase 6 — LLM integration and synchronous evaluation

**Implemented scope:** provider protocol, OpenAI adapter and factory; strict JSON-schema output; injection-guarded prompts; per-criterion scoring with separate malformed-JSON and score-range retry budgets; weighted totals and persisted AI scores pinned to an immutable rubric version. Missing key → explicit configuration failure.

**Scope differences:** the approved initial provider is OpenAI only; Gemini and embeddings are deferred. Evaluation is synchronous and does not create ARQ jobs. Student text is not included in system prompts. Results omit evidence citations, which are the priority for revised Phase 7.

**Tests:** mocked schema-valid JSON; invalid JSON retry; score-range rejection/retry; missing key; provider failures; authorization and result persistence.

### Phase 7 — Evidence-grounded results and explicit mock mode

**Implemented:** extended the synchronous Phase 6 evaluator without replacing its OpenAI path. Deterministic local lexical retrieval ranks existing essay chunks per criterion. Provider claims include exact excerpts tied to retrieved chunk IDs; backend validation rejects missing, ambiguous, or non-matching quotes, computes extracted/normalized character offsets, and returns paragraph/page locations where metadata supports them. Citation metadata distinguishes verified existence from unverified relevance. Unsupported claims are flagged. The explicit `LLM_PROVIDER=mock` provider is deterministic, uses no API key, and is labeled in the response and persisted evaluation mode; OpenAI errors do not fall back to mock.

**Database:** additive migration `0008_evidence_citations_mock` adds `evaluations.evaluation_mode` and `criterion_scores.claims_json`; applied to the configured PostgreSQL database. Alembic reports this revision as head and `alembic check` detects no model drift.

**Tests:** complete backend suite: 62 passed. Focused evaluation/evidence/document suite: 47 passed. Pylance diagnostics: no issues in checked modified source/test files. OpenAI adapter behavior is covered by mocked tests; no live OpenAI request was made. Recent PDF block extraction supports paragraph locations; older PDF records without block metadata may lack them.

### Phase 8 — Faculty review and approval

**Implemented:** course-enrolled faculty can list pending and changes-requested evaluations, inspect the existing evaluation detail (AI scores, feedback, evidence excerpts/verification/locations), append notes, and edit separate `faculty_*` criterion fields. Faculty scores are validated against the immutable criterion range; the faculty weighted total uses faculty overrides where present and AI scores for criteria not yet overridden. AI scores, AI feedback, and citations are never overwritten. Review events persist faculty ID, action, optional note, and timestamp. Supported transitions are `needs_review` → approved/rejected/changes_requested and `changes_requested` → approved/rejected/changes_requested. Approved and rejected evaluations are closed to further editing.

Students receive no criterion scores, feedback, citations, faculty notes, or review history before approval. After approval, students can view evaluation results; review notes/history remain faculty-only.

**Database:** additive migration `0009_faculty_review` adds separate faculty feedback columns and `evaluation_review_events`; no existing tables or user data are deleted.

**Tests:** course/role authorization; review queue scope; all review decisions; notes and reviewer/timestamp history; score-range validation and weighted faculty totals; AI fields unchanged by corrections; closed-state enforcement; student visibility before/after approval.

### Phase 9 — Functional React demonstration

**Implemented:** connected student registration/login, in-memory access-token handling with HttpOnly-cookie refresh and expiry handling, role-protected routes, responsive student course/submission dashboard, secure PDF/DOCX/TXT upload, published rubric-version selection, synchronous evaluation start/status/history, and approval-gated results. Exact citation offsets are checked against the loaded extracted essay text before highlighting; the UI presents verified excerpt existence separately from unverified relevance and displays citation locations. Mock evaluation provenance is prominently labeled.

Faculty can view the course-scoped review queue and review page, inspect AI scores/evidence, add notes, save separate criterion-level score/feedback overrides, view review history, and approve/reject/request changes. Student score visibility remains gated by approval. No backend architecture changes were made other than the authorized, paginated `GET /evaluations` history route with ownership/course filtering and unapproved student-result redaction. Faculty rubric authoring and an admin dashboard are not part of this phase.

**Verification:** 15 Vitest tests passed, including registration/login, role guards, refresh/expiry behavior, upload, evaluation mode labeling, exact evidence highlighting, student result redaction, failure messaging, and faculty correction/note/approval actions. `npx tsc --noEmit` passed; `npm run build` passed. The complete backend suite passed 67 tests. The route contract was checked against backend OpenAPI and backend tests; a live authenticated browser end-to-end flow was not run.

### Phase 10 — Synthetic local demo data and verification

Add repeatable synthetic users, course, published rubric, and essay fixtures. Never commit real user data, passwords, database credentials, or API keys. Update local instructions and remove unused Redis/ARQ/Gemini/embedding configuration from the demo setup. Verify migrations and the complete flow with mock mode; run an optional real OpenAI smoke only when configured.

**Tests:** clean local setup, synthetic seed repeatability, backend suite, frontend suite, safe mock/real-mode distinction, and documented Windows run commands.

---

## 11. Status machine (evaluations)

```
running → needs_review → approved
                              ↘ rejected
                              ↘ changes_requested → (faculty edit or rerun)
        running → failed
```

Students see scores/feedback only when `approved`. Faculty see all states. `queued` remains an unused compatibility value; no queue is planned.

---

## 12. Testing strategy

| Layer | Tools | Focus |
| --- | --- | --- |
| Unit | pytest | extractors, alignment, Gate A, score reject/retry, RBAC |
| API | pytest + httpx | auth, IDOR, rubric publish, review |
| Evaluation | pytest + httpx + mocked provider | scoring, explicit mock provenance, exact quote/offset validation, errors |
| Frontend | Vitest + Testing Library | login, upload, evaluation, citations, faculty review |

Default tests must pass without API keys or cloud access. Live OpenAI smoke is optional and only runs when a local key is configured.

### 12.1 Practical testing dataset

Phase 10 will add synthetic fixtures under `testdata/`; currently the directory contains only its README. Include a small set of original TXT essays and, where useful, equivalent generated PDF/DOCX files to exercise extraction. Add one rubric/course fixture and golden evidence annotations containing exact quotes and expected normalized offsets (plus expected PDF page where applicable). Seed accounts must have synthetic identities, with passwords supplied locally rather than checked into fixtures.

Use mocked provider responses for deterministic score-range, weighted-total, malformed-output, provider-error, and mock-provenance tests. Exact quote existence and offset mapping are deterministic tests against the golden essay text. Do not add entailment labels, claim semantic validation from exact matching, or use live LLM score agreement as a default test gate. An optional real OpenAI smoke may be run only with a configured key and must be reported separately from automated tests.

---

## 13. How this stays a functional product

- Evaluation runs synchronously through the explicitly selected OpenAI or mock provider.
- Mock outputs are unmistakably labeled and never used as an automatic fallback.
- Invalid scores are not stored.
- Invalid quotes are not student-facing citations.
- Faculty cannot overwrite `ai_*`.
- Offsets are tested against golden text, not assumed.
- Missing credentials are configuration errors, not sample JSON.

---

## 14. Local execution (no queue service)

The demonstration needs the local PostgreSQL service, FastAPI/Uvicorn, and Vite. The current Phase 6 evaluation route is synchronous; no Redis URL, queue, worker, or job-progress endpoint is required. The `queued` status value may remain for compatibility but is not part of the local workflow.

---

## 15. Original Windows setup steps (historical — do not use)

The original Windows setup below documents the earlier Redis/ARQ proposal and is not authoritative. For the revised local demo, use the scope amendment's PostgreSQL + Uvicorn + Vite workflow. Phase 10 must update the README and remove Redis/ARQ/Gemini/embedding setup instructions.

### 15.1 One-time software

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) and start it (Linux containers).
2. Install [Python 3.11+](https://www.python.org/downloads/) — check **Add python.exe to PATH**.
3. Install [Node.js 20 LTS](https://nodejs.org/) (includes npm).
4. Optional: [Git for Windows](https://git-scm.com/).

Verify:

```powershell
docker --version
docker compose version
python --version
npm --version
```

Python must print 3.11 or newer.

### 15.2 Project location

```powershell
cd "C:\Desktop\TheSMB\projects\Rubric-Grounded Essay Feedback with Evidence Citation"
```

### 15.3 Environment file

After Phase 1 creates `.env.example`:

```powershell
copy .env.example .env
notepad .env
```

The `.env` file lives in the **repo root**. `app/core/config.py` (pydantic-settings) is configured to load `../.env` relative to `backend/`, so commands run from `backend/` will find it automatically. Alembic's `env.py` does the same.

Set at least:

```
DATABASE_URL=postgresql+psycopg://essay:essay@localhost:5432/essay_eval
JWT_SECRET_KEY=change-me-to-a-long-random-string
JWT_REFRESH_SECRET_KEY=change-me-to-another-long-random-string
FILE_STORAGE_DIR=./data/files
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:5173
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

> **Note:** The Compose file (§15.4) creates the Postgres database `essay_eval` with user `essay` / password `essay` automatically. The `DATABASE_URL` above matches those defaults. `FILE_STORAGE_DIR` can be a relative path (resolved from repo root) or absolute.

To use Gemini instead, set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=...` and omit the OpenAI key. You only need **one** provider.

**Frontend environment** (optional — Vite proxy handles most cases):

```powershell
# frontend/.env.local (created automatically in Phase 10 if needed)
VITE_API_URL=http://127.0.0.1:8000
```

Create the file storage directory:

```powershell
New-Item -ItemType Directory -Force -Path .\data\files
```

### 15.4 Start PostgreSQL and Redis (Docker)

The Phase 1 `docker-compose.yml` at the repo root will define these services:

```yaml
# Expected service configuration (created in Phase 1)
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: essay
      POSTGRES_PASSWORD: essay
      POSTGRES_DB: essay_eval
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U essay -d essay_eval"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 5

volumes:
  pgdata:
```

From the repo root:

```powershell
docker compose up -d postgres redis
docker compose ps
```

Wait until both show `healthy`. Logs:

```powershell
docker compose logs -f postgres
docker compose logs -f redis
```

Stop later with `docker compose stop postgres redis`. Data persists in named volumes unless you run `docker compose down -v` (destroys DB).

### 15.5 Backend: virtualenv, dependencies, spaCy model

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m spacy download en_core_web_sm
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again.

### 15.6 Database migrations

With venv active and Postgres up:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

Optional seed (creates accounts only for roles not already represented; passwords are prompted without echo):

```powershell
python -m app.scripts.seed
```

### 15.7 Run the API

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/docs`.

### 15.8 Run the ARQ worker (required for evaluations)

**Second PowerShell window:**

```powershell
cd "C:\Desktop\TheSMB\projects\Rubric-Grounded Essay Feedback with Evidence Citation\backend"
.\.venv\Scripts\Activate.ps1
arq app.worker.WorkerSettings
```

Leave it running. You should see it connect to Redis. From Phase 7, upload + “evaluate” will not finish unless this process is up.

Re-run the same command after code changes (or rely on a documented `--watch` if added later). One worker is enough on a laptop.

### 15.9 Frontend: dependencies and dev server

**Third PowerShell window:**

```powershell
cd "C:\Desktop\TheSMB\projects\Rubric-Grounded Essay Feedback with Evidence Citation\frontend"
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite proxy / `VITE_API_URL` will point at `http://127.0.0.1:8000`.

### 15.10 Tests

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

Optional live calibration (needs LLM key):

```powershell
pytest tests/verification/test_calibration.py --run-calibration
```

Frontend:

```powershell
cd frontend
npm test
```

### 15.11 Typical four-terminal layout

| Window | Command |
| --- | --- |
| A | `docker compose up -d postgres redis` (once) |
| B | `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` |
| C | `arq app.worker.WorkerSettings` |
| D | `npm run dev` |

### 15.12 Full stack via Docker (later / production-like)

When Phase 13 images exist:

```powershell
cd "C:\Desktop\TheSMB\projects\Rubric-Grounded Essay Feedback with Evidence Citation"
docker compose --profile full up --build
```

MVP daily work should keep using §15.4–15.9 so Python/TS reload stays fast.

### 15.13 Common Windows problems

| Symptom | What to do |
| --- | --- |
| Port 5432 in use | Another Postgres is installed locally; stop it or change Compose port and `DATABASE_URL` |
| Docker is not running | Start Docker Desktop and wait until it is idle |
| `Activate.ps1` disabled | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| spaCy model missing | `python -m spacy download en_core_web_sm` |
| Jobs stuck `queued` | Worker window not running or Redis down |
| `LLM_NOT_CONFIGURED` | Set `LLM_PROVIDER` and that provider’s key in `.env`, restart API **and** worker |
| `QUEUE_UNAVAILABLE` | `docker compose up -d redis` |

---

## 16. Changelog (architecture review)

### Review 1 (prior revision)

1. Kept full architecture and all major features (modules, ERD, APIs, security, 13 phases).
2. Added **§2.5 MVP vs production enhancements** so hardening (S3, dual providers, ClamAV, CI, local NLI, HA Redis, partial eval) is explicit and does not block a working product.
3. Added **§2.6 simplified local workflow**: Compose only for Postgres+Redis; native Uvicorn, one ARQ worker, Vite; batched phase execution without dropping phases.
4. Kept **Redis + ARQ**; documented local behavior (§14) and exact Windows commands (§15.4, §15.8).
5. **Evidence:** Gate A is mandatory exact substring match. Gate B is independent **entailment** (`entailment|neutral|contradiction`). Cosine/FAISS is retrieval + diagnostics only, never proof of support.
6. **Removed** the assumed **0.55** cosine threshold as a decision rule. Calibration uses `testdata/verification` gold labels; live calibration is opt-in; CI uses fixtures.
7. **Scoring:** invalid or out-of-range scores are **rejected and retried**, then fail the evaluation. **No silent clamp** (including faculty PATCH).
8. **Text consistency:** `extracted_text`, versioned `normalized_text`, `offset_alignment`, dual offsets on chunks, golden invariants (§8.5). Schema updated (`normalizer_version`, `offset_alignment`, `extracted_char_*`, entailment fields).
9. Defined **`testdata/`** with three essays, one rubric, instructor scores, evidence annotations, and entailment gold files (§12.1).
10. **One configured LLM provider** at runtime; both adapters exist; factory selects one; unused adapter tested with mocks.
11. Added **beginner Windows setup** (§15).
12. Added **exact commands** for Docker infra, venv, pip, spaCy, Alembic, Uvicorn, ARQ, npm, pytest.

### Review 2 (final architecture review — this pass)

13. **§0 Table of Contents** expanded to list all sections individually (§3–§16); previously compressed entries like "3–6" and "12–12.1" are now explicit.
14. **§2.1 diagram:** removed `NLTK` reference (only spaCy is used throughout).
15. **§3.1 `evidence_citations` schema:** added `extracted_char_start`, `extracted_char_end` (dual offsets matching `essay_chunks`, required by §8.1 step 4 and §8.5 rule 5) and `reason` (stores the LLM's explanation from §7.3 output schema).
16. **§3.2 constraints:** expanded Citations entry to document all new columns (`extracted_char_*`, `reason`, `claim_span`).
17. **§4 backend folder structure:** added `app/scripts/seed.py` (referenced by §15.6) and `tests/verification/test_calibration.py` (referenced by §15.10).
18. **§5 status badges:** replaced `unsupported_flags` (a boolean field, not a status) with `changes_requested` (actual status from §11); added note that `has_unsupported_flags` renders as a warning indicator.
19. **§7.3 retry budget:** clarified that JSON-repair retries (max 1) and score-range retries (max 2) have **separate** counters per criterion.
20. **§8.7 implementation clarifications (new section):** resolved 7 ambiguities:
    - Document parsing is synchronous (Phase 4); ARQ not needed until Phase 7
    - FAISS index is per-essay, ephemeral, rebuilt from DB
    - Zero-quote claims handling and `has_unsupported_flags`
    - Feedback LLM re-verification: failed quotes stripped, not retried
    - Student visibility: scores/feedback redacted until `approved`
    - `course_id` optional: standalone essays/rubrics have owner-only access
    - `LLMClient` protocol covers both `chat()` and `embed()`
21. **§15.3 environment file:** documented `.env` loading path (`../.env` from `backend/`), replaced hardcoded `FILE_STORAGE_DIR` with relative path, added Postgres credential note, added `VITE_API_URL` for frontend.
22. **§15.4 Docker Compose:** added expected `docker-compose.yml` service definitions (postgres:16-alpine, redis:7-alpine, healthchecks, named volumes, ports, credentials).
23. **§15.11:** renamed from "three-window" to "four-terminal" layout (the table has 4 entries).

### Review 3 (portfolio scope revision — 2026-11-25)

24. Reframed the project as a local learning/academic/portfolio demonstration and made this scope amendment authoritative for remaining phases.
25. Kept completed Phases 1–6 history and the current FastAPI, React/Vite, PostgreSQL, auth, upload, rubric, and OpenAI evaluation implementation.
26. Replaced the remaining Redis/ARQ, embedding/FAISS, analytics, reporting, and deployment plan with evidence-grounded evaluation, explicit mock provenance, faculty approval, a connected React workflow, and synthetic local demo data.
27. Recorded current gaps: no live OpenAI verification because no non-empty key was loaded; no published test rubric in the local database; no citation verification service, mock provider, faculty review API, functional UI, or synthetic fixtures yet.

**Current defaults:** local PostgreSQL; synchronous requests; local files; OpenAI only when explicitly configured; mock mode only when explicitly selected and labeled; no distributed infrastructure or cloud services.

Phase 1 is already delivered and verified. Do not recreate or rewrite it; proceed with later phases only after approval.
