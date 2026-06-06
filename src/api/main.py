"""
FastAPI service--companies API + outreach generation endpoint.

Runs on Fargate in production. Locally: uvicorn src.api.main:app --reload
"""

import json
import os
from datetime import datetime, timezone

import boto3
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session, sessionmaker

from src.models.schema import Company, Contact, Outreach, ScoreHistory, Signal
from src.shared.config import BEDROCK_MODEL_ID, DATABASE_URL, INTENT_THRESHOLD

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

app = FastAPI(
    title="Intent Engine",
    description="Sales intelligence API--intent scores, signals, and AI-generated outreach",
    version="2.0.0",
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/companies")
def list_companies(
    min_score: float = Query(0, description="Minimum intent score filter"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """List companies ordered by intent score. Filter by minimum score."""

    companies = (
        db.query(Company)
        .filter(Company.intent_score >= min_score)
        .order_by(desc(Company.intent_score))
        .limit(limit)
        .all()
    )

    return [
        {
            "id": c.id,
            "name": c.name,
            "domain": c.domain,
            "industry": c.industry,
            "intent_score": c.intent_score,
            "last_scored_at": c.last_scored_at,
        }
        for c in companies
    ]


@app.get("/companies/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db)):
    """Full company detail with recent signals and score history."""

    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "company not found")

    signals = (
        db.query(Signal)
        .filter(Signal.company_id == company_id)
        .order_by(desc(Signal.created_at))
        .limit(20)
        .all()
    )

    history = (
        db.query(ScoreHistory)
        .filter(ScoreHistory.company_id == company_id)
        .order_by(desc(ScoreHistory.scored_at))
        .limit(30)
        .all()
    )

    contacts = db.query(Contact).filter(Contact.company_id == company_id).all()

    return {
        "id": company.id,
        "name": company.name,
        "domain": company.domain,
        "industry": company.industry,
        "intent_score": company.intent_score,
        "last_scored_at": company.last_scored_at,
        "signals": [
            {
                "type": s.type,
                "content": s.content,
                "confidence": s.confidence,
                "sentiment": s.sentiment,
                "source": s.source,
                "created_at": s.created_at,
            }
            for s in signals
        ],
        "score_history": [
            {"score": h.score, "scored_at": h.scored_at} for h in history
        ],
        "contacts": [
            {"name": c.name, "title": c.title, "email": c.email} for c in contacts
        ],
    }


@app.get("/companies/{company_id}/outreach")
def generate_outreach(company_id: int, db: Session = Depends(get_db)):
    """Generate personalized outreach message using recent signals as context."""

    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "company not found")

    signals = (
        db.query(Signal)
        .filter(Signal.company_id == company_id)
        .order_by(desc(Signal.created_at))
        .limit(5)
        .all()
    )

    if not signals:
        raise HTTPException(400, "no signals available for outreach generation")

    context = "\n".join(f"- [{s.type}] {s.content}" for s in signals)
    message = _generate_outreach_message(company.name, company.industry, context)

    # persist it
    outreach = Outreach(
        company_id=company.id,
        message=message["body"],
        talking_points=message.get("talking_points"),
        generated_at=datetime.now(timezone.utc),
    )
    db.add(outreach)
    db.commit()

    return message


@app.get("/hot-leads")
def hot_leads(db: Session = Depends(get_db)):
    """Companies above the intent threshold, sorted by score."""

    return list_companies(min_score=INTENT_THRESHOLD, db=db)


def _generate_outreach_message(
    company_name: str, industry: str, signal_context: str
) -> dict:
    """Call Bedrock to generate a personalized outreach email."""

    ind = industry or "tech"
    prompt = (
        f"Write a short, personalized sales outreach email for "
        f"{company_name} ({ind}).\n\n"
        f"Use these recent signals about them as context:\n"
        f"{signal_context}\n\n"
        "Requirements:\n"
        "- Under 150 words\n"
        "- Reference a specific signal naturally (don't list them all)\n"
        "- End with a soft CTA (coffee chat, not a demo)\n"
        "- Tone: consultative, not pushy\n\n"
        'Return JSON: {"subject": "...", "body": "...", '
        '"talking_points": ["...", "..."]}'
    )

    try:
        region = os.environ.get("AWS_REGION", "us-east-1")
        bedrock = boto3.client("bedrock-runtime", region_name=region)
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        result = json.loads(response["body"].read())
        return json.loads(result["content"][0]["text"])

    except Exception as e:
        # fallback for local dev without bedrock access
        return {
            "subject": f"Quick thought for {company_name}",
            "body": (
                f"Hi--saw some interesting movement at {company_name} "
                "recently. Would love to grab 15 minutes to share what "
                "we're seeing in the space."
            ),
            "talking_points": [
                s.strip("- []") for s in signal_context.split("\n") if s.strip()
            ],
            "error": f"bedrock unavailable: {e}",
        }
