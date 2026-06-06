"""
SEC EDGAR collector--monitors recent filings for M&A, material events, and
executive changes (8-K, SC 13D, DEF 14A forms).

EDGAR's full-text search API is free, no auth needed, just a user-agent header.
Rate limit: 10 req/sec. We run every 15min so nowhere near that.
"""

import json
import os
import time
import urllib.request

import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
USER_AGENT = "IntentEngine/2.0 (jay@example.com)"  # SEC requires identification

# filing types that carry intent signals
FILING_TYPES = ["8-K", "SC 13D", "DEF 14A"]
# NOTE: EDGAR search API is undocumented and occasionally returns empty results
# for no clear reason. if this becomes a problem, switch to the RSS feed at
# https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=8-K&output=atom


def handler(event, context):
    """Lambda entry point. Triggered by EventBridge schedule."""

    total = 0

    for form_type in FILING_TYPES:
        try:
            filings = _fetch_recent_filings(form_type)
            for filing in filings:
                _enqueue(filing)
                total += 1
        except Exception as e:
            print(f"edgar error ({form_type}): {e}")

    print(f"enqueued {total} filings")
    return {"statusCode": 200, "filings": total}


def _fetch_recent_filings(form_type: str, limit: int = 10) -> list[dict]:
    """Query EDGAR full-text search for recent filings of a given type."""

    url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?q=%22{form_type}%22&dateRange=custom&startdt=2024-01-01"
        f"&forms={form_type}&hits.hits.total.value={limit}"
    )

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"edgar fetch failed: {e}")
        return []

    filings = []
    hits = data.get("hits", {}).get("hits", [])

    for hit in hits[:limit]:
        source = hit.get("_source", {})
        filings.append({
            "company_name": source.get("display_names", [""])[0],
            "ticker": source.get("tickers", [""])[0] if source.get("tickers") else "",
            "form_type": form_type,
            "filed_at": source.get("file_date", ""),
            "description": source.get("display_description", ""),
            "url": f"https://www.sec.gov/Archives/edgar/data/{source.get('entity_id', '')}/",
            "source": "edgar",
            "collected_at": int(time.time()),
        })

    return filings


def _enqueue(filing: dict):
    if not QUEUE_URL:
        print(f"  [local] {filing['company_name']} - {filing['form_type']}")
        return

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(filing),
        MessageGroupId=filing.get("company_name", "edgar"),
    )
