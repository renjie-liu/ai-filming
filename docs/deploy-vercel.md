# Deploying Jellyfish on Vercel

This fork runs the whole stack in a single Vercel project using
[Vercel Services](https://vercel.com/docs/services):

| Piece | Upstream (Docker Compose) | On Vercel |
| --- | --- | --- |
| Frontend (`front/`) | nginx | `web` service (Vite static build) |
| API (`backend/`) | uvicorn | `api` service (FastAPI on Vercel Functions) |
| Task workers | Celery + Redis | **In-process** inside the API function (`TASK_EXECUTION_MODE=inline`, kept alive with `wait_until`). Optional: Celery on Vercel Queues (`TASK_EXECUTION_MODE=celery`, subscriber `backend/worker.py`) |
| Database | MySQL | **Postgres** (Neon via Vercel Marketplace) |
| Object storage | RustFS / S3 | **Vercel Blob** (public store) |
| DB init / seed SQL | init containers | `app/deploy_bootstrap.py` on cold start (idempotent) |

Routing is defined in `/vercel.json`: `/api/*`, `/docs`, `/openapi.json` go to the
API service; everything else goes to the SPA.

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` or `POSTGRES_URL` | yes | Injected automatically when a Neon database is connected to the project. `postgres://…` URLs are normalized to `postgresql+psycopg://…`. |
| `BLOB_READ_WRITE_TOKEN` | yes | Injected automatically when a Blob store is connected. |
| `SEEDDANCE_API_KEY` (or `ARK_API_KEY`) | recommended | Ark / BytePlus ModelArk API key. On startup the app creates provider `ark-seedance` with a text, image and video model and sets them as defaults (only if no default is set yet). |
| `ARK_BASE_URL` | optional | Defaults to BytePlus ModelArk `https://ark.ap-southeast.bytepluses.com/api/v3`. Use `https://ark.cn-beijing.volces.com/api/v3` for Volcengine (China); model defaults switch to the `doubao-*` names automatically. |
| `TASK_EXECUTION_MODE` | optional | `inline` (default on Vercel) or `celery`. In `celery` mode on Vercel, tasks go to Vercel Queues and are consumed by the `worker:app` subscriber. That path is untested on a Services deployment. |
| `ARK_TEXT_MODEL` / `ARK_IMAGE_MODEL` / `ARK_VIDEO_MODEL` | optional | Override the default Seed / Seedream / Seedance model IDs. They can also be changed in the UI under model management. |

Without a database URL the API falls back to an ephemeral SQLite file in `/tmp`
(smoke tests only: data is lost and is not shared between the API and worker functions).

## Health check

`GET /api/v1/_deploy/status` reports the database dialect and row counts, the
storage backend, the Celery broker scheme, the bootstrap result, and the configured
Ark models. Add `?probe_ark=true` to make read-only calls to the Ark API
(list models / list video tasks; these don't generate anything or cost money).
No secrets are returned.

`GET /api/v1/_deploy/selftest` dispatches a test job the same way real generation
jobs are dispatched (inline or Celery). By default the job calls no model provider,
so it costs nothing. Add `?llm=true` to also send one tiny request to the default text
model; this checks the Ark key from the job's runtime. The response returns a `token`. Then
`GET /api/v1/_deploy/selftest/{token}` shows `done: true` once the worker function has
run it and written its result to the database.

## Notes and limits

- Generation jobs run inside the API function after the response is sent and are
  bounded by the function max duration (300 s on Hobby). If a job outlives that limit,
  it stays in `running` state.
- Task cancellation works through the database `cancel_requested` flag. Celery
  `revoke` broadcasts are not supported on Vercel Queues.
- Blob URLs are public but unguessable (generated files use UUID keys). Set
  `BLOB_ACCESS=private` with a private store if you need stricter access.
- Preview deployments are protected by Vercel Authentication by default. Production
  deployments on the Hobby plan are public, so anyone with the URL can spend your
  Ark credits.
