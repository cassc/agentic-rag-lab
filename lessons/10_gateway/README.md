# Lesson 10 - LLM gateway: failover, routing, structured output, streaming

## The idea

Every agent step is a call to someone else's API. That API is slow, rate
limited, sometimes down, and it changes. If each agent talks to it directly,
each agent must solve this alone.

So: put **one gateway** between all agents and all providers.
`lab/gateway.py` (~120 lines) does what LiteLLM, Portkey, or an in-house
gateway do:

| Piece | In `lab/gateway.py` | Why |
| --- | --- | --- |
| Fallback chain | `Gateway.complete()` | A provider outage must not be your outage |
| Retries with backoff + jitter | `complete()` | Short errors go away; jitter stops all clients retrying in step |
| Retryable vs not | `RETRYABLE` | 429/5xx/timeout: retry. 400/401: your bug, fail at once |
| Circuit breaker | `open_until` | Stop paying the timeout of a dead provider on every request |
| Structured output | `structured()` | The model's text is input to code. Validate it like any input |
| Streaming | `stream()` | Users feel time to first token, not total time |
| One option name | `think=False` | Each provider has its own request fields; callers should not care |

Two real providers are used: DeepSeek direct, and the same model through
OpenRouter. Outages are simulated (`fail`, `hang`). All LLM calls are real.

## Run it

```sh
uv run lessons/10_gateway/run.py       # all (A-E), needs DEEPSEEK_API_KEY + OPENROUTER_API_KEY
uv run lessons/10_gateway/run.py D     # just one
```

## Results

**A. Retry vs fallback** (20 requests each):

| Policy | Primary fails 50% | Primary is down |
| --- | --- | --- |
| no retry, no fallback | 9/20 | 0/20 |
| 2 retries, same provider | 18/20 | **0/20** |
| fallback to a second provider | 20/20 | 20/20 |

Retries fix short errors. They do nothing in an outage - they only add load
to a provider that is already in trouble. Only a second provider fixes an
outage.

**B. Circuit breaker.** The primary hangs for 2 s and times out. 10 requests:

| Breaker | Total | Waiting on the dead provider |
| --- | --- | --- |
| off | 31.3 s | 20 s (every request pays the timeout) |
| open after 2 failures | 9.9 s | 4 s |

After the cooldown the breaker lets one request through to test the provider
again (half-open).

**C. Model routing.** 12 "does this order pass the filters?" checks, graded
by exact match:

| Route | Correct | Tokens/q (run 1 / run 2) | Seconds/q (run 1 / run 2) |
| --- | --- | --- | --- |
| flash (cheap) | 12/12 | 445 / 439 | 1.4 / 5.4 |
| pro (strong) | 12/12 | 550 / 617 | 5.6 / 3.5 |
| cascade: flash twice, pro if they disagree | 12/12 | 884 / 937 | 5.4 / 5.7 |

The cheap model was enough. The strong model used 25-40% more tokens for the
same score, and the cascade never called it (0 escalations) but still paid
double. Latency says nothing here: it changed more between two runs of the
same model than between the models (provider load). **Routing only pays
when the cheap model fails on some slice of traffic** - find that slice with
evals first, then route only that slice.

**D. Structured output.** 10 messy order messages ("dump 0.25 BTC @ 70k")
into `Order(symbol, side, quantity, price)`:

| Prompt | No repair | With repair (max 2 rounds) |
| --- | --- | --- |
| loose ("fields symbol, side, quantity, price") | 0/10 valid | 10/10 valid, 10 repair rounds |
| JSON schema in the prompt | 10/10 valid | 10/10, 0 repair rounds |

With the loose prompt every answer broke a rule the prompt never stated
(`symbol` must end in `USDT`). The validation error, sent back to the model,
fixed all 10 - at the price of a second call each. With the schema in the
prompt no repair was needed. **Valid is not correct:** in one run a market
order came back with `price: 0.0`, not `null`. It passed the schema. Only an
eval with expected values catches that.

**E. Streaming.** Same prompt, about 800 characters of answer:

| Thinking | First visible token | Total |
| --- | --- | --- |
| on (default) | 6.7 - 11.6 s | 7.2 - 12.1 s |
| off | 0.6 - 0.8 s (one run 5.7 s) | 1.4 - 1.6 s (one run 6.6 s) |

This model thinks before it answers, so with thinking on, streaming hardly
helps: the user stares at nothing for 7 s and then gets everything in 0.5 s.
Under a tight latency budget, turn thinking off for simple steps, or stream
the thinking as a progress signal.

**Two things I hit while building this:**

- `max_tokens=5` gave HTTP 200 with **empty content**: the thinking used the
  budget. A 200 is not a good answer. The gateway (or the caller) must check
  the content, and evals must cover "empty".
- Turning thinking off is `thinking: {type: disabled}` on DeepSeek and
  `reasoning: {enabled: false}` on OpenRouter. That is the case for one
  gateway: provider differences live in one place.

## What I would do in production

- Run the gateway as its own service: one place for keys, quotas per tenant,
  rate limits, cost and token accounting, audit logs, PII redaction.
- Fallback order per use case: same model on another provider first (same
  behaviour), a different model only as the last step (and only if the evals
  pass on it).
- Timeouts per step from the latency budget, not one global 60 s.
- Hedged requests for the slow tail: send a second request after the p95
  wait and take the first answer.
- Streaming with failover only **before** the first token. After that, the
  user has seen text and a switch would show.
- Prefer the provider's own schema-constrained output when it exists; keep
  validation anyway.

## Review questions

**Q: Why put a gateway between agents and LLM providers?**
> One place for failover, retries, rate limits, keys, cost tracking and
> provider differences. Agents call one stable interface. You can change
> provider or model without touching agent code.

**Q: Retry or fall back - when do you use which?**
> Retry (with backoff and jitter) for short errors: a timeout, a 429, a 503.
> Fall back to another provider when the errors continue. Never retry a 400
> or 401: the request is wrong and will fail again. In my test, retries
> lifted 9/20 to 18/20 on a flaky provider and did nothing (0/20) in an
> outage.

**Q: What does a circuit breaker add on top of fallback?**
> Fallback still tries the dead provider first on every request and pays its
> timeout. The breaker remembers: after N failures in a row it skips that
> provider for a cooldown, then lets one test request through. In my test
> it cut the time lost from 20 s to 4 s over 10 requests.

**Q: How do you get reliable structured output from an LLM?**
> Put the schema in the prompt (or use the provider's schema mode), parse,
> validate with a real validator, and on failure send the error back for a
> repair round, with a limit. Then test correctness with evals - a valid
> object can still be wrong.

**Q: How do you route between a cheap and a strong model?**
> By rule (task type), by a small classifier, or by a cascade (cheap first,
> escalate when it is unsure). Measure first: here the cheap model scored
> 12/12, so routing would only add cost. Route the slice where it fails.

**Q: A provider failover in the middle of a stream - what do you do?**
> Before the first token: switch silently. After: you cannot hide it. Either
> restart the answer and tell the client to drop the partial text, or buffer
> the stream on the server and accept a later first token.
