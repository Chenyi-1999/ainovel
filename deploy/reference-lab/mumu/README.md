# MuMuAINovel UI evaluation

Source: https://github.com/xiamuceer-j/MuMuAINovel, main commit
`743e5abec18beb8d73426527e6579538053bc6fd` (upstream version 1.5.7).
The unchanged ignored source checkout is at the repository root: `.reference-sources/mumu`. Its GPL v3 LICENSE remains
unchanged and is copied into the evaluation image at `/app/LICENSE`.

The evaluation frontend build sets `reportCompressedSize:false`, which skips only
Vite's gzip-size statistics after the TypeScript check. It still loads the original
Vite config and uses its chunks, plugins and minifier; this setting does not change
business behavior. The report phase exceeded the constrained builder budget; no
upstream source file is changed.

This overlay is merged after `deploy/reference-lab/compose.yaml`. All relative
paths resolve from that base file. Requires Docker Compose with BuildKit named
additional build contexts (Compose 2.17+). The base gateway joins `mumu_net` and
proxies to `mumu:8000`, with the shared form-login gateway session supplied as a
signed cookie. Neither application nor database publishes a host port. Both networks are internal; the database
joins only `mumu_db_net`. Keep every application network internal to preserve
the no-egress constraint, including after any root-level overlay merge.

Required private environment variables are `MUMU_DB_PASSWORD`,
`MUMU_ADMIN_PASSWORD`, and `MUMU_SESSION_SECRET`. Generate independent random
values, using URL-safe alphanumeric/hex for the database password because it is
embedded in the SQLAlchemy connection URL. No credentials are supplied here.
Native username is `admin`; the password is initialized in the dedicated database
on first login, so changing the environment later does not reset an existing
account password. Session cookies are `session_token` and `session_expire_at`,
path `/`, same-site lax; ports do not isolate cookies. Check other applications
on the same IP for naming collisions before exposing the gateway. HTTP evaluation
explicitly sets `SESSION_COOKIE_SECURE=false`; use true if moved to HTTPS.

Native authentication reads the signed cookie and does not require an
Authorization header. The shared gateway uses an ordinary login form and signed
session cookie (gateway username `viewer`). Clear `X-Instance-ID` and `X-User-ID` request headers at the gateway: upstream otherwise
uses these as workshop proxy identities instead of local cookie authentication.

The upstream entrypoint waits for PostgreSQL and runs `alembic upgrade head`, then
executes one Uvicorn worker (`app.main:app`, port 8000). PostgreSQL 18 uses its
documented parent volume path `/var/lib/postgresql`, with the unchanged upstream
SQL extension initializer mounted read-only. Named volumes preserve database,
application data, and uploaded/generated cover storage. Runtime limits are
384 MiB application and 128 MiB PostgreSQL; these are evaluation limits pending
runtime measurement, below the upstream 2 GiB minimum recommendation.

The upstream Dockerfile downloads a 470,236,255-byte ONNX model, and its global
memory service loads that model while importing the application. The replacement
Dockerfile does not download it. `patch_ui_only.py` applies a minimal patch to
the image copy of `memory_service.py`, guarded against the pinned LF-normalized
source hash, leaving the original checkout unchanged. In UI-only mode, vector
components are explicit unavailable objects. Existing upstream handlers may
convert their exceptions into empty results or failed operations; no fake
embeddings or generation results are created. The patch omits five exclusively
vector-related direct requirements (`chromadb`, `numpy`, `onnxruntime`,
`tokenizers`, `filelock`); static import inspection found their only application
consumers in the disabled memory/ONNX modules. AI SDKs remain installed because
application routes import them, but all provider credentials, base URLs, and
default model are empty. Offline model flags provide a second guard.

Login, project browsing, configuration screens, and manual content editing are
intended for inspection. AI generation, analysis, embedding, vector memory,
knowledge indexing, cloud announcements/workshop, OAuth, and email are unavailable
or unconfigured. Cloud workshop points to closed loopback port 9. Do not add API
credentials or invoke paid generation as part of this evaluation. Runtime network
isolation is the enforcement boundary for outbound access, even if a visitor
edits a model setting. The dedicated evaluation account can access upstream MCP
and administrative UI; do not enable plugins or attach host mounts/privileges.

Validation: the Linux authentication suite passed all 18 tests, and the MuMu
static configuration suite passed all 5 checks. HTTP form login, manual content
save, and export have also passed. The four images are built and running on 188.
Real-browser verification and persistence after container recreation are still
being checked by the primary agent; do not treat them as passed yet. No model API
or paid generation is configured or used.
