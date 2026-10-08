# VikatHire

VikatHire is an evidence-driven candidate screening service. Deterministic
matching, evaluation, scoring, and policy remain authoritative; the API only
invokes the screening graph and presents its stored results. The separate
research scoring specification is still **REQUIRES HUMAN APPROVAL** and is not
part of candidate screening.

## Local setup

Requirements: Python supported by `pyproject.toml` and PostgreSQL with a
database created for VikatHire.

```bash
uv sync
cp .env.example .env
```

Fill required configuration in `.env` with deployment-approved values. The
application does not create the PostgreSQL database itself. On startup it runs
the official LangGraph PostgreSQL checkpointer's idempotent `setup()` migrations
and creates the screening-ID uniqueness table. The PostgreSQL account therefore
needs permission to create and update those tables.

Start the service:

```bash
uv run uvicorn vikat_hire.app.main:app --host 127.0.0.1 --port 8000
```

### Next.js frontend

The TypeScript App Router frontend lives in `frontend/`. It calls the FastAPI
backend through same-origin Next.js route handlers, so the backend URL stays
server-side and no provider credential is exposed to the browser.

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Set `VIKATHIRE_API_BASE_URL` in `frontend/.env.local` to the reachable FastAPI
origin if it is not `http://127.0.0.1:8000`. For a production frontend, build
and serve with `npm run build` and `npm run start`. Configure the deployment
proxy/load balancer with a request-body limit no larger than the API's
`VIKATHIRE_API_MAX_REQUEST_BYTES`.

Importing the app does not connect to PostgreSQL. Required settings and durable
resources are validated/opened during application lifespan startup; missing or
invalid configuration prevents startup.

## Configuration

`.env.example` lists the supported variable names without credentials.

Required settings:

| Variable | Purpose |
| --- | --- |
| `VIKATHIRE_APP_NAME` | FastAPI application title |
| `VIKATHIRE_ENVIRONMENT` | Deployment environment label |
| `VIKATHIRE_LOG_LEVEL` | Logging level label |
| `VIKATHIRE_DATABASE_URL` | PostgreSQL/psycopg connection URI |
| `VIKATHIRE_APIFY_API_TOKEN` | Apify credential for LinkedIn retrieval |
| `VIKATHIRE_APIFY_LINKEDIN_ACTOR_ID` | Configured Apify LinkedIn actor |
| `VIKATHIRE_GROQ_API_KEY` | Groq credential for advisory/explanation operations |
| `VIKATHIRE_GROQ_MODEL` | Configured Groq model |
| `VIKATHIRE_JD_TECHNICAL_INDICATORS` | Approved comma-separated technical JD indicators |
| `VIKATHIRE_JD_NON_TECHNICAL_INDICATORS` | Approved comma-separated non-technical indicators |
| `VIKATHIRE_JD_CLASSIFICATION_CONFIGURATION_REF` | Classification configuration identity |
| `VIKATHIRE_POLICY_CONFIGURATION_REF` | Policy configuration identity |
| `VIKATHIRE_POLICY_CERTIFICATION_PRESENT` | Existing certification gate configuration |
| `VIKATHIRE_POLICY_EDUCATION_PRESENT` | Existing education gate configuration |
| `VIKATHIRE_POLICY_LOCATION_PRESENT` | Existing location gate configuration |
| `VIKATHIRE_POLICY_AVAILABILITY_PRESENT` | Existing availability gate configuration |

Optional/configurable operational values are `VIKATHIRE_GITHUB_API_TOKEN`,
`VIKATHIRE_GROQ_TEMPERATURE`, `VIKATHIRE_GROQ_MAX_TOKENS`,
`VIKATHIRE_API_MAX_REQUEST_BYTES`, `VIKATHIRE_NETWORK_TIMEOUT_SECONDS`,
`VIKATHIRE_APIFY_TIMEOUT_SECONDS`, `VIKATHIRE_APIFY_POLL_INTERVAL_SECONDS`,
`VIKATHIRE_POSTGRES_POOL_MIN_SIZE`, and
`VIKATHIRE_POSTGRES_POOL_MAX_SIZE`. The checked-in example contains safe
non-secret defaults where the code defines them. Do not commit `.env` or put
provider secrets in domain contracts or graph state.

GitHub retrieval uses the GitHub REST API and accepts public profiles,
organizations, and repositories. The GitHub token is optional. Portfolio
retrieval fetches the supplied public HTTP(S) page with bounded time, response
size, and redirect count; it does not invent portfolio data when a page cannot
be fetched. LinkedIn retrieval uses the configured Apify actor. External
provider failures propagate through the existing collection error boundary.

## API

The browser uses multipart uploads through the frontend BFF. Raw bytes are
sent only to the extraction boundary; `DocumentInput` stores metadata and
identity, not bytes. The frontend creates no extraction blocks and performs
no screening calculations. For API clients, `POST /screenings` also accepts
the existing typed JSON/base64 request contract. The maximum whole-request
body size is configured by `VIKATHIRE_API_MAX_REQUEST_BYTES`; oversized
requests receive HTTP 413 and are never silently truncated.

### `POST /screenings`

Starts a screening. Request JSON contains `screening_input` and may include
`jd_content` and `resume_content` as base64-encoded bytes. The frontend uses
`POST /screenings/upload` with multipart `screening_id`, `jd_file`,
`resume_file`, and optional external-profile URLs plus explicit authorization
checkboxes. Upload metadata and SHA-256 hashes are generated by the backend.
The graph interrupts when required document content is absent. A normal
execution returns HTTP 200; an execution waiting for required input returns
HTTP 202 with the authoritative report and an `interruption` object. Reusing a
screening ID returns HTTP 409.

### `POST /screenings/{screening_id}/resume`

Resumes an interrupted screening with `screening_input` and typed extracted
blocks as defined by the API request contract. A mismatched path/payload ID or
a screening that is not awaiting input returns HTTP 409. Unknown IDs return
HTTP 404; malformed input returns HTTP 422.

The browser resume flow uses `POST /screenings/{screening_id}/resume-upload`
with multipart `jd_file` and/or `resume_file`. It accepts only documents
currently requested by the interrupted checkpoint and requires all currently
missing document files in one resume request. Extraction is performed by the
existing backend extractors; clients do not submit normalized blocks.

### `GET /screenings/{screening_id}`

Returns the report projected from the graph's persisted state. Unknown IDs
return HTTP 404. The API/report layer does not recalculate dimensions, score,
eligibility, or policy.

### Operational endpoints

* `GET /health` is process health and does not call external providers.
* `GET /readiness` checks that the graph/checkpointer is initialized and that
  PostgreSQL is reachable; it returns HTTP 503 when not ready.

Unexpected errors return a generic HTTP 500 response; provider exception
messages and credentials are not returned to clients. API authentication is
not specified by the repository; deploy behind the deployment's approved
authentication/network boundary.

## Persistence and restart behavior

The official `langgraph-checkpoint-postgres` `PostgresSaver` is the authoritative
execution/checkpoint store. It uses the configured PostgreSQL database, is
initialized once during application startup, and is closed during shutdown.
LangGraph's `thread_id` is the screening ID, so interrupted executions can be
read and resumed after an application restart when connected to the same
database. Raw JD/resume bytes are not written to `ScreeningState` by the API.

A separate PostgreSQL table contains only reserved screening IDs and a
uniqueness constraint. Its atomic insert prevents concurrent duplicate
screening creation; graph execution state remains solely in LangGraph's
checkpoint tables. IDs are retained indefinitely because this repository has no
approved screening deletion/retention policy. LangGraph checkpoints likewise
have no automated retention policy configured; operators must account for that
in database retention and backup procedures. The existing domain
`CheckpointStore` and `ScreeningStateStore` protocols are not wired as competing
state stores.

Production requires PostgreSQL connectivity and the required provider/config
settings. The app does not bootstrap a database server, create a database/user,
or configure deployment authentication. Tests may use `MemorySaver` for fast
unit coverage; the PostgreSQL restart integration test uses a real PostgreSQL
instance and is enabled with `VIKATHIRE_TEST_DATABASE_URL`.
