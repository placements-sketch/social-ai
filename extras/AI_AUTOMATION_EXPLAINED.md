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

| Slider | Left | Right |
|---|---|---|
| **Formality** | Chatty and informal | Polished and professional |
| **Response length** | Short, to the point | Full explanations |
| **Sales focus** | Answers only, no pitching | Actively suggests products |

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
