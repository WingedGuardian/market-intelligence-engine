# Intent Scoring Model

## How it works

Each company starts at 0. Signals increase the score; time decreases it.
When the score crosses 70, the company becomes a "Hot Lead" and triggers
an alert.

## Signal weights

| Signal Type | Weight | Why |
|-------------|--------|-----|
| competitor_dissatisfaction | 30 | Strongest predictor--actively unhappy with competitor |
| executive_hire | 25 | New leadership = new vendor evaluations |
| funding | 20 | Budget available for new tools |
| senior_hire | 15 | Growth phase, more tools needed |
| tech_migration | 15 | Actively changing stack |
| rapid_hiring | 15 | 5+ hires in 30 days = scaling fast |
| pain_mention | 10 | Problem awareness, not yet buying |
| earnings_beat | 10 | Healthy company, budget likely intact |
| sec_filing | 10 | M&A, material events = vendor re-eval |

Weights are from a production deployment that processed 30K+ accounts.
Competitor dissatisfaction was added in v2 after observing that negative
G2/Capterra reviews preceded vendor switches by 2-4 weeks.

## Time decay

Signals lose 5 points per week. A funding signal (weight 20) is worthless
after 4 weeks. This ensures the score reflects *current* intent, not
historical interest.

```
contribution = max(0, weight - (age_weeks * 5)) * confidence
```

## Confidence weighting

The extractor assigns a confidence score (0-1) to each signal. A vague
mention of "we might be hiring" gets 0.3; a posted VP role gets 0.9.
This prevents noise from overwhelming real signals.

## Rapid hiring bonus

If a company has 5+ executive/senior hire signals within 30 days, they get
a +15 bonus. This captures the "scaling fast" pattern that individual signals
miss.

## Alert cooldown

When a company crosses the threshold, one alert fires. No more alerts for
that company for 6 hours, regardless of new signals. This prevents the
"funding announcement + 5 job posts in one day" from sending 6 emails.

The score still updates--only notifications are suppressed.

## Score examples

**Scenario: Hot lead (score = 76)**
- Competitor dissatisfaction (G2 review, 2 days ago): max(0, 30 - 1.4) * 0.9 = 25.7
- Executive hire (VP Eng, 5 days ago): max(0, 25 - 3.6) * 0.8 = 17.1
- Funding (Series B, 1 week ago): max(0, 20 - 5.0) * 0.9 = 13.5
- Tech migration (3 days ago): max(0, 15 - 2.1) * 0.7 = 9.0
- Rapid hiring bonus (6 hires in 30 days): +15
- **Total: 80.3 → capped display, alert fires**

**Scenario: Stale lead (score = 12)**
- Funding from 3 weeks ago: max(0, 20 - 15) * 0.8 = 4.0
- Pain mention from 2 weeks ago: max(0, 10 - 10) * 0.7 = 0.0
- Executive hire from 10 days ago: max(0, 25 - 7.1) * 0.5 = 8.9
- **Total: ~12.9--not actionable**

## Tuning

Weights are config (`src/shared/config.py`). Change them, re-run the scorer
against existing signals to see new scores. No redeployment needed for Lambda
since they're env-var driven.
