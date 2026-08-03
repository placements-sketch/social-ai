# The automation rule engine — what was broken, and what it does now

Companion to `AI_AUTOMATION_EXPLAINED.md`. That document covers the AI settings
(tone, sliders, response rules). This one covers **automation rules** — the
IF/THEN list — which is where the real problem was.

---

## 1. The state it was in

The API accepted **seven** action types and **five** trigger types. Exactly
**one** action type had an executor.

Of the five rules in the database, all showing a green **Enabled** pill:

| # | Rule | Reality |
|---|---|---|
| 2 | Out of Stock | Could not fire — `shopify_stock` trigger had no evaluator |
| 3 | Comment → DM | Could not fire — `trigger_dm_flow` action had no executor |
| 4 | After Hours | Did nothing — `normal_reply` was skipped entirely |
| 5 | Complaint Escalate | Fired **by accident** (see below) |
| 6 | Order Status | Fired **by accident** |

### The accident

Two engines matched rules, on **two different fields**:

- `services.py` matched the structured `trigger_config` / `action_config` JSON,
  and only ever acted on `action_config.type == "reply_template"`.
- `handoff.py` matched by substring-searching the free-text **`action`
  description column** for the words `"human"`, `"escalate"`, `"notify_agent"`.

So rules #5 and #6 escalated because somebody had *typed the word "human" in the
description*, not because of how they were configured. Rewording
"Flag for human review" to "Send this to an agent" would have silently switched
both off. Nothing in the UI would have changed.

---

## 2. What was built

### The matcher

`_check_template_rule` became `_match_automation_action`, which returns the
matched rule **and its action** instead of just a template string. Rules are
evaluated in `sort_order`, first match wins.

It runs in **two passes**, because a stock rule cannot be judged before we know
which product the customer means:

| Pass | Where | Triggers |
|---|---|---|
| 1 | Step 3.6 — before the Shopify fetch | `keyword`, `intent`, `always`, `channel` |
| 2 | Step 4.6 — after the fetch **and after the live stock refresh** | `shopify_stock` |

Pass 1 stays before the Shopify call deliberately: a canned reply should
short-circuit fast rather than wait on a network round-trip it doesn't need.

Pass 2 sits after the *live* stock refresh, not just the cached figures, so an
"out of stock" rule is judged on the same number the customer would see on the
site — not whatever the last sync wrote hours ago.

### `shopify_stock`

```
{"type": "shopify_stock", "condition": "eq" | "lte" | "lt" | "gte" | "gt", "value": 0}
```

Judged on the **best match only** — `products[0]` — not "any product in the
list". We return up to three candidates, so an `any()` would have fired an
out-of-stock rule because the third-best *alternative* happened to be sold out,
while the item the customer actually asked about was in stock.

A non-numeric `value` **does not fire**. It used to fall back to `0`, which
meant a broken config like `{"value": "zero"}` matched every sold-out product
and sent a real customer-facing reply off the back of a typo.

### `trigger_dm_flow`

Moves a public comment into a DM. This needed a new integration function —
`send_instagram_private_reply()` — because you **cannot** message a commenter
through the normal send API: you have their comment-author ID, not their IGSID.
Meta's `/{comment_id}/private_replies` endpoint resolves that. It works once per
comment, within 7 days, and only if the person accepts DMs.

The order matters: **the DM is attempted first.** If Meta refuses, the public
reply falls back to wording that does not claim a DM was sent.

| Outcome | Public reply |
|---|---|
| DM opened | "Check your DMs!" |
| DM refused | "Thanks for asking! Drop us a DM and we'll help you out." |

Verified both ways — the "check your DMs" claim only ever goes out when a DM
actually went out. Telling a customer to check an inbox that has nothing in it
is worse than answering them in the open.

### `ask_order_number`

Implemented as **asking for the full name and email**, not an order number.

This is a deliberate deviation from the action's name, and it is worth being
able to defend: `_lookup_order_status(email, name_tokens)` finds orders by email
plus name. It has no way to search by order number, and the AI's own prompt
already says *"Do NOT ask for an order number"* for that reason. Asking for a
number would collect something the system cannot use and leave the customer
believing they'd been helped.

An admin who wants different wording sets `action_config.prompt_text`.

### `include_price`

The only action that **shapes** the reply rather than replacing it. It sets
`force_include_price` on `context_data`, and `generator.py` turns that into a
prompt line instructing the assistant to state the price in KES explicitly.

### `normal_reply`

Genuinely does nothing — and that is the point. Because rules are
first-match-wins, a `normal_reply` rule **matching** stops every rule below it
from firing. Put one above a broad canned-reply rule and you have carved out an
exception where the assistant answers properly instead. It is now reported in
the UI as **"No effect"** with that explanation, rather than looking active.

### Escalation, de-fragilised

`handoff.py` now decides escalation from `action_config.type`
(`human_escalate`, `notify_agent`, `ask_order_number`). The old free-text
substring match is kept only as a fallback for rules created before
`action_config` existed. The set of escalating actions lives in **one place**
(`automation.py`) and is imported by `handoff.py`, so the two cannot drift.

---

## 3. Unreachable rules are now visible

Building everything exposed a second problem: rules can be **misordered**.

"After Hours" triggers on `always`. First match wins. So every rule below it in
the same pass is unreachable — dead code with a green Enabled pill.

The API now returns an `execution` object with every rule, and the UI badges
them **"Never runs"** or **"No effect"** with the reason. Three cases
deliberately do **not** warn, because warning would be a false alarm:

| Case | Warns? | Why |
|---|---|---|
| Catch-all above a canned-reply rule | **Yes** | Genuinely unreachable |
| Catch-all above an **escalation** rule | No | `handoff.py` scans every rule independently — not first-match-wins |
| Catch-all above a **stock** rule | No | Different pass |
| **Disabled** catch-all | No | Disabled rules match nothing |
| Comment-scoped catch-all above a **DM** rule | No | Different channel |
| Comment-scoped catch-all above a **comment** rule | **Yes** | Same channel |

All six cases are covered by tests and pass.

---

## 4. Where each rule stands now

```
RUNS   #2  Out of Stock
RUNS   #3  Comment → DM
NO-OP  #4  After Hours          (by design — suppresses rules below it)
RUNS   #5  Complaint Escalate
RUNS   #6  Order Status
```

Was: 3 dead, 2 firing by accident. Now: 4 firing for the right reason, 1
honestly labelled.

---

## 5. Failure behaviour

Every action is best-effort. A failure is logged and downgraded to "no reply",
which falls through to the normal AI path. **A broken rule must never cost the
customer their answer.** Verified: an action that raises, an action with an
empty template, an unknown action type, and a `trigger_dm_flow` with no comment
ID all return no reply and let the assistant answer normally.

---

## 6. Questions you might get

**"How do you know the rules work now rather than just being wired up?"**
Each action was exercised with its side effects stubbed: the DM path both when
Meta accepts and when it refuses, the stock trigger with the best match in stock
and out of stock, every comparison operator, malformed config, and the crash
path.

**"Why is 'After Hours' marked as having no effect — is it broken?"**
No. It is doing exactly what a `normal_reply` rule does: matching, and thereby
stopping any rule below it. The badge tells you it sends nothing itself, so
nobody wastes time wondering what it did.

**"Did this need a database change?"**
No. Rules already had `trigger_config` and `action_config` columns; the problem
was that almost nothing read them. There is no SQL step for this work.

**"What is still not built?"**
Nothing in the accepted type lists. All five trigger types and all seven action
types are now either executed or honestly reported as a no-op.
