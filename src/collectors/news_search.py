"""
News search collector--queries Google News RSS for company mentions.

Replaces the web search mock with real data. Google News RSS is free, needs
no API key, and returns recent articles matching a search query. We search
for each target company and push results to SQS for extraction.

Limitations: Google News titles are often truncated, descriptions contain
HTML entities. Good enough for signal extraction--the LLM handles messy input.
"""

import json
import os
import time

import boto3
import feedparser

sqs = boto3.client("sqs")
QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")

# TODO: load targets from DB or EventBridge payload
DEFAULT_TARGETS = ["Salesforce", "Snowflake", "Databricks", "HashiCorp", "Datadog"]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def handler(event, context):
    """Lambda entry point. Triggered by EventBridge schedule."""

    companies = event.get("companies", DEFAULT_TARGETS)
    total = 0

    for company in companies:
        try:
            articles = _search_news(company)
            for article in articles:
                _enqueue(article)
                total += 1
        except Exception as e:
            print(f"news search error ({company}): {e}")

    print(f"enqueued {total} articles from news search")
    return {"statusCode": 200, "articles": total}


def _search_news(company: str, max_items: int = 5) -> list[dict]:
    """Query Google News RSS for recent articles mentioning the company."""

    query = f'"{company}" hiring OR funding OR acquisition OR partnership'
    url = GOOGLE_NEWS_RSS.format(query=query.replace(" ", "+"))

    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        # feedparser sets bozo=1 on parse errors but may still have entries
        return []

    articles = []
    for entry in feed.entries[:max_items]:
        articles.append({
            "title": entry.get("title", ""),
            "summary": entry.get("summary", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": "news_search",
            "company_hint": company,
            "collected_at": int(time.time()),
        })

    return articles


def _enqueue(article: dict):
    if not QUEUE_URL:
        print(f"  [local] {article['title'][:80]}")
        return

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(article),
        MessageGroupId=article.get("company_hint", "news"),
    )
