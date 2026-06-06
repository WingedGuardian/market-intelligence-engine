"""Extract structured signals from raw text via Bedrock Claude Haiku."""

import json
import os
from datetime import datetime, timezone

import boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.schema import Company, Signal
from src.shared.config import BEDROCK_MODEL_ID, DATABASE_URL
from src.shared.entity import resolve_company

bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
engine = create_engine(DATABASE_URL)

EXTRACTION_PROMPT = """Analyze this text and extract business intent signals.

Text: {text}

Return JSON with these fields:
- company_name: string (the primary company mentioned)
- company_domain: string (best guess at their website domain, e.g. "acme.com")
- signal_type: one of [executive_hire, senior_hire, funding, tech_migration,
  pain_mention, competitor_dissatisfaction, rapid_hiring, earnings_beat, sec_filing]
- confidence: float 0-1 (how confident are you this is a real signal?)
- sentiment: float -1 to 1 (negative = bad for them = good for us selling to them)
- summary: string (1-2 sentence summary of the signal)

If the text doesn't contain a clear business signal, return {{"skip": true}}.
Return ONLY valid JSON, no markdown."""
def handler(event, context):
    """SQS trigger--processes batch of messages."""

    processed = 0
    skipped = 0

    with Session(engine) as db:
        for record in event.get("Records", []):
            body = json.loads(record["body"])
            text = _build_text(body)

            extraction = _extract_signal(text)
            if not extraction or extraction.get("skip"):
                skipped += 1
                continue

            _persist_signal(db, extraction, body)
            processed += 1

        db.commit()

    print(f"processed={processed} skipped={skipped}")
    return {"statusCode": 200, "processed": processed, "skipped": skipped}
def _build_text(message: dict) -> str:
    """Combine available text fields into extraction input."""
    parts = []
    for field in ("title", "summary", "snippet", "description", "text"):
        if message.get(field):
            parts.append(message[field])
    return " ".join(parts)
def _extract_signal(text: str) -> dict | None:
    """Call Bedrock to extract structured signal from raw text."""

    prompt = EXTRACTION_PROMPT.format(text=text[:3000])  # cap input length

    try:
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        result = json.loads(response["body"].read())
        content = result["content"][0]["text"]
        return json.loads(content)

    except Exception as e:
        print(f"bedrock extraction failed: {e}")
        return None
# TODO: batch upserts--current approach does N queries for N signals, fine at
# our volume but will need a bulk merge if we add more feeds
def _persist_signal(db: Session, extraction: dict, raw_message: dict):
    name = extraction.get("company_name", "Unknown")
    domain = extraction.get("company_domain", "unknown.com")

    company = resolve_company(db, name, domain)
    if not company:
        company = Company(name=name, domain=domain, industry=raw_message.get("industry"))
        db.add(company)
        db.flush()

    signal = Signal(
        company_id=company.id,
        source=raw_message.get("source", "unknown"),
        type=extraction["signal_type"],
        content=extraction.get("summary", ""),
        sentiment=extraction.get("sentiment", 0.0),
        confidence=extraction.get("confidence", 0.5),
        raw_json=raw_message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(signal)
