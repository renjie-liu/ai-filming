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

## Setup: one API key

Connect a Neon database and a Blob store to the project (both from the project's
**Storage** tab), then add **one** environment variable:

| Variable | Notes |
| --- | --- |
| `SEEDDANCE_API_KEY` | Your Seedance / ModelArk API key. `SEEDANCE_API_KEY`, `ARK_API_KEY`, `MODELARK_API_KEY`, `BYTEPLUS_API_KEY` and `VOLCENGINE_API_KEY` also work. |

Nothing else is needed. On the first start (and whenever the key changes) the app:

1. works out which region the key belongs to (BytePlus ModelArk or Volcengine Ark)
   with a read-only call;
2. picks the first text, image and video model **enabled on your account**. Each
   candidate model gets a deliberately incomplete request, so nothing is generated
   or billed;
3. creates the provider and models and sets them as defaults, then caches the result
   in the database so later starts don't call Ark again.

Users never enter an API key in the app. Model Management shows the provider as
"Managed by deployment".

`DATABASE_URL` / `POSTGRES_URL` and `BLOB_READ_WRITE_TOKEN` are injected automatically
when the Neon database and Blob store are connected.

<details>
<summary>Optional overrides</summary>

| Variable | Notes |
| --- | --- |
| `ARK_BASE_URL` | Force a region endpoint instead of auto-detecting it. |
| `ARK_TEXT_MODEL` / `ARK_IMAGE_MODEL` / `ARK_VIDEO_MODEL` | Force specific model IDs. If the current default is still the auto-created model, it switches on the next cold start. Defaults picked in the UI are never overwritten. |
| `TASK_EXECUTION_MODE` | `inline` (default on Vercel) or `celery`. In `celery` mode on Vercel, tasks go to Vercel Queues and are consumed by the `worker:app` subscriber. That path is untested on a Services deployment. |
| `BLOB_ACCESS` | `public` (default) or `private`. |

</details>

Without a database URL the API falls back to an ephemeral SQLite file in `/tmp`
(smoke tests only: data is lost and is not shared between instances).

## Health check

`GET /api/v1/_deploy/status` reports the database dialect and row counts, the
storage backend, the Celery broker scheme, the bootstrap result, and the configured
Ark models. Add `?probe_ark=true` to make read-only calls to the Ark API
(list models / list video tasks; these don't generate anything or cost money).
Add `?probe_models=true` to check which candidate Seed / Seedream / Seedance models
your account has activated. Each model gets a deliberately incomplete request:
`available` means the model rejected the parameters (so it is enabled), and
`unavailable` means not found / not activated. No generation is billed. The
`/models` catalogue lists models that may not be activated on your account.
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
