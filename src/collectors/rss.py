"""
RSS collector--fetches tech/business news feeds and pushes raw articles to SQS.

Runs on EventBridge schedule (every 15min). Each article becomes an SQS message
for the extractor to process. We don't filter here--the extractor decides
what's relevant using Bedrock.
"""

import json
import os
import time

import boto3
import feedparser

sqs = boto3.client("sqs")
QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")

# curated for signal density--general tech news has too much noise
FEEDS = [
    "https://techcrunch.com/feed/",
    "https://news.crunchbase.com/feed/",
    "https://www.businesswire.com/rss/home/?rss=G1QFDERJBmk%3D",  # funding/M&A
    "https://feeds.feedburner.com/venturebeat/SZYF",
]


def handler(event, context):
    """Lambda entry point. Triggered by EventBridge schedule."""

    total = 0

    for feed_url in FEEDS:
        try:
            articles = _fetch_feed(feed_url)
            for article in articles:
                _enqueue(article)
                total += 1
        except Exception as e:
            # don't let one bad feed kill the whole run
            print(f"feed error ({feed_url}): {e}")

    print(f"enqueued {total} articles")
    return {"statusCode": 200, "articles": total}


def _fetch_feed(url: str, max_items: int = 15) -> list[dict]:
    feed = feedparser.parse(url)
    articles = []

    for entry in feed.entries[:max_items]:
        articles.append({
            "title": entry.get("title", ""),
            "summary": entry.get("summary", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": url,
            "collected_at": int(time.time()),
        })

    return articles


def _enqueue(article: dict):
    if not QUEUE_URL:
        # local dev--just log
        print(f"  [local] {article['title'][:80]}")
        return

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(article),
        MessageGroupId=article.get("url", "rss"),
    )
