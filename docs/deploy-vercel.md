# Deploying Jellyfish on Vercel

This fork runs the whole stack in a single Vercel project using
[Vercel Services](https://vercel.com/docs/services):

| Piece | Upstream (Docker Compose) | On Vercel |
| --- | --- | --- |
| Frontend (`front/`) | nginx | `web` service (Vite static build) |
| API (`backend/`) | uvicorn | `api` service (FastAPI on Vercel Functions) |
| Task workers | Celery + Redis | **In-process** inside the API function (`TASK_EXECUTION_MODE=inline`, kept alive with `wait_until`). Optional: Celery on Vercel Queues (`TASK_EXECUTION_MODE=celery`, subscriber `backend/worker.py`) |
| Database | MySQL | **Postgres** (Neon via Vercel Marketplace) |
| Object storage | RustFS / S3 | **Cloudflare R2** (or any S3-compatible bucket) via `S3_*` variables; **Vercel Blob** is used when only the Blob token is present (see [Object storage](#object-storage-cloudflare-r2)) |
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
when the Neon database and Blob store are connected. For the recommended R2 object
storage, see [Object storage: Cloudflare R2](#object-storage-cloudflare-r2).

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

## Object storage: Cloudflare R2

Generated images / videos and user uploads go to an S3-compatible bucket when
`S3_BUCKET_NAME` is set; otherwise to Vercel Blob. Cloudflare R2 is the recommended
bucket: its free tier (10 GB storage, 1 M writes and 10 M reads per month, **no egress
fee**) is per account and is not suspended team-wide the way Hobby Blob is. The backend
detects an R2 endpoint (`*.r2.cloudflarestorage.com`) and applies R2's differences by
itself: region `auto`, path-style addressing, no default CRC checksums, no
`LocationConstraint` on bucket creation. Browser uploads of videos / audio use a
presigned PUT URL (1 h, signed Content-Type), so files never pass through the function.

Setup (Cloudflare dashboard → R2 Object Storage):

1. **Create a bucket**, e.g. `ai-filming-media` (location hint: Asia-Pacific is fine;
   R2 picks the actual region).
2. **Public access**: bucket → Settings → *Public Development URL* → Enable (gives
   `https://pub-<hash>.r2.dev`), or attach a custom domain on a zone in the same
   account (better: r2.dev is rate-limited and meant for development). Generated
   assets are referenced by this URL from the browser and from the Ark (Seedance)
   API, so the bucket must be publicly readable; keys contain UUIDs and are
   unguessable.
3. **CORS** (bucket → Settings → CORS policy). Needed for browser uploads and for
   在浏览器内合成导出 (which `fetch`es clips). The app writes this rule itself on cold
   start when the token has admin rights; otherwise paste it:

   ```json
   [
     {
       "AllowedOrigins": ["*"],
       "AllowedMethods": ["GET", "HEAD", "PUT"],
       "AllowedHeaders": ["*"],
       "ExposeHeaders": ["ETag", "Content-Length", "Content-Type"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

4. **API token**: R2 → *Manage R2 API Tokens* → Create. Permission *Object Read &
   Write* scoped to the bucket is enough for the app; *Admin Read & Write* additionally
   lets the app create the bucket and write the CORS rule itself. Copy the **Access Key
   ID**, **Secret Access Key** and the **S3 endpoint**
   (`https://<account_id>.r2.cloudflarestorage.com`) shown after creation.
5. Add these variables to the Vercel project (Production, and Preview if you use it),
   then redeploy:

   | Variable | Value |
   | --- | --- |
   | `S3_ENDPOINT_URL` | `https://<account_id>.r2.cloudflarestorage.com` |
   | `S3_REGION_NAME` | `auto` (optional; default for R2) |
   | `S3_ACCESS_KEY_ID` | the token's Access Key ID |
   | `S3_SECRET_ACCESS_KEY` | the token's Secret Access Key (mark as sensitive) |
   | `S3_BUCKET_NAME` | `ai-filming-media` |
   | `S3_PUBLIC_BASE_URL` | `https://pub-<hash>.r2.dev` or `https://media.example.com` |
   | `S3_BASE_PATH` | optional prefix, e.g. `prod` |

Verify with `GET /api/v1/_deploy/status`: `storage.backend` is `s3`,
`storage.cloudflare_r2` is `true`, `storage.direct_upload` is `s3` and `storage.ok` is
`true` (one `HeadBucket` call); `bootstrap.summary.storage.cors` is `written` or
`present` when the CORS rule is in place, `error` when the token lacks bucket
permissions (then configure CORS by hand as above). Then upload a video in step ④ and
check that the file appears in the bucket under `uploads/<uuid>/`.

Notes:

- Files generated while Blob was the backend keep their `blob.vercel-storage.com` URLs
  and are not migrated; they load again once the Blob suspension lifts. New files go to
  R2 only. `BLOB_READ_WRITE_TOKEN` can stay connected; `S3_BUCKET_NAME` takes precedence.
- Any other S3-compatible store works with the same variables (AWS S3 with a real
  region; MinIO / RustFS with `S3_ADDRESSING_STYLE=path`).
- Local development: put the same variables in `backend/.env` (see `.env.example`).

## Health check

`GET /api/v1/_deploy/status` reports the database dialect and row counts, the
storage backend (`storage`: backend, bucket, endpoint host, direct-upload mode and a
`HeadBucket` / Blob head probe, no secrets), the Celery broker scheme, the bootstrap
result, and the configured Ark models. Add `?probe_ark=true` to make read-only calls to the Ark API
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

Cause: the Hobby plan's included Blob usage was used up. Hobby includes, per
30-day cycle and shared by **every project in the team**: 1 GB storage, 10 GB
Blob data transfer, 10,000 simple and 2,000 advanced operations. When any of
them is exceeded Vercel suspends *all* Blob stores of the team at once (reads
included: public blob URLs answer 403, so existing thumbnails and videos stop
showing too) and, per the docs, "you will have to wait until 30 days have
passed before using Blob storage again". On 2026-11-07 the suspension hit at
07:29 UTC; the team's usage API showed 3.6 GB of egress in the cycle, 95 % of it
from another project's store (`gaming-arena-media`), ~0.1 GB from this app. Check
with `GET /v2/usage?type=storage_blob&from=…&to=…&granularity=day` or the
dashboard's Usage page.

Fixes, pick one:

1. Upgrade the Vercel team to Pro (or start the Pro trial offered on the store
   page); the stores resume immediately.
2. Wait for the 30-day window to pass (about 30 days after the suspension);
   keep other projects' Blob traffic in mind, the allowance is team-wide.
3. Point the backend at Cloudflare R2 (or any S3-compatible bucket) instead of
   Blob, see [Object storage: Cloudflare R2](#object-storage-cloudflare-r2);
   `storage.backend` in `/_deploy/status` switches to `s3`. The production
   deployment was switched to R2 this way on 2026-11-08 (bucket `ai-filming-media`,
   APAC; the R2 token has object permissions only, so `bootstrap.summary.storage.cors`
   reports `error` and the CORS rule was written through the Cloudflare API instead).
   Files already stored in Blob keep their Blob URLs and become readable again when
   the suspension lifts.

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
