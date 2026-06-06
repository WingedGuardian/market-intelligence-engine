import os

# scoring thresholds
INTENT_THRESHOLD = int(os.environ.get("INTENT_THRESHOLD", "70"))
DECAY_POINTS_PER_WEEK = int(os.environ.get("DECAY_RATE", "5"))
ALERT_COOLDOWN_HOURS = int(os.environ.get("ALERT_COOLDOWN_HOURS", "6"))

# signal weights
# highest weight--strongest real-world conversion signal
SIGNAL_WEIGHTS = {
    "executive_hire": 25,
    "senior_hire": 15,
    "funding": 20,
    "tech_migration": 15,
    "pain_mention": 10,
    "competitor_dissatisfaction": 30,
    "rapid_hiring": 15,
    "earnings_beat": 10,
    "sec_filing": 10,
}

# aws
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

# database
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://intent:intent@localhost:5432/intent_engine")
