# Government Service Request Management System

**Developed by Minhazul Islam Royel**

A backend service (with a small web UI) where citizens submit service requests such as NID, passport, missing
report and police verification, admins validate them and assign officers, and officers process them.

- **Live demo:** _add your URL here after deploying (see [Deploy](#deploy-make-it-live))_
- **API docs (Swagger):** `/api/docs/`

## Tech stack

Python 3.12, Django 5.1, Django REST Framework, PostgreSQL, Redis, JWT (SimpleJWT), Docker + Docker Compose,
nginx (load balancer), Bootstrap 5 + vanilla JavaScript. SQLite is supported as an optional local database.

## Features

| Area | What is implemented |
|---|---|
| Authentication | JWT register / login / refresh. Roles: Citizen, Officer, Admin. Public sign-up always creates a citizen; only an admin can create officers. |
| Requests | Category, title, description, priority (low / medium / high), citizen remarks, status, officer assignment, comments, file attachments |
| Status flow | `not_validated` -> `validated` -> `officer_assigned` -> `pending` -> `task_done`. Steps cannot be skipped and each step is limited to specific roles. |
| Citizen | Register with name, email, phone, password. Submit requests, follow the status, add remarks and comments, upload files, edit a request until it is validated. |
| Officer | See only assigned tasks. Start work (Pending), mark done. Earns points: High 3, Medium 2, Low 1. |
| Admin | Manage categories, validate requests, assign officers, view all requests, statistics, per-officer workload and points, audit log, create officers. |
| Availability | The assign dropdown lists only officers holding fewer than 3 active tasks (`OFFICER_MAX_ACTIVE_TASKS`). The server checks this again on assignment. |
| Comments | Each comment is for the citizen or internal for the officer. Citizens never see internal comments. |
| Redis + rate limiting | Login/register: 50 requests per minute per IP. Other endpoints: 120 per minute per user. Counters live in Redis so they hold across all API replicas. |
| Audit logs | Login, registration, request changes, assignments, status changes, comments, uploads and category changes are recorded (admin-only view). |
| AI support (RAG) | Answers from guide documents and from the citizen's own requests. |
| Frontend | Bootstrap + JavaScript single page for all three roles. |

## Run it with Docker (recommended)

Requires Docker Desktop (or Docker Engine with the Compose plugin).

```bash
cp .env.example .env          # Windows CMD: copy .env.example .env
# edit .env: set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build -d
```

- App: http://localhost:8080
- Swagger: http://localhost:8080/api/docs/
- Tests: `docker compose run --rm web python manage.py test tests`
- Logs: `docker compose logs -f web`
- Stop: `docker compose down` (add `-v` to also delete the database)
- More API replicas: `docker compose up -d --scale web=4`

Compose starts PostgreSQL, Redis, a one-shot `migrate` job (migrations + optional demo data), two `web` replicas,
and nginx in front of them.

### Demo accounts

With `SEED_DEMO_DATA=true` (in `.env.example`) these exist, password `Demo@12345`:
`admin@example.com`, `officer1@example.com`, `officer2@example.com`, `officer3@example.com`, `citizen@example.com`.
Turn seeding off for anything public.

## Database choice

Set `DB_ENGINE` in the environment:

| `DB_ENGINE` | Use | Needs |
|---|---|---|
| `postgres` (default) | Docker Compose, production | `POSTGRES_*` variables |
| `sqlite` | Quick local run, no server | nothing (`SQLITE_PATH` optional) |

Run without Docker on SQLite:

```bash
pip install -r requirements.txt
export DB_ENGINE=sqlite           # PowerShell: $env:DB_ENGINE="sqlite"
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

For a local PostgreSQL, create the user and database, set `DB_ENGINE=postgres`, `POSTGRES_HOST=localhost` and the other
`POSTGRES_*` values, and run the same commands. The tests pass on both engines (44 tests).

## How a request moves

1. **Citizen** submits a request. Status: *Not validated yet*.
2. **Admin** validates it. Status: *Validated*.
3. **Admin** assigns an available officer. Status: *Officer assigned*. Admin and officer can leave comments.
4. **Officer** starts work. Status: *Pending*.
5. **Officer** marks it done. Status: *Task done*. The officer receives 3 / 2 / 1 points for High / Medium / Low.

## API summary

Full interactive documentation is at `/api/docs/`.

```
POST /api/auth/register/   /login/   /refresh/          GET /api/auth/me/
GET, POST   /api/requests/                               GET, PATCH /api/requests/{id}/
            filters: ?status= &priority= &category= &q=
POST /api/requests/{id}/validate/                        (admin)
POST /api/requests/{id}/assign/        {"officer_id": 2}  (admin)
POST /api/requests/{id}/status/        {"status": "pending" | "task_done"}  (officer)
GET, POST   /api/requests/{id}/comments/     {"body": "...", "audience": "citizen" | "officer"}
GET, POST   /api/requests/{id}/attachments/  (multipart "file")
GET         /api/requests/{id}/attachments/{aid}/download/
GET, POST, PATCH /api/categories/                        (write: admin)
GET, POST   /api/admin/officers/       GET /api/admin/officers/available/
GET         /api/admin/stats/          GET /api/admin/audit-logs/
POST        /api/support/ask/          {"question": "..."}
GET         /api/health/
```

## Redis and rate limiting

- Redis is used through Django's cache (`REDIS_URL`) as the shared counter store. All API replicas behind nginx see the
  same counters.
- Each request adds one to a key like `ratelimit:auth:<ip>:<minute>` (an atomic Redis increment). Over the limit gives
  `429 Too Many Requests` with a `Retry-After` header. The key expires on its own.
- Limits: `RATE_LIMIT_AUTH_PER_MIN` (default 50, per IP, for login/register/refresh) and `RATE_LIMIT_API_PER_MIN`
  (default 120, per user, or per IP when not logged in).
- **Limitations:** it is a fixed one-minute window, not a token bucket, so a client can burst up to twice the limit
  across a minute boundary. If Redis is unreachable, requests fail instead of skipping the limit.
- `TRUST_X_FORWARDED_FOR=true` makes the app read the client IP from `X-Forwarded-For`. That is only safe behind a proxy
  you control (the bundled nginx overwrites the header).

Quick check (about 50 `401` results, then `429`):

```bash
for i in $(seq 1 55); do curl -s -o /dev/null -w "%{http_code} " -X POST http://localhost:8080/api/auth/login/ \
  -H "Content-Type: application/json" -d '{"email":"x@x.com","password":"bad"}'; done
```

## Load balancing

nginx (`deploy/nginx.conf`) round-robins requests across all `web` replicas and re-resolves the service name every few
seconds, so `--scale web=N` works without restarting nginx. The replicas are stateless. Uploaded files use a shared
Docker volume.

## AI support (RAG)

`POST /api/support/ask/` runs a small retrieval pipeline in `apps/support/rag.py`:

1. Guide files in `apps/support/knowledge/*.md` are split into chunks by heading.
2. The asking citizen's own requests are added as extra chunks (never other people's).
3. Chunks are ranked with TF-IDF cosine similarity.
4. An extractive generator returns the best passages with their sources, or a polite fallback.

It matches words, not meaning, and it cannot answer anything that is not in the guides or the citizen's requests. The
guide text is sample content: replace it with official content. To use an LLM, implement `AnswerGenerator.generate()`
and pass it to `RAGService`.

## Code structure and SOLID

```
apps/accounts          user model, JWT views, seed_demo command
apps/service_requests  models, policies.py, services.py, selectors.py, stats.py, views (thin)
apps/audit             append-only AuditLog and AuditService
apps/support           RAG pipeline and knowledge base
apps/frontend          Bootstrap + JavaScript page
common/                rate limiter, throttles, exceptions, pagination
deploy/                nginx.conf, start.sh
tests/                 automated tests (44)
```

- **Single responsibility:** views handle HTTP, `RequestService` runs use-cases, policies hold business rules,
  `AuditService` only audits.
- **Open/closed:** new points or availability rules are new policy classes; new status changes are one line in
  `TRANSITIONS`.
- **Liskov:** `PriorityPointsPolicy`, `TfidfRetriever`, `ExtractiveAnswerGenerator` and `CacheWindowRateLimiter` can be
  replaced by any subclass of their base class.
- **Interface segregation:** small interfaces such as `RateLimiter.hit`, `PointsPolicy.points_for`, `Retriever.search`,
  `AnswerGenerator.generate`.
- **Dependency inversion:** `RequestService` and `RAGService` receive their collaborators through the constructor.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | dev key | Django secret. Always change it. |
| `DEBUG` | `false` | Debug mode |
| `ALLOWED_HOSTS` | `*` | Comma-separated host names |
| `DB_ENGINE` | `postgres` | `postgres` or `sqlite` |
| `POSTGRES_DB` / `_USER` / `_PASSWORD` / `_HOST` / `_PORT` | gov_service / gov / gov / db / 5432 | PostgreSQL connection |
| `REDIS_URL` | empty | Redis for counters. Empty uses in-process memory (fine for local only). |
| `RATE_LIMIT_AUTH_PER_MIN` | 50 | Login/register limit per IP |
| `RATE_LIMIT_API_PER_MIN` | 120 | Other endpoints, per user |
| `TRUST_X_FORWARDED_FOR` | `false` | Read client IP from the proxy header |
| `OFFICER_MAX_ACTIVE_TASKS` | 3 | Tasks an officer can hold at once |
| `MAX_UPLOAD_MB` | 5 | Attachment size limit |
| `SEED_DEMO_DATA` | `true` (example file) | Docker Compose only: create demo users |
| `DEMO_PASSWORD` | unset | Single-container hosts: create demo users with this password |

## Deploy (make it live)

The instructions below use Render. Check Render's current plans before you start, as free-tier limits change.

1. Push this repository to GitHub.
2. Render dashboard: **New > PostgreSQL** (free plan is fine for a demo). Copy its *internal* host, port, database,
   user and password.
3. **New > Key Value** (Redis-compatible). Copy its *internal* URL (starts with `redis://`).
4. **New > Web Service**, connect the GitHub repo, and set:
   - Language / runtime: **Docker**
   - Docker Command: `sh deploy/start.sh`
   - Health Check Path: `/api/health/`
   - Environment variables:

     ```
     SECRET_KEY=<long random string>
     DEBUG=false
     ALLOWED_HOSTS=<your-service>.onrender.com
     DB_ENGINE=postgres
     POSTGRES_HOST=<internal host>
     POSTGRES_PORT=5432
     POSTGRES_DB=<database>
     POSTGRES_USER=<user>
     POSTGRES_PASSWORD=<password>
     REDIS_URL=<internal redis url>
     TRUST_X_FORWARDED_FOR=true
     DEMO_PASSWORD=<private password, letters and digits>
     ```
5. Deploy. `deploy/start.sh` runs migrations, creates the demo users (only if `DEMO_PASSWORD` is set) and starts
   gunicorn on Render's `PORT`.
6. Open `https://<your-service>.onrender.com`, then put that URL at the top of this README.

**Free-plan limits to expect:** free web services sleep after idle time and take about a minute to wake, free
PostgreSQL databases expire after 30 days, free Key Value is memory-only, and files written to the web service's disk
(uploaded attachments) are lost on redeploy. For a permanent deployment, use paid plans plus a persistent disk or object
storage such as S3.

**Own server (VPS):** install Docker, clone the repo, `cp .env.example .env`, set strong values (and
`SEED_DEMO_DATA=false`), run `docker compose up --build -d`, and put a TLS reverse proxy (Caddy, or nginx with
Let's Encrypt) in front of port 8080.

## Known limitations

- No email verification or notifications and no Celery (not selected as bonus items).
- Attachments are stored on local disk or a Docker volume, not object storage.
- The RAG assistant is keyword-based and extractive.
- The frontend is intentionally basic.

## Author

Developed by **Minhazul Islam Royel**.