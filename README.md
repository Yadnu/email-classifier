# Personal Gmail Spam Classifier

A personal email spam/phishing classifier that pulls your own Gmail and classifies messages using [TypeSafe's Jev model](https://typesafe.ai) (System One — returns typed decisions with probabilities, not text).

Each classification returns **category, spam verdict, reply probability, timing breakdown, and detailed observability metrics**.

---

## Quick architecture

```
Gmail API → OAuth → ingest → SQLite
                              ↓
                    parse → features → Jev state → TypeSafeClient (jev-1.13.0)
                                                          ↓
                                              decide (threshold logic)
                                                          ↓
                                         ClassificationResult (Pydantic)
                                         ↙          ↓          ↘
                                       CLI        FastAPI      SQLite + OTel
```

---

## Setup

### 1 — Google Cloud Console (Gmail API)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project (or use an existing one).
2. **Enable the Gmail API**: *APIs & Services → Library → Gmail API → Enable*.
3. **Create an OAuth Desktop client**:
   - *APIs & Services → Credentials → Create Credentials → OAuth client ID*
   - Application type: **Desktop app**
   - Download the JSON file and save it as **`data/credentials.json`** in this repo.
4. **Add yourself as a test user**:
   - *APIs & Services → OAuth consent screen → Test users → Add Users*
   - Enter your Gmail address.

> `data/` is gitignored. The file will not be committed.

### 2 — TypeSafe API key

1. Sign up at [typesafe.ai](https://typesafe.ai) and create an API key.
2. Copy `.env.example` to `.env`:
   ```sh
   cp .env.example .env
   ```
3. Fill in `TYPESAFE_API_KEY=<your-key>`.

### 3 — Install dependencies

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```sh
uv sync
```

---

## Commands

### Ingest Gmail

```sh
# Incremental sync (uses historyId; first run fetches all messages)
email-classifier ingest

# Force a full re-fetch regardless of saved historyId
email-classifier ingest --full
```

Output is counts only — no subjects or email addresses are printed.

```
Ingested  1,247 messages  (312 spam, 935 ham)  historyId=3048291
```

### Serve the API

Binds **127.0.0.1** only (local single user, no auth).

```sh
uv run email-classifier serve
```

| Endpoint | Purpose |
|---|---|
| `POST /classify` | Classify one Gmail id |
| `GET /metrics` | Prometheus scrape |
| `GET /api/health` | Jev key, Gmail token expiry, ingest time, row counts |
| `GET /api/messages` | Paginated compact list (`from`, `to`, `category`, `min_confidence`, `search`, `cursor`) |
| `GET /api/messages/{id}` | Full contract + Jev state, questions, span tree, decision trail |
| `GET /api/stats` | Dashboard aggregates |
| `GET /api/calibration` | Spam/reply calibration buckets |
| `GET /api/live` | SSE stream of new classifications |
| `POST /api/replay/{id}` | Re-run stored state through Jev; return a diff |

Seed fake rows so the GUI can be built without real mail (ids are `seed-0000` …):

```sh
uv run python scripts/seed_classifications.py --count 80
```

The Next.js GUI (list + detail) lives in `web/`. Keep the API on 127.0.0.1:8000.

```sh
uv run python scripts/seed_classifications.py --count 80
uv run email-classifier serve
# other terminal:
cd web
npm install
npm run dev
```

Open http://127.0.0.1:3000 — message list, click a row for waterfall + Jev question cards.

### Classify a single message

```sh
# Compact one-liner
email-classifier classify <message_id>

# Full JSON output
email-classifier classify <message_id> --json
```

Sample compact output:

```
[SPAM 97%] category=spam (0.94) reply=2% time=212ms (jev 148ms) model=jev-1.13.0
```

### Evaluate

Uses the latest stored classification per message and Gmail labels as ground truth (no new Jev calls).

```sh
email-classifier evaluate
```

Prints precision, recall, F1, confusion matrix, spam/reply calibration, a threshold sweep that maximizes spam precision, the SPF/DKIM + From≠Reply-To baseline, cost/email, and p50/p95/p99 latency.

### Stats

```sh
email-classifier stats --from 2026-09-01 --to 2026-09-30
```

Reports latency percentiles, category mix, mean confidence, uncertain rate, cost, and agreement vs Gmail `SPAM`.
With `--from`, compares an equal-length previous window and flags drops above `stats.drift_alert_pct` in `config.yaml`.

### Label inbox

```sh
# Dry run (default — prints what would happen, changes nothing)
email-classifier label-inbox
# same as: email-classifier label-inbox --dry-run

# Live run — requests gmail.modify (token at data/token_modify.json)
# and adds Jev-Spam / Jev-Phishing / Jev-Needs-Reply only
email-classifier label-inbox --no-dry-run
```

Never trashes, moves, or deletes messages. Uncertain verdicts are never labeled.

---

## Observability stack

```sh
# API (metrics + classify) on the host
email-classifier serve

# Then, from another terminal:
cd deploy
docker compose up -d
```

| Service     | URL                       |
|-------------|---------------------------|
| Prometheus  | http://localhost:9090     |
| Grafana     | http://localhost:3000     |
| Jaeger      | http://localhost:16686    |
| OTel collector | grpc :4317, http :4318 |

Metrics endpoint (FastAPI): `GET http://localhost:8000/metrics`

---

## Configuration

All tunable values live in [`config.yaml`](config.yaml):

| Key | Default | Description |
|-----|---------|-------------|
| `ingest.page_size` | 500 | Gmail list page size |
| `ingest.batch_size` | 50 | Gmail batch-get size |
| `ingest.promotions_as` | `promotional` | How to treat CATEGORY_PROMOTIONS |
| `ingest.max_messages` | null | Safety cap per run |
| `jev.model` | `jev-1.13.0` | Pinned Jev version |
| `jev.price_per_million_input_tokens` | 0.042 | USD/M input tokens |
| `jev.body_excerpt_chars` | 1500 | Max body chars sent to Jev |
| `thresholds.uncertain_floor` | 0.50 | Min confidence to auto-label |
| `thresholds.phishing_category_confidence` | 0.85 | Phishing category bar |
| `stats.drift_alert_pct` | 10 | Drift alert threshold % |

---

## Project layout

```
email_classifier/
├── auth/         OAuth Desktop flow
├── ingest/       Gmail pull, SQLite schema, historyId sync
├── parse/        MIME + HTML stripping
├── features/     Code-computed signals: SPF/DKIM, links, domain checks
├── jev/          State builder (questions + TypeSafeClient in Stage 3)
├── decide/       Threshold logic, decision_path  (Stage 3)
├── models/       Pydantic output contract  (Stage 3)
├── observability/ OTel traces, Prometheus metrics, structlog JSON
├── eval/         Precision/recall, calibration, stats, drift watch
├── label/        label-inbox (Jev-Spam / Jev-Phishing / Jev-Needs-Reply)
├── api/          FastAPI endpoints  (Stage 3)
└── cli/          Typer CLI
deploy/           docker-compose, Prometheus config, Grafana dashboard
tests/            Fake .eml fixtures only — never real email
data/             gitignored (credentials.json, token.json, classifier.db)
```

---

## Development

```sh
# Run tests
uv run pytest

# Run a specific test file
uv run pytest tests/test_ingest.py -v
```
