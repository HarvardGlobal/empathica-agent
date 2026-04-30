# Health Literacy Scoring Framework

Source: project design document (see conversation history for full derivation).

## Reading-Level Mapping

| Level    | Grade Level | Description |
|----------|-------------|-------------|
| Low      | 4–6         | Simple vocabulary, short sentences, emotional/safety focus. Aligned with AHRQ/CDC plain language guidelines. |
| Moderate | 7–9         | Basic medical terms, practical questions, structured sentences. Reflects average adult literacy. |
| High     | 10+         | Technical pharmacological terms, multi-clause analytical questions, clinical/research framing. |

---

## Scoring Algorithm (deterministic — implemented in scorer.py)

### Per-message scoring

**A. Vocabulary score (0–1 per class)**

Match message against `LOW_WORDS`, `MODERATE_WORDS`, `HIGH_WORDS` in `wordlist.py`.

```
low_vocab  = low_count  / total_matches
mod_vocab  = mod_count  / total_matches
high_vocab = high_count / total_matches
```

**B. Sentence complexity score (0–1)**

```
< 6 words               → 0.2
6–15 words, no clauses  → 0.5
> 15 words or clauses   → 0.8–1.0
```

**C. Intent score (0 or 1 per class)**

Match against `INTENT_LOW`, `INTENT_MODERATE`, `INTENT_HIGH` in `wordlist.py`.

**D. Raw class scores (weighted combination)**

```
low_raw      = 0.5 * low_vocab  + 0.3 * (1 - complexity) + 0.2 * intent_low
moderate_raw = 0.5 * mod_vocab  + 0.3 * mid_complexity   + 0.2 * intent_mod
high_raw     = 0.5 * high_vocab + 0.3 * complexity       + 0.2 * intent_high
```

**E. Normalize → probabilities**

```
total = low_raw + moderate_raw + high_raw
low_prob = low_raw / total  (etc.)
```

**F. Classification confidence**

```
confidence = top_prob - second_highest_prob
```

**G. Signal quality (0–1)**

```
word_count < 4               → +0.2  else +0.3
no medical terms             → +0.0  else +0.3
clear medication context     → +0.3
multiple signals present     → +0.2
cap at 1.0
```

**H. Message confidence**

```
message_confidence = 0.7 * classification_confidence + 0.3 * signal_quality
```

---

### Session-level scoring (across messages)

```
majority_label  = most frequent label
consistency     = count_majority / total_messages
final_confidence = 0.6 * avg_message_confidence + 0.4 * consistency
```

**Not yet stable**: if `final_confidence < 0.5`, continue collecting messages before locking in a level.

---

## Guardrails

- If technical terms are used incorrectly → treat as Moderate
- If level is ambiguous → default to Moderate
- Combine keyword detection with intent analysis (e.g. "why" + "mechanism" → high)