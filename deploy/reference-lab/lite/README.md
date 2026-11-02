# Ai-Novel Lite evaluation

Source: <https://github.com/inliver233/Ai-Novel>, documented `lite` branch,
commit `d3bce7437861402083edd77af3cc50b088026b7d`. The source checkout is
`../../.reference-sources/lite` relative to `deploy/reference-lab`.
Upstream business code and source Dockerfiles remain unchanged. No LICENSE
file was found at this commit; this evaluation does not assign a license.

Merge this overlay after the primary `deploy/reference-lab/compose.yaml`.
All Compose paths resolve against that primary file's directory:

```sh
cd deploy/reference-lab
docker compose --env-file .env -f compose.yaml -f lite/compose-fragment.yml config --quiet
docker compose --env-file .env -f compose.yaml -f lite/compose-fragment.yml build lite-api
docker compose --env-file .env -f compose.yaml -f lite/compose-fragment.yml build lite
docker compose --env-file .env -f compose.yaml -f lite/compose-fragment.yml up -d lite-api lite
```

Build one service at a time. The frontend has a 384 MiB Node heap cap;
that is not a total build memory limit. The primary must monitor host memory
and bound the builder separately if needed. Runtime limits total 416 MiB
(API 384, Nginx 32), an upper bound, not measured consumption.

The primary gateway must join `lite_net`, use the shared ordinary form login
and signed session cookie (gateway username `viewer`), and forward public port
18021 to `http://lite:80`. Neither Lite
service publishes a host port. `lite_net` is internal and the API must have
no additional network, host mapping, or configured proxy. This prevents
runtime model API access even if a visitor enters a key later. The app has
no configured model, provider key, embedding model, OIDC service, or worker
model service. Registry labels/default model suggestions in the upstream UI
are not provisioned model configurations. Do not test generation or model
connections for this evaluation.

Private `.env` values (created by the primary, never committed):

```dotenv
LITE_ADMIN_USER=lab-admin
LITE_ADMIN_PASSWORD=<unique strong password of at least 8 characters>
LITE_SESSION_SIGNING_KEY=<unique random secret of at least 32 bytes>
LITE_ORIGIN=http://188.68.41.4:18021
```

There are two form logins: the shared gateway login, then the upstream local
username and password. Look up passwords only in the ignored
`private/access.json`; never record their values in documentation. The API
entrypoint creates the administrator on first startup;
it does not reset an existing account's password when the env value changes.
Encryption key generation is upstream-native and persists in
`lite_data:/data/secrets/secret_encryption_key`. Keep the session signing key
stable across restarts. Do not share a real application's volume or secrets.
Cookie names `lite_session` / `lite_session_expiry` avoid collisions between
apps served at different ports of the same IP.

The HTTP evaluation intentionally uses `APP_ENV=dev`, with
`AUTH_DEV_FALLBACK_USER_ID` empty, a static production frontend build,
single Uvicorn worker, SQLite WAL storage at `/data/lite.db`, and one inline
queue thread. Upstream `prod` forces Secure cookies and Redis/RQ; a plain
HTTP public origin would otherwise lose its session cookies. This is an
upstream-supported evaluation configuration and retains real account login,
but dev error detail and open local registration are present behind the shared
gateway login. It is not the upstream production deployment recommendation. SQLite and inline
tasks are appropriate for this temporary UI inspection, not
concurrent production generation. Background task state may be interrupted
by container restarts.

The native entrypoint waits for the DB, runs Alembic `upgrade head`, creates
the admin, and starts Uvicorn. Empty volumes require no separate DB service
or migration command. `/api/health` reports `db_is_sqlite=true` and
`effective_backend=inline`. `/api/auth/local/login` accepts
`{"user_id":"lab-admin","password":"..."}`; `/api/auth/user` verifies the
signed session. The frontend calls relative `/api` paths. The evaluation
Nginx replaces upstream's `backend:8000` target with `lite-api:8000` and
keeps SPA deep links functional; there is no compiled browser backend URL
to patch. Nginx uses one worker to fit the small runtime budget.

Static regression checks (existing Python + PyYAML, no app imports or host
dependency installation):

```sh
python lite/check_config.py
```

The Linux authentication suite passed all 18 tests, the Lite static configuration
suite passed all 5 checks, and HTTP form login, manual content save, and export
passed. All four images are built and running on 188. Real-browser verification
and persistence after container recreation remain under verification by the primary
agent; do not claim them as passed yet. No API/model configuration or paid
generation is used.
