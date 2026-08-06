# AI & Automation, explained

Two tabs on one page: how the assistant behaves, and the rules that override it.
Written so you can answer "what does that do?" without preparation.

---

## 1. What this section controls

**AI Settings** shapes *how* the assistant writes — its tone, its length, how
hard it sells, and the standing instructions it receives before every reply.

**Automation Rules** are exceptions that fire *before* the assistant writes at
all. A rule can answer for it, or hand the conversation to a person.

Between them they decide what a customer hears back. That is why the whole
section is **admin-only**.

---

## 2. The security hole that was here

Worth knowing, because it shaped the rest of the work.

Every endpoint behind both tabs carried a login check and **nothing else**. The
sidebar hides this section from agents, but that is the interface — the
endpoints were reachable directly by anyone signed in.

What that allowed, concretely: **rewriting the system prompt that governs every
reply to every customer**, changing the tone and personality, resetting the
whole configuration, and creating, editing, reordering, toggling or deleting
automation rules.

The handlers even notified admins afterwards. The code *expected* only admins to
reach them while permitting everybody.

Now: reading is open to admins and supervisors, **every change is admin-only**,
and the check is defined once so a route added later cannot skip it by being
written without it. Verified per role across all ten routes.

> **The general lesson**, and it recurred on the Products page too: *is the
> button hidden, or is the action actually prevented?* A `roles` array in the
> sidebar is decoration. Only the endpoint decides.

---

## 3. AI Settings

### Brand tone

Five presets. The starting point for everything below.

### The three sliders

They used to read "Formality 50%", which tells you nothing about what the
assistant will actually do. Each now reads its position back in words:

Each also shows its number, so you can read the exact value back rather than
eyeballing the handle position.

The words are not a paraphrase. They are the generator's own buckets, which
`_slider_bucket()` picks on `value <= ceiling` at **25 / 50 / 75 / 100** — four
bands, not three:

| Value | Formality | Response length | Sales focus |
|---|---|---|---|
| **0-25** | Casual — contractions welcome | Under 2 sentences | Answers only, no pitching |
| **26-50** | Casual but polite | 2-3 sentences | Light nudge when relevant |
| **51-75** | Professional, no slang | 4-6 sentences | Suggests a product after answering |
| **76-100** | Formal — no contractions | Up to 8 — anticipates follow-ups | Always closes with a call to action |

This page previously described three bands split at 33 and 66, which meant the
label and the instruction disagreed across whole stretches of the scale. At 60,
the page read "Warm but businesslike" while the model was being told "Lean
professional. Avoid slang." Anyone tuning by the label was tuning against a
description of something else.

**One case ignores the length slider on purpose.** A comment routed into a DM
is written to a fixed "4-8 short lines" instead, because the public reply has
already promised the customer all the details — see
[AUTOMATION_ENGINE_EXPLAINED.md](AUTOMATION_ENGINE_EXPLAINED.md). Tone,
formality and sales focus still apply there.

### System prompt — the powerful one

**This governs every reply, on every channel, to every customer.**

It was presented as a plain textarea with a character count, visually identical
to the tone picker above it. It now carries an amber edge and an "Affects every
reply" badge, and warns you if you empty it — because an empty prompt means the
assistant answers with no standing instructions at all.

Treat a change here the way you would treat editing a script your whole team
reads from.

### Response rules

Four on/off switches for specific behaviours — greeting new conversations,
mentioning nationwide delivery, emoji, suggesting alternatives when something is
out of stock.

### Saving

Save appears **only when something has changed**, in a bar that follows you down
the page, and it names what changed — *"brand tone, system prompt"* — rather
than just asserting that something did.

It used to sit in the header, so you would edit four sections below it and
scroll back to the top to commit. The page also had no idea whether anything was
unsaved; leaving mid-edit was silent. It now warns you.

**Reset** moved to the foot of the page, in a red panel that says what it
destroys. It used to sit immediately beside Save at equal weight — one click
from wiping the configuration, next to the button you press constantly.

---

## 4. Automation Rules

### The one thing that matters most

> **Only the first matching rule runs.**

They are checked top to bottom, after the message's intent is worked out and
before the AI writes anything. Drag to reorder.

That note used to sit **underneath** the list, so you read five rules without
knowing that only one of them fires. It is now above them.

### Reading a rule

Each rule is an **IF** and a **THEN**:

| Rule | IF | THEN |
|---|---|---|
| Out of Stock | Shopify stock = 0 | Reply "currently out of stock" + suggest similar |
| Comment → DM | Comment contains "price?", "how much?" | Reply publicly "Check your DMs!" + start a DM |
| Complaint Escalate | Intent = complaint | Flag for human review + send an empathy reply |
| Order Status | Intent = order_status | Ask for the order number + flag for follow-up |

### The number badge

It shows the position the rule will actually be **checked** in — not its
position in the list.

Those differ whenever a rule is disabled. With rule 2 switched off, the old
badges read 1, 2, 3, 4 — implying four things run, when the second never fires.
A disabled rule now shows a dash instead of a number it does not own, and the
whole row dims, because a rule that never runs should not look like one that
does.

### Dragging

Only the grip handle on the left is draggable. The whole card used to be, so
hovering anywhere — including over Edit and Delete — suggested you were about to
drag something.

---

## 4a. Deciding a conversation needs a person

You cannot write down every reason a customer needs a human. Complaints and
abuse are easy to name; wholesale enquiries, press requests, legal demands,
safety issues, payment disputes and "I have asked this three times now" are
not, and next week brings one nobody thought of.

So the classifier decides, on the same principle as the praise gate for public
comments: **judge the situation, not the vocabulary.**

### What changed

There is a list of escalation keywords — `refund`, `broken`, `manager`,
`missing`, `damaged`, `angry` and a dozen more. It used to run **first**, and
win outright. The AI's judgement was consulted only if no keyword matched.

That cost in both directions. It missed anything phrased outside the
vocabulary. And a bare word match cannot tell a problem from a mention of one:

| Message | Old verdict | Actually |
|---|---|---|
| "do you do refunds if the size is wrong?" | escalated (`refund`, `wrong item`) | a policy question |
| "is the zip broken like the reviews say?" | escalated (`broken`) | a product question |
| "am I missing something, is there a code?" | escalated (`missing`) | a discount question |
| "who's the manager at Moi Avenue?" | escalated (`manager`) | a shop question |

Each of those pulled an agent onto a question the assistant could answer from
the catalogue.

### The order now

1. **Automation rules.** An admin configured this deliberately — a standing
   instruction outranks a judgement call.
2. **The classifier's verdict**, plus the intents that always need a person
   (`complaint`, `order_request`). Both come from the same reading of the
   message.
3. **Keywords — only if the classifier never ran.**

When the classifier is healthy and says no, that is the answer. Running the
keyword list underneath it would reinstate every false positive above.

### The escape hatch

`other` is now a valid handoff reason, and the prompt is explicit that it is
not a synonym for "unsure" — it is for real situations nobody listed. Without
it the classifier had two bad options: force a genuine escalation into a label
that misdescribes it, or not escalate.

### Why `degraded` is carried separately

"The AI read this and saw nothing needing a person" and "the AI never ran" both
arrive as `{should: False}`. They mean opposite things. The classifier now
reports `degraded`, and it is threaded through to the handoff check — because
without it, a classifier outage reads as a clean bill of health, and every
complaint that week gets answered by a bot.

In the degraded path the keywords come back, deliberately over-eager. A
customer routed to a person unnecessarily is inconvenienced; abuse or a
complaint left with a bot is not. The fallback logs
`handoff.keyword_fallback` so those escalations are distinguishable afterwards.

---

## 4b. When the AI cannot answer at all

The API can refuse: rate limits, timeouts, an expired key, an account out of
credit. Something still has to happen to the customer waiting.

**It used to send a template.** `_mock_reply()` assembled a sentence from
whatever product data was already in hand. On 6 August 2026 the Anthropic
account ran out of credit and customers were sent:

> Yes, the Afriwia Africana Kimono is available — we have 7 units in stock! ✅
> Would you like to place an order? 😊

Factually true, and useless. No price, no delivery, no link — and nothing in
the inbox marking it as canned, so an agent reading the thread would have
concluded the customer had been helped. Three subsystems were down at once
(classifier, vision, generator) and the inbox looked completely normal.

**It now escalates.** The conversation goes to `human_override`, an agent is
auto-assigned, supervisors are notified, and the customer gets the standard
handoff line — "I'm connecting you with a member of our team". No invented
answer, and a person is already on it.

The escalation is recorded as its own reason, `ai_unavailable`, rather than
being folded in with the others. Two different questions both get asked, and
they have different answers:

- *How many customers needed a human?* — complaints, order requests. The system
  working.
- *How many times did our AI fall over?* — this. Not the system working.

Two details worth knowing:

- **A thread already with an agent is not re-escalated.** It would reassign the
  conversation and fire a second round of notifications at whoever is mid-reply
  to that customer.
- **The template code is still there**, one environment variable away:
  `AI_FAILURE_FALLBACK=template` restores the old behaviour exactly. The
  default is `human`, and an unrecognised value falls back to `human` rather
  than failing open into sending templates.

---

## 5. Honest limitations

- **Rules are free text.** The IF and THEN are descriptions, not a validated
  expression language. Nothing checks that a trigger you type will ever match.
- **Deleting a rule is recoverable only through the audit trail**, and only for
  deletions made after this work — the audit entry used to record just the
  rule's name, which is enough to know something vanished and useless for
  putting it back. It now snapshots the whole rule.
- **There is no preview.** You cannot see what a rule would have done to past
  conversations before enabling it.

---

## 6. The one-paragraph version

AI Settings shapes how the assistant writes; Automation Rules are exceptions
that fire before it writes at all, and only the first matching rule runs. Both
were reachable by any logged-in user, including agents, which meant anyone could
rewrite the instructions behind every customer reply — that is closed, and the
check now lives in one place. The rest of the work was making the page say what
it does: sliders that describe their effect rather than showing a percentage, a
system prompt marked as the powerful thing it is, a save bar that names what
changed, and rule numbers that reflect what will actually run rather than what
happens to be on screen.
