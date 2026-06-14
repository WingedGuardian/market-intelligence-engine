# Intent Engine v2--Sales Intelligence Pipeline

Monitors the internet for buying signals, scores companies by purchase intent, and generates personalized outreach. Portable AWS architecture--serverless pipeline, costs $0 at rest.

## How it works

EventBridge triggers collectors every 15 minutes to pull RSS feeds, SEC EDGAR filings, and web search results. A Bedrock Claude extraction step pulls structured signals (company, signal type, confidence, sentiment) from raw text and queues them into Postgres. A scorer applies time-decayed weights to each company and fires SNS alerts when a score crosses the threshold. A FastAPI service exposes the rankings and generates outreach copy on demand.

## Architecture

```
EventBridge (15min) → Lambda Collectors → SQS FIFO → Lambda Extractor (Bedrock)
    → Aurora Serverless v2 (Postgres) → Lambda Scorer → SNS Alerts
                                      → Fargate API (FastAPI)
```

## Scoring model

```python
SIGNAL_WEIGHTS = {
    "executive_hire": 25,
    "senior_hire": 15,
    "funding": 20,
    "tech_migration": 15,
    "pain_mention": 10,
    "competitor_dissatisfaction": 30,  # 3x conversion rate vs other signals
    "rapid_hiring": 15,
    "earnings_beat": 10,
    "sec_filing": 10,
}
DECAY_RATE = 5      # points/week
THRESHOLD = 70      # "Hot Lead"
ALERT_COOLDOWN = 6h # per-company cooldown
```

Competitor dissatisfaction is weighted highest because it's the strongest conversion signal--someone already looking to switch is much closer to a yes than someone just hiring.

## Run it

**Local (Docker Compose)**

```bash
docker compose up -d
docker compose run --rm collector-rss
# API at http://localhost:8000
```

**AWS (deploy on demand)**

```bash
cd terraform/
terraform init
terraform apply -var="environment=demo"
# run the demo
terraform destroy  # back to $0
```

## Project structure

```
intent-engine/
├── src/
│   ├── collectors/     # RSS, EDGAR, web search
│   ├── extractor/      # Bedrock structured extraction
│   ├── scorer/         # Intent scoring + decay + alerts
│   ├── api/            # FastAPI (companies, outreach generation)
│   ├── models/         # SQLAlchemy ORM
│   └── shared/         # Config, constants
├── terraform/          # Full IaC--networking, data, events, compute
├── docker/
└── docker-compose.yml
```

## Stack

- Lambda (collectors, extractor, scorer)
- Fargate (FastAPI)
- Aurora Serverless v2 (Postgres 16)
- SQS FIFO
- Bedrock (Claude Haiku--extraction + outreach)
- EventBridge, SNS
- Terraform
- Docker Compose, ruff

## Cost

All serverless/pay-per-use. Demo run costs $2–5 for a couple hours. `terraform destroy` brings it back to $0.

---

MIT License
