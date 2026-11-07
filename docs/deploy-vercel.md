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

1. works out which region the key belongs to with a read-only call: BytePlus ModelArk
   Asia (Johor, `ark.ap-southeast.bytepluses.com`), BytePlus ModelArk Europe (Dublin,
   `ark.eu-west.bytepluses.com`) or Volcengine Ark (`ark.cn-beijing.volces.com`).
   BytePlus API keys, model activation and billing are separate per region, and the
   Europe region currently offers only chat and image generation, not Seedance video;
2. picks a text, image and video model **enabled on your account**. For video it
   chooses the **newest Seedance** in your account's catalogue (currently Seedance 2.5,
   `dreamina-seedance-2-5-260628`): newest version first, flagship before fast/mini.
   Each candidate gets a deliberately incomplete request (no messages / no prompt / no
   content), which is rejected before anything is generated, so nothing is billed;
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
`available` means the model rejected the parameters (so it is enabled),
`unavailable` means not found / not activated, and `overdue` means Ark refused the
request because the account has an overdue balance (`AccountOverdueError`; Ark checks
this before validating parameters, so every enabled model reports it). No generation
is billed. With both flags set, the same probes also run in every other region that
accepts the key (`model_availability_other_regions`). The
`/models` catalogue lists models that may not be activated on your account.
No secrets are returned.

`GET /api/v1/_deploy/selftest` dispatches a test job the same way real generation
jobs are dispatched (inline or Celery). By default the job calls no model provider,
so it costs nothing. Add `?llm=true` to also send one tiny request to the default text
model; this checks the Ark key from the job's runtime. The response returns a `token`. Then
`GET /api/v1/_deploy/selftest/{token}` shows `done: true` once the worker function has
run it and written its result to the database.

## Notes and limits

- Seedance 2.x requests differ from 1.x (per BytePlus's Dreamina Seedance 2.5 tutorial and
  errors returned by the live ModelArk API): in first-frame / first-and-last-frame mode the
  output ratio follows the first frame, so `ratio` is sent as `adaptive` (a fixed ratio is
  rejected). Text-only requests keep the project ratio. Key frames are sent as
  `reference_image` (2.x rejects the `key_frame` role). `duration` is clamped to 4–30 s on
  Seedance 2.5 and 4–15 s on the 2.0 series.
- Seedance 2.x can only be activated and used while the account meets BytePlus's threshold
  (USD 30 in Credits, a USD 30+ AI Savings Plan, or a Seedance resource pack). Usage is
  deducted from the resource pack, then the Savings Plan, then the account balance; when
  the balance goes negative, Ark answers every model with `AccountOverdueError`.

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

## Troubleshooting: Blob store suspended (`limits-exceeded-suspended`)

Symptom: uploads return 503 and every image / video task fails with
`Blob storage unavailable … BlobStoreSuspendedError`; the creator page shows
「素材存储（Vercel Blob）已超出免费额度被暂停」. The store itself reports
`status: limits-exceeded-suspended` / `usageQuotaExceeded: true`
(Vercel dashboard → Storage → the Blob store, or `GET /api/v1/_deploy/status`
plus the Vercel API).

Cause: the Hobby plan's included Blob usage for the month was used up (generated
videos are 4–9 MB each and every board refresh loads thumbnails).

Fixes, pick one:

1. Upgrade the Vercel team to Pro (the store resumes automatically).
2. Wait for the monthly usage reset.
3. Point the backend at any S3-compatible bucket instead of Blob: set
   `S3_ENDPOINT_URL`, `S3_REGION_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
   `S3_BUCKET_NAME` (and `S3_PUBLIC_BASE_URL` for a public CDN host) in the
   project environment and redeploy; `storage_backend` in `/_deploy/status`
   switches to `s3`. Cloudflare R2's free tier (10 GB) is enough for hobby use.
   Files already stored in Blob stay readable through their public URLs.

## Troubleshooting: Neon quota exceeded (every API call returns 503)

Symptom: every API request fails; the response is
`503 Database quota exceeded: Neon 数据库已超出免费额度…` and the creator page shows
「数据库（Neon）已超出免费额度」. Runtime logs contain
`psycopg.OperationalError … ERROR: Your account or project has exceeded the quota.
Upgrade your plan to increase limits.` (the static frontend still loads).

Cause: the Neon free plan's monthly compute / data-transfer allowance for the
project was used up (board polling every 3 s while tasks run adds up).

Fixes, pick one:

1. **Create a second Neon database on the same free installation** (the free
   plan's 100 CU-hours are *per Neon project*, so a new one starts with a fresh
   allowance): Vercel dashboard → Storage → Create Database → Neon → connect to
   `ai-filming`, then disconnect the exhausted one and redeploy. Via the REST API
   (what was done on 2026-11-07):
   `POST /v1/integrations/billing/authorization` (plan `free_v3`, product
   `neon`) → `POST /v1/storage/stores/integration` with the `authorizationId` →
   `DELETE /v1/storage/stores/{old}/connections/{spc_…}` →
   `POST /v1/storage/stores/{new}/connections` `{projectId, envVarEnvironments}`
   → push or redeploy. The new database starts empty: tables, prompts and the
   Ark provider are recreated by `ensure_bootstrapped` on first start, works are
   not migrated (the old project stays readable once its quota resets).
2. Upgrade the Neon installation (Launch plan, pay per CU-hour); connections
   resume immediately and the data is kept.
3. Wait for the monthly reset.
4. Point `DATABASE_URL` at another Postgres (any provider) and redeploy.

Reduce usage: Neon bills compute while the endpoint is awake and suspends it
after 5 idle minutes, so what matters is how often the app wakes it. The
creator board polls only while a task is running, and the task center polls
every 4 s only while something is pending / running, once a minute when idle,
and not at all while the tab is hidden. Still, close creator tabs you are not
using.

## Troubleshooting: `/ffmpeg/*` or other static files return the SPA HTML

The first rewrite in `vercel.json` sends every non-API, non-asset path to
`/index.html` so deep links work. Any new static directory under `front/dist`
(for example `ffmpeg/`, copied at build time) must be added to that rule's
negative lookahead, otherwise the browser receives `index.html` instead of the
file and features depending on it (合成导出) fail with an import error.
