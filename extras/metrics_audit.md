# ShopZetu Platform — Metrics Audit

Every computed figure in `app/analytics.py`, `app/customers.py` and the frontend,
checked against what its label claims. Shopify-sourced money figures are excluded
(those are being replaced by ShopifyQL).

Ordered by severity. Each entry: **what it says** / **what it does** / **verdict**.

---

## 🔴 BROKEN — wrong numbers on screen right now

### 1. Total Revenue is divided by VAT twice
`app/customers.py`, `customers_overview`

```python
VAT_DIVISOR = 1.16
total_revenue = ex_vat(...) / VAT_DIVISOR
```

`ex_vat()` already divides by 1.16. This divides again → **÷1.3456**.
`avg_aov` derives from it, so that's wrong too.

**Fix:** delete `/ VAT_DIVISOR` and the local `VAT_DIVISOR = 1.16` line.
`ex_vat()` on its own is correct.

---

### 2. VIP threshold is a hardcoded fallback, not a percentile
`app/customers.py`, `_vip_threshold()`

```python
p75 = ...percentile_cont(0.75)...over ALL customers
return float(p75 or 50000)
```

77% of customer records have `total_spent = 0` (161,865 total, 36,822 buyers).
The 75th percentile therefore lands **inside the zero band** → `p75 = 0` → `0 or 50000`
is falsy → returns **50,000 every time**.

So the docstring ("top 25% of spenders") is false, and the VIP segment is defined by
an arbitrary constant that nobody chose deliberately.

**Fix:** compute the percentile over buyers only —
`.filter(CustomerCache.total_orders > 0)` — which makes it mean what it says.
Expect the VIP count to change noticeably.

---

### 3. Override rate divides conversations by messages
`frontend/src/pages/Dashboard.jsx` and `Analytics.jsx`

```js
overrideRate = human_override_total / ai_replies_total
```

Numerator counts **conversations** (`ai_enabled=False`, never escalated).
Denominator counts **messages**. The ratio has no meaning — it shrinks purely
because the AI sends multiple messages per conversation.

**Fix:** denominator should be `conversations_total`, or expose an
`ai_handled_conversations` count and use that.

---

### 4. Conversion rate's numerator isn't inside its denominator
`app/analytics.py`

- Denominator: conversations that received a tracked link **in the window**
- Numerator: conversations with an order **dated in the window**

An order placed today against a recommendation from last month lands in the
numerator but not the denominator. The rate can exceed 100%, or understate badly,
depending purely on window length.

**Fix:** anchor both on the same set — take conversations recommended in the window,
then count how many of *those* later ordered (with a defined attribution window,
e.g. 30 days).

---

## 🟠 MISLEADING — technically computing something, but not what the label says

### 5. "Retention Rate" is not retention
`app/customers.py`: `repeat / total` where `total` = **all customer records**,
including the ~125,000 who never bought anything.

It answers "what share of all signups have ordered twice", which is a
signup-to-repeat-purchase rate, not retention.

**Fix:** denominator should be customers with ≥1 order. Both numbers are worth
showing, but they need different labels.

---

### 6. Intent percentages are per-mention, not per-message
`app/analytics.py`: intents are stored pipe-joined (`greeting|order_status`),
split and tallied. A message with 3 intents contributes 3 to the total.

Percentages are therefore "% of intent mentions", but the donut's centre label
reads **"messages"**.

**Fix:** either relabel to "mentions", or divide by message count instead of
mention count. Don't leave both readings live.

---

### 7. Channel split counts replies as traffic
`app/analytics.py`: counts **all** messages per channel — inbound and outbound.
A channel where the AI is chatty looks busier than one where customers actually are.

**Fix:** for a traffic view, filter `direction == 'inbound'`. If total volume is
wanted, say so in the label.

---

### 8. "Most asked-about products" counts repeats within one conversation
`app/analytics.py`: counts messages carrying a `product_url`. If the AI recommends
the same item five times in one thread, it scores five.

**Fix:** `.distinct()` on `(conversation_id, handle)` for a demand signal;
keep the raw count only if you specifically want recommendation volume.

---

### 9. Customer-profiling "top products" ignores time and order status
`app/customers.py`, `customers_overview`: unnests `products` across **every order
ever**, with no date window and no `financial_status` filter — so voided and
refunded orders count as demand.

**Fix:** add the same status filter used elsewhere, plus a window.

---

### 10. Success rate penalises one-and-done conversations
`app/analytics.py`: "engaged" = ≥2 inbound messages **or** an attributed order.

A customer who asks one question, gets a perfect answer, and leaves satisfied
scores as **not** engaged. The metric rewards conversations that needed more
back-and-forth.

It reads 100% today only because every test conversation is multi-turn. It will
fall on real traffic for the wrong reason.

**Fix:** rename to "Engagement rate" (accurate), or define success separately —
answered without escalation and without a complaint intent.

---

## 🟡 WORTH KNOWING — defensible, but document it

### 11. Denominators shift when AI is toggled off
`ai_eligible_conv_ids` filters on the **current** `ai_enabled` flag. Disabling AI
on a conversation retroactively removes all its historical inbound from every
eligibility-based metric. Yesterday's numbers change because of a toggle today.

### 12. Agent scoping vs global business KPIs
`_scope_filter` limits agents to their assigned conversations, but `conversion` is
deliberately global. An agent's dashboard therefore mixes personal and company-wide
figures with no visual distinction.

### 13. "New this month" is a rolling 30 days
Not calendar month. Fine — the label should say "last 30 days".

### 14. Segment "new" requires exactly 1 order within 30 days of signup
A customer who joined 40 days ago with one order becomes `regular`, never `new`.
Deliberate, but non-obvious.

### 15. Average response time changed meaning
The 5-second `time.sleep()` before finalizing the outbound was removed. Any
`ai_response_time_ms` recorded before that change is on a different basis than
after it. Historical comparisons across that date are invalid.

---

## ✅ CHECKED AND SOUND

- **RFM quintiles** — `NTILE(5)` is a ranking; immune to scaling errors. Correct.
- **Segment counts** — indexed `GROUP BY` on a persisted column. Correct.
- **`compute_segment`** — compares raw spend against a raw threshold; internally
  consistent (the threshold value itself is the problem, see #2).
- **Simple counts** — total customers, repeat buyers, conversations, escalations,
  messages, inbound, AI replies, human replies. All plain filtered counts.
- **Previous-window comparison** — `previous_start = cutoff - days` is correct.
- **Weekly chart** — inbound vs AI-replied per day, straightforward.
- **Failure breakdown** — reads real `ai.generator.failure` logs. Correct since
  the earlier fix.
- **Response rate** — correct once the conversation-level fix is applied.

---

## NOT AUDITED

- **LTV projection** (`CustomerDetail.jsx`) — computed in the frontend, not read.
- **Conversion attribution writer** — how `ConversionAttribution` rows get created
  from `utm_token` was never verified end to end. Worth testing with a real order,
  since every conversion metric depends on it.
- **`aggregate_orders`** in `ai_query.py` — the AI assistant's own aggregation path.

---

## THE PATTERN

Almost every problem above is one of two shapes:

1. **Grain mismatch** — a ratio whose numerator and denominator count different
   kinds of thing (messages vs conversations, mentions vs messages).
2. **Denominator drift** — the denominator silently includes rows the label
   doesn't imply (never-bought customers in retention, zero-spenders in the
   percentile, voided orders in demand).

Neither shows up in testing, because both produce plausible-looking numbers.

**The durable fix is a definition line per KPI** — question, numerator,
denominator, grain, source, exclusions — written before the query. Most of these
become obvious the moment numerator and denominator are written on the same line.
