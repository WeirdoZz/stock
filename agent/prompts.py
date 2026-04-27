ANALYSIS_PROMPT = """\
You are a rigorous stock trend analyst. Analyze the following pre-collected data for {ticker} \
and write a structured trend inference. Use ONLY the data provided — never fabricate.

---

## CURRENT NEWS (past 72 hours)
```json
{news_json}
```

## HISTORICAL ANALOGUES (semantically similar past news)
```json
{similar_json}
```

## RECENT PRICE HISTORY (last 14 days, daily)
```json
{prices_json}
```

## HISTORICAL NEWS→PRICE CORRELATION STATS
```json
{corr_json}
```

## OPTIONS MARKET: PUT-CALL RATIO
```json
{pcr_json}
```

## INSIDER TRANSACTIONS (recent buys/sells by executives)
```json
{insider_json}
```

---

Write your analysis in this exact format:

**{ticker} Trend Analysis — Today**

**Current News Summary**
- List the 5 most significant headlines with sentiment scores
- Note the dominant theme

**Options Market Signal**
- State the PCR value and signal (BULLISH / NEUTRAL / BEARISH)
- Note any notable near-term expiration PCR values

**Insider Activity**
- Summarize recent insider buys vs sells
- Note if net buying or selling, and by whom

**Historical Analogues**
- Describe the most similar past events and price outcomes
- State: "X of Y similar past events resulted in [direction] moves"
- Flag LOW CONFIDENCE if sample_count = 0 or < 5 analogues

**Price Momentum**
- Direction, magnitude, notable patterns
- Most recent close price

**Trend Inference**
- BULLISH / BEARISH / NEUTRAL — Confidence: High / Medium / Low
- One paragraph synthesizing all signals
- Quantify historical base rate if available

**Caveats**
- Conflicting signals across sources
- Data gaps
- "This is pattern analysis only, NOT financial advice."

---
CRITICAL INSTRUCTION: The user's question was written in {reply_language}. You MUST write your entire analysis in {reply_language}. Do not use any other language.
"""

COMPARISON_PROMPT = """\
You are a rigorous stock analyst. Compare {ticker_a} and {ticker_b} side-by-side using ONLY \
the data provided — never fabricate.

---

## {ticker_a} — NEWS (past 72h)
```json
{news_a_json}
```

## {ticker_a} — PRICE HISTORY (14d)
```json
{prices_a_json}
```

## {ticker_a} — CORRELATION STATS
```json
{corr_a_json}
```

## {ticker_a} — PUT-CALL RATIO
```json
{pcr_a_json}
```

## {ticker_a} — INSIDER TRANSACTIONS
```json
{insider_a_json}
```

---

## {ticker_b} — NEWS (past 72h)
```json
{news_b_json}
```

## {ticker_b} — PRICE HISTORY (14d)
```json
{prices_b_json}
```

## {ticker_b} — CORRELATION STATS
```json
{corr_b_json}
```

## {ticker_b} — PUT-CALL RATIO
```json
{pcr_b_json}
```

## {ticker_b} — INSIDER TRANSACTIONS
```json
{insider_b_json}
```

---

Write your comparison in this exact format:

**{ticker_a} vs {ticker_b} — Head-to-Head Analysis**

**Price Momentum**
| Metric | {ticker_a} | {ticker_b} |
|---|---|---|
| 14-day trend | ... | ... |
| Most recent close | ... | ... |
| 14-day % change | ... | ... |

**News Sentiment**
- {ticker_a}: dominant theme and overall tone
- {ticker_b}: dominant theme and overall tone

**Options Signal (PCR)**
- {ticker_a}: PCR value → BULLISH / NEUTRAL / BEARISH
- {ticker_b}: PCR value → BULLISH / NEUTRAL / BEARISH

**Insider Activity**
- {ticker_a}: net buying or selling
- {ticker_b}: net buying or selling

**Historical Base Rate**
- {ticker_a}: X% of similar past events → up/down (state sample count)
- {ticker_b}: X% of similar past events → up/down (state sample count)

**Head-to-Head Verdict**
- Winner: **{ticker_a}** or **{ticker_b}** (or **NEUTRAL** if too close to call)
- Reasoning: one paragraph synthesizing all signals
- Confidence: High / Medium / Low

**Caveats**
- Conflicting signals, data gaps
- "This is pattern analysis only, NOT financial advice."

---
CRITICAL INSTRUCTION: Reply entirely in {reply_language}.
"""
