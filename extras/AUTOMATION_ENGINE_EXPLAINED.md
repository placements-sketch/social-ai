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

`_check_template_rule` became `_match_automation_actions`, which returns **every
rule that applies**, in `sort_order`, instead of just a template string.

### What happens when several rules match

"First match wins" is right for actions that **answer** the customer — you
cannot send two canned replies to one message, so the first such rule wins and
everything below it is skipped.

It is wrong for actions that only **shape** the reply the assistant was going to
write anyway. `include_price` adds a line to the prompt; it sends nothing.
Treating it as terminal meant an `include_price` rule near the top quietly
switched off every rule beneath it — ask about a sold-out item and you'd get the
price mentioned but never the out-of-stock reply.

So actions fall into two kinds:

| Kind | Actions | Effect on evaluation |
|---|---|---|
| **Directive** | `include_price` | Accumulates; evaluation **continues** |
| **Terminal** | `reply_template`, `trigger_dm_flow`, `ask_order_number`, `human_escalate`, `notify_agent`, `normal_reply` | Applies, then **stops** |

Evaluation therefore collects any leading run of directive rules plus the first
terminal rule. Verified:

| Rules that match | Applied | Skipped |
|---|---|---|
| `include_price`, then `reply_template` | both | — |
| two `reply_template` | the first | the second |
| `include_price`, `include_price`, `reply_template`, `reply_template` | first three | the last |
| `normal_reply` above a broad `reply_template` | `normal_reply` only | the canned reply |

Escalation is a **third, separate mechanism**: `handoff.py` runs earlier
(Step 3.5) and scans every enabled rule independently rather than
first-match-wins, so a catch-all sitting above an escalation rule does not stop
it reaching a human.

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
Meta resolves that from the comment. It works once per comment, within 7 days,
and only if the person accepts DMs.

The two Instagram logins do not share an endpoint here, unlike every other
sender in `meta.py`:

| Login | Endpoint | Body |
|---|---|---|
| Instagram Login | `POST {ig_user_id}/messages` | `{"recipient": {"comment_id": …}}` |
| Facebook Login | `POST {comment_id}/private_replies` | `{"message": "…"}` |

Under Instagram Login a private reply is simply a message whose recipient is
named by comment instead of by IGSID. It also answers with `message_id` rather
than `id`, so the response is normalised before returning — otherwise the DM
saves with a NULL `external_id` and the inbox reads it as undelivered.

#### The DM carries the real answer

The action originally answered at rule-match time, which is Step 3.6 — *before*
the Shopify match, the price and the stock level are fetched at Step 4. So the
DM could only ever be a fixed string from `action_config`. The result was a
public reply promising "we've sent you a DM with all the details" followed by a
DM that opened with "what would you like to know?" — the customer had just told
us, in the comment, and we discarded it to ask again.

It now defers instead. The rule sets a `_dm_handoff` directive, the pipeline
runs normally and the AI generates its real answer, and Step 6 routes it:

| Where | What lands there |
|---|---|
| The DM | the AI's actual answer — product, price, stock, link |
| Under the post | the short teaser, e.g. "Check your inbox! 💌" |

**The DM is attempted first**, and the teaser is only posted once the DM has
succeeded. The "check your DMs" claim can therefore never go out to an empty
inbox. If Meta refuses, the answer is posted publicly instead — the customer
gets it where they asked rather than being pointed at nothing.

| Outcome | Public reply | DM |
|---|---|---|
| DM opened | "Check your inbox! 💌" | the full answer |
| DM refused | the full answer | — |

Note the directive is popped out of the rule directives before the rest are
merged into `context_data`; it is a routing instruction, not context, and the
generator should never see it.

#### Telling the generator where its words will land

Deferring was not enough on its own. The first DM that went out read:

> It comes in: XS, S, M, L, XL. Would you like to place an order? 😊

Correct, and useless — underneath a public reply announcing "a DM with **all
the details**". No price, no delivery, no link. Three things caused it, and all
three were about the message being written for the wrong place:

1. The system prompt said *"You are responding via instagram comment"*, because
   that is the channel the message arrived on. So it wrote a comment.
2. The **length slider** was applying its low bucket — "Keep replies under 2
   sentences when possible". The reply was exactly two sentences. The setting
   was doing its job; it is simply the wrong job for a DM.
3. `CLAUDE_MAX_TOKENS` is 300, sized for comment replies. A full briefing would
   have been cut off mid-sentence, which reads as broken rather than brief.

A single flag, `context_data['deliver_as_dm']`, now fixes all three: the prompt
says `instagram dm`, the length line is replaced with "4-8 short lines", the
token ceiling lifts to 700, and an instruction requires the product name, the
price in KES, in-stock sizes, delivery cost and timeframe, and the buy link.

The instruction ends with *"Omit only what is genuinely not in the data — never
guess a figure to fill a gap."* Asking for more detail is exactly the request
that invites invented prices, and the constraint against fabricating figures has
to be restated where the pressure is applied.

Nothing else changes: tone, formality and the sales slider still apply, and
every other reply in the system keeps the tuned length and token budget.

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
| **Directive** catch-all (`include_price`) above anything | No | Directives don't stop evaluation |
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
