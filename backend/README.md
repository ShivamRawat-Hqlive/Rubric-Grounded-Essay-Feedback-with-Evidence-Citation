# Backend (Phase 5)

FastAPI service with PostgreSQL persistence, authentication, role-protected course membership, secure essay uploads, synchronous PDF/DOCX/TXT text extraction, and course-scoped rubric authoring. Copy the repository-root `.env.example` to `.env`, set a PostgreSQL role/password/database that already exist on the server, configure `JWT_SECRET_KEY` with at least 32 random bytes, and start PostgreSQL before running migrations.

```powershell
cd "C:\Desktop\TheSMB\projects\Rubric-Grounded Essay Feedback with Evidence Citation"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m app.scripts.create_admin
# Optional: interactively create accounts for any missing roles
python -m app.scripts.seed
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pytest
```

`GET /health` remains a database-independent liveness endpoint. Interactive API documentation is available at `/docs`. The Compose example credentials initialize a new Compose volume only; they do not change credentials on an installed local PostgreSQL service.
Set a random `JWT_SECRET_KEY` of at least 32 bytes in `.env` before using login. The first admin is created once through the interactive command above; it refuses to create another admin if one already exists.

## Authentication API

- `POST /api/v1/auth/register` accepts `email`, `password`, and `full_name`. Public registration always creates a student; unknown fields such as `role` are rejected.
- `POST /api/v1/auth/login` accepts `email` and `password`, returns `access_token`, `token_type`, and `expires_in`, and sets a refresh cookie.
- `POST /api/v1/auth/refresh` rotates the HttpOnly refresh cookie and issues a new access token.
- `POST /api/v1/auth/logout` revokes the matching refresh-token family and clears the cookie.
- `GET /api/v1/auth/me` requires `Authorization: Bearer <access_token>`.
- `GET /api/v1/users/{user_id}` permits the user to view their own profile; admins may view any profile.
- `GET /api/v1/admin/users` and `POST /api/v1/admin/users` require the admin role. Admin provisioning accepts `email`, `password`, `full_name`, and `role` (`student`, `faculty`, or `admin`).

Registration and login return generic conflict/credential errors; password values are never returned or persisted in plaintext. Passwords are hashed with Argon2id. Access tokens are signed using `JWT_SECRET_KEY`. The login response contains only the access token; the refresh token is carried exclusively in the HttpOnly cookie.
Refresh tokens are high-entropy opaque values; only SHA-256 hashes are persisted. Rotation invalidates the previous token while retaining its family ID. Reuse of a revoked token revokes that entire family, and logout revokes the family. Cookie settings are HttpOnly, SameSite=Strict, and auth-path scoped; set `REFRESH_COOKIE_SECURE=true` for HTTPS. Logout revokes the refresh cookie even after the access token expires. Auth limits are 5 registrations/minute, 10 logins/minute, and 20 refreshes/minute per client IP and API process.

The optional `python -m app.scripts.seed` command prompts without echoing passwords and creates accounts for each missing role (student, faculty, admin) in a single transaction. It does not reset or replace existing accounts.

For local development, create a separate faculty account with `python -m app.scripts.create_faculty` from `backend/`. The command prompts for the faculty name, email, and password (without echo), uses the existing password hashing and database session services, and refuses duplicate email addresses. Public registration continues to create student accounts only.

`POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` configure both SQLAlchemy and the Compose PostgreSQL service. The installed local PostgreSQL service has its own existing roles/passwords: `.env.example` does not reset or synchronize them. Use a dedicated database role and configure its valid credentials in the ignored root `.env`.

`FILE_STORAGE_DIR` defaults to `./data/files` (resolved relative to the repository root). `MAX_UPLOAD_MB` defaults to 10 and `MAX_EXTRACTED_CHARS` defaults to 500,000; both limits can be set in the repository-root `.env`. Migration `0004_essay_upload_and_courses` adds the course membership and essay/chunk tables. Migration `0005_rubric_management` adds rubric, version, and criterion tables.

## Phase 4 course and essay API

- `POST /api/v1/courses` creates a course for faculty/admin; faculty creators receive faculty membership.
- `POST /api/v1/courses/{course_id}/enrollments` lets course faculty enroll students; admins can enroll students or faculty.
- `GET /api/v1/courses` and `GET /api/v1/courses/{course_id}` are limited to members, except admins can view all courses.
- `GET /api/v1/courses/available` lets students list active courses they have not joined; `POST /api/v1/courses/{course_id}/self-enrollment` enrolls only the authenticated student.
- `POST /api/v1/essays` accepts multipart `file` and optional `course_id`; only authenticated students can upload, and a supplied course must include their student enrollment.
- `GET /api/v1/essays`, `GET /api/v1/essays/{essay_id}`, and `GET /api/v1/essays/{essay_id}/text` enforce student ownership, faculty course membership, or admin access. Unauthorized records are returned as 404 to avoid disclosing their existence.

The upload allowlist requires matching `.pdf` / `application/pdf`, `.docx` / the OOXML DOCX MIME type, or `.txt` / `text/plain`; PDF and DOCX signatures/packages are checked, and TXT must contain valid UTF-8 text. Encrypted/active PDFs, DOCX macro/embedded-object packages, oversized archives, corrupt documents, and documents without extractable text are rejected. Originals are stored under generated UUID filenames; original paths are never returned by the API.

PDF pages carry 1-based page numbers and extracted/normalized half-open character spans. DOCX and TXT are returned with a whole-document span and `page_number: null`, because these text extractors do not perform pagination. Optional OCR is available for scanned pages using Microsoft TrOCR. It is disabled by default and remains separate from native PDF, DOCX, TXT, and attachment handling. `GET /essays/{essay_id}/text` returns the raw extract, normalized text, compact offset alignment, and page metadata, including extraction method and page-level offsets.

## Phase 5 rubric API

- `POST /api/v1/rubrics` creates a draft rubric and its first draft version. The authenticated faculty member must be enrolled in the selected course.
- `GET /api/v1/rubrics` and `GET /api/v1/rubrics/{rubric_id}` are course-scoped for faculty. Students see only published rubrics in their enrolled courses. Admins can read all rubrics.
- `PATCH /api/v1/rubrics/{rubric_id}` updates metadata only while the rubric is a draft and only for its faculty owner.
- `POST /api/v1/rubrics/{rubric_id}/versions` creates the next draft version by copying the latest published criteria. Only one unpublished version may be open at a time.
- `GET /api/v1/rubrics/{rubric_id}/versions` returns versions to course faculty and only published versions to enrolled students. `GET /api/v1/rubric-versions/{version_id}` applies the same access rules.
- `PUT /api/v1/rubric-versions/{version_id}/criteria` replaces all criteria in an unpublished version. Criteria require a description, `min_score < max_score`, positive weight, unique name/order, and optional score-level descriptors within the score range. A version has 1–100 criteria and weights are fractional values summing to `1.0` (within `0.000001`).
- `POST /api/v1/rubric-versions/{version_id}/publish` requires valid criteria and freezes a snapshot of the rubric metadata and criteria. Published versions cannot be edited; later versions are separate drafts.
- `POST /api/v1/rubrics/{rubric_id}/archive` archives a rubric without deleting its versions. Archived rubrics are hidden from students and cannot be changed or republished. Only the faculty owner may archive; admins have read-only rubric access.

The version snapshot preserves decimal scores and weights as strings to avoid loss of precision. Rubric management does not calculate essay scores or invoke an LLM; scoring and AI integration remain out of scope until later phases.

## Optional OCR

Install the optional handwritten recognition dependencies:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-ocr.txt
```

Enable OCR in the repository-root `.env`:

```text
OCR_ENABLED=true
OCR_PROVIDER=trocr
OCR_MODEL_ID=microsoft/trocr-base-handwritten
OCR_DEVICE=cpu
```

The provider is lazy-loaded, so native PDF/DOCX/TXT processing does not download or load TrOCR. The first scanned-page upload may download the Hugging Face model. CPU inference is slow and is a local demonstration feature, not a production handwriting service.
