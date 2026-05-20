# Scoring Rubric

Scores are conservative and should prefer durable usefulness over hype.

## Weights

| Factor | Weight |
| --- | ---: |
| Domain relevance | 20 |
| Practical usability evidence | 15 |
| README / documentation clarity | 12 |
| Maintenance activity | 12 |
| Community signal | 10 |
| Recent 3-day star growth | 10 |
| License friendliness | 8 |
| Novelty | 8 |
| Safety / compliance controllability | 5 |

## Growth Metrics

Star growth must come from local snapshots. If the app does not have enough local history, it must write `insufficient_history` instead of guessing.

Growth windows:

- 3 days: daily ranking boost
- 7 days: short-term validation
- 30 days: durable trend

## Penalties

| Signal | Penalty |
| --- | ---: |
| Archived repository | hard exclude |
| Fork or mirror | -30 |
| Thin README | -15 |
| Unclear license | -8 |
| Stale repository | -15 |
| Trading-bot noise | -20 |
| Marketing-only repo | -12 |
| Sensitive permission requirements | -15 |
| Abnormal star/fork ratio | -10 |
| Keyword stuffing | -10 |

## Recommendations

Recommended lifecycle labels:

- `new`
- `watch`
- `deep_read`
- `trial_later`
- `ignore`
- `archived`
