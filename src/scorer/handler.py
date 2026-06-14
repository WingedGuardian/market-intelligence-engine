"""
Scorer Lambda--recalculates intent scores when new signals arrive.

Triggered by: new rows in signals table (via EventBridge pipe from RDS event
notifications, or direct invocation after extraction batch).

Signals are weighted and time-decayed; companies crossing INTENT_THRESHOLD trigger an SNS
alert with cooldown.

The cooldown prevents alert fatigue when a company gets multiple signals in
rapid succession--e.g., funding announcement + hiring surge in same news cycle.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.schema import Company, ScoreHistory, Signal
from src.shared.config import (
    ALERT_COOLDOWN_HOURS,
    DATABASE_URL,
    DECAY_POINTS_PER_WEEK,
    INTENT_THRESHOLD,
    SIGNAL_WEIGHTS,
    SNS_TOPIC_ARN,
)

sns = boto3.client("sns", region_name=os.environ.get("AWS_REGION", "us-east-1"))
engine = create_engine(DATABASE_URL)


def handler(event, context):
    """Score companies that received new signals."""

    company_ids = _extract_company_ids(event)

    scored = 0
    alerted = 0

    with Session(engine) as db:
        for company_id in company_ids:
            company = db.get(Company, company_id)
            if not company:
                continue

            score = _calculate_score(db, company)
            company.intent_score = score
            company.last_scored_at = datetime.now(timezone.utc)

            db.add(ScoreHistory(company_id=company.id, score=score))

            if score >= INTENT_THRESHOLD and _can_alert(company):
                _send_alert(company, score)
                company.last_alerted_at = datetime.now(timezone.utc)
                alerted += 1

            scored += 1

        db.commit()

    print(f"scored={scored} alerted={alerted}")
    return {"statusCode": 200, "scored": scored, "alerted": alerted}


def _extract_company_ids(event: dict) -> set[int]:
    """Pull company IDs from the trigger event."""

    ids = set()
    # direct invocation with explicit list
    if "company_ids" in event:
        return set(event["company_ids"])

    # SQS trigger carrying signal creation events
    for record in event.get("Records", []):
        body = json.loads(record.get("body", "{}"))
        if cid := body.get("company_id"):
            ids.add(cid)

    return ids


def _calculate_score(db: Session, company: Company) -> float:
    now = datetime.now(timezone.utc)
    # 90 days covers most B2B sales cycles. longer window picks up too much
    # noise from companies that were briefly interesting but went quiet.
    cutoff = now - timedelta(days=90)

    signals = (
        db.query(Signal)
        .filter(Signal.company_id == company.id, Signal.created_at >= cutoff)
        .all()
    )

    total = 0.0

    for signal in signals:
        weight = SIGNAL_WEIGHTS.get(signal.type, 5)
        age_weeks = (now - signal.created_at).days / 7.0
        decay = age_weeks * DECAY_POINTS_PER_WEEK

        # linear decay is simpler to explain in demos than exponential
        contribution = max(0, weight - decay) * (signal.confidence or 0.5)
        total += contribution

    # note: rapid_hiring can overlap signals scored above. at current weights the
    # bonus just kicks in slightly early--revisit if more hiring signal subtypes are added
    # rapid hiring bonus: 5+ hiring signals in 30 days
    recent_hires = sum(
        1 for s in signals
        if s.type in ("executive_hire", "senior_hire")
        and (now - s.created_at).days <= 30
    )
    if recent_hires >= 5:
        total += SIGNAL_WEIGHTS.get("rapid_hiring", 15)

    return min(100.0, round(total, 1))


def _can_alert(company: Company) -> bool:
    """Check cooldown--don't spam alerts for the same company."""

    if not company.last_alerted_at:
        return True

    cooldown = timedelta(hours=ALERT_COOLDOWN_HOURS)
    return datetime.now(timezone.utc) - company.last_alerted_at > cooldown


def _send_alert(company: Company, score: float):
    """Publish hot lead notification to SNS."""

    if not SNS_TOPIC_ARN:
        print(f"  [local] ALERT: {company.name} score={score}")
        return

    message = {
        "company": company.name,
        "domain": company.domain,
        "score": score,
        "industry": company.industry or "Unknown",
        "threshold": INTENT_THRESHOLD,
    }

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f"Hot Lead: {company.name} ({score}/100)",
        Message=json.dumps(message, indent=2),
    )
