"""
Seed the database with sample data for demo/review purposes.

Run after `docker compose up`:
    docker compose exec api python seed.py

Creates companies, signals, and runs scoring so the API immediately
has data to show. Takes ~2 seconds.
"""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.schema import Base, Company, Contact, Signal
from src.scorer.handler import _calculate_score
from src.shared.config import DATABASE_URL, INTENT_THRESHOLD

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)

# realistic sample companies
COMPANIES = [
    ("Acme Corp", "acme.com", "SaaS"),
    ("TechStart Inc", "techstart.io", "DevTools"),
    ("DataFlow Systems", "dataflow.dev", "Data Infrastructure"),
    ("CloudNine Solutions", "cloudnine.co", "Cloud Services"),
    ("Nexus AI", "nexusai.com", "AI/ML"),
    ("Greenfield Labs", "greenfieldlabs.io", "Biotech"),
    ("Velocity Commerce", "velocitycommerce.com", "E-commerce"),
    ("SignalPath Analytics", "signalpath.io", "Analytics"),
]

# signal templates--type, content template, confidence range, sentiment
SIGNAL_TEMPLATES = [
    ("executive_hire", "{company} hiring VP of Engineering", (0.7, 0.95), -0.2),
    ("executive_hire", "{company} appoints new CTO from Google", (0.85, 0.95), 0.1),
    ("senior_hire", "{company} looking for Director of Sales", (0.6, 0.85), -0.1),
    ("funding", "{company} raises $45M Series B led by Sequoia", (0.9, 0.98), 0.3),
    ("funding", "{company} closes seed round, emerges from stealth", (0.8, 0.9), 0.2),
    ("tech_migration", "{company} migrating from on-prem to AWS", (0.5, 0.75), -0.3),
    ("pain_mention", "Frustrated with {company} support response times", (0.6, 0.8), -0.7),
    ("competitor_dissatisfaction", "{company} leaving for alternatives - G2", (0.7, 0.9), -0.8),
    ("competitor_dissatisfaction", "After 2 years with {company}, switching", (0.75, 0.9), -0.9),
    ("rapid_hiring", "{company} posts 12 engineering roles in one week", (0.8, 0.95), 0.1),
    ("earnings_beat", "{company} Q3 revenue up 40% YoY", (0.85, 0.95), 0.5),
    ("sec_filing", "{company} 8-K filing indicates material acquisition", (0.9, 0.98), 0.2),
]


def seed():
    with Session(engine) as db:
        # clear existing demo data
        db.query(Signal).delete()
        db.query(Contact).delete()
        db.query(Company).delete()
        db.commit()

        companies = []
        for name, domain, industry in COMPANIES:
            c = Company(name=name, domain=domain, industry=industry)
            db.add(c)
            companies.append(c)
        db.flush()

        # distribute signals unevenly--some companies get many, some get few
        now = datetime.now(timezone.utc)
        signal_counts = [8, 6, 5, 4, 3, 2, 1, 1]

        for company, n_signals in zip(companies, signal_counts):
            templates = random.sample(SIGNAL_TEMPLATES, min(n_signals, len(SIGNAL_TEMPLATES)))
            for i, (sig_type, content_tpl, conf_range, sentiment) in enumerate(templates):
                signal = Signal(
                    company_id=company.id,
                    source=random.choice(["rss", "edgar", "news_search"]),
                    type=sig_type,
                    content=content_tpl.format(company=company.name),
                    confidence=round(random.uniform(*conf_range), 2),
                    sentiment=sentiment,
                    raw_json={"seeded": True},
                    created_at=now - timedelta(days=random.randint(0, 21)),
                )
                db.add(signal)

        db.flush()

        # run scorer
        for company in companies:
            company.intent_score = _calculate_score(db, company)
            company.last_scored_at = now

        db.commit()

        # report
        hot = [c for c in companies if c.intent_score >= INTENT_THRESHOLD]
        warm = [c for c in companies if 30 <= c.intent_score < INTENT_THRESHOLD]
        cold = [c for c in companies if c.intent_score < 30]

        print(f"\nSeeded {len(companies)} companies, {sum(signal_counts)} signals")
        print(f"  Hot leads (≥{INTENT_THRESHOLD}): {len(hot)}")
        for c in sorted(hot, key=lambda x: x.intent_score, reverse=True):
            print(f"    {c.name:25} score={c.intent_score}")
        print(f"  Warm ({30}-{INTENT_THRESHOLD-1}): {len(warm)}")
        for c in sorted(warm, key=lambda x: x.intent_score, reverse=True):
            print(f"    {c.name:25} score={c.intent_score}")
        print(f"  Cold (<30): {len(cold)}")
        print("\nAPI ready at http://localhost:8000/companies")


if __name__ == "__main__":
    seed()
