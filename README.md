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

### Evaluate  *(Stage 5)*

```sh
email-classifier evaluate
```

Prints precision, recall, F1, confusion matrix, calibration table, threshold sweep, and cost/email.

### Stats  *(Stage 5)*

```sh
email-classifier stats --from 2026-09-01 --to 2026-09-30
```

Reports latency percentiles, category distribution, uncertain rate, cost, and Gmail-agreement rate.
Flags drops vs the previous period according to `stats.drift_alert_pct` in `config.yaml`.

### Label inbox  *(Stage 6)*

```sh
# Dry run (default — prints what would happen, changes nothing)
email-classifier label-inbox --dry-run

# Live run — applies Jev-Spam / Jev-Phishing / Jev-Needs-Reply labels only
email-classifier label-inbox
```

Never trashes, moves, or deletes messages. Uncertain verdicts are never labeled.

---

## Observability stack  *(Stage 4)*

```sh
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
├── observability/ OTel, Prometheus, structlog  (Stage 4)
├── eval/         Precision/recall, calibration  (Stage 5)
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
