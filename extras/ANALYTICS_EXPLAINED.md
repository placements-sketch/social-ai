# The Analytics page, explained

How to read every number on this page, and what to do about it. Written so you
can answer "what does that mean?" without preparation.

All example figures below are real, taken from the development database over a
90-day window.

---

## 0. Two things to establish first

### Who the numbers cover

There is a line at the top of the figures for agents:

> Every figure below covers **your assigned conversations only** — not the whole
> business.

This is not decoration. On the same data and the same window:

| Who's looking | "Inbound" says |
|---|---|
| Admin or supervisor | **127** |
| An agent | **5** |

Same page, same word, same styling. The server decides the scope and tells the
page which one it applied — the page displays what the server declared rather
than guessing from your role.

### Which window

The dropdown top-right offers two *kinds* of range, and each option is labelled:

- **Calendar** — "This month", "Last week". Resets on the 1st, on Monday. This
  is what a monthly target means.
- **Rolling** — "Last 30 days". A constant window that never collapses to
  nothing just because a month ticked over.

They give different answers on purpose. On 1 August, "This month" is a few hours
old and nearly empty; "Last 30 days" still covers July. **If a number looks
impossible, check which one you're on first.**

Everything compares against the **preceding equivalent window** — this week vs
last week, last month vs the month before. For a period still running, the
comparison is truncated to the same elapsed time, so a half-finished month is
never measured against a whole one.

---

## 1. The band across the top — AI performance

> **50.0%** success rate · ↘ 25.0 pts
> 1 of 2 conversations handled & engaged

### What "success rate" actually counts

It is **not** "how many messages the AI answered". It is stricter, and the
distinction matters:

> Of the conversations the AI was **allowed** to handle and where the customer
> **actually engaged**, how many went well?

A conversation counts as a success when the AI replied, the customer stayed with
it, and it was **not** escalated to a human and **did not** fail.

Three things are deliberately excluded from the denominator:

- **Conversations where the AI was switched off** — globally or for that chat.
  It can't fail at something it was never allowed to attempt.
- **One-line exchanges with no engagement** — a "hi" that goes nowhere isn't a
  win or a loss.
- **Escalations and failures** — those are subtracted, not ignored, which is why
  the rate falls when they rise.

The small line beneath — *"1 of 2 conversations handled & engaged"* — is the
fraction the percentage came from. **Always read it.** At small numbers the
percentage swings wildly: one conversation going the other way moves 50% to
100%. When the sample is too small to mean anything, the trend arrow is
suppressed rather than showing a dramatic and meaningless change.

### The bars on the right

The last 8 periods of AI reply volume. Shape only — it's there to show whether
activity is rising or falling, not to be read off precisely. The last two bars
are highlighted because they're the most recent.

---

## 2. The four tiles

| Tile | Means | Watch for |
|---|---|---|
| **Avg response** | How long the AI took to produce a reply, averaged | Rising = the model or a lookup is slowing |
| **Inbound** | Customer messages received | The base volume everything else is a share of |
| **Escalated** | Conversations handed to a human | Rising = the AI is out of its depth more often |
| **Override rate** | Share of AI-handled conversations a human took over | High = agents don't trust the AI's answers |

**Avg response** is the AI's own measured generation time, not the gap between
message timestamps. Those differ: an outbound row is created *before* the model
runs, so timestamp arithmetic measures the debounce window instead and reads
several times too high.

**Escalated vs Override** sound similar and aren't. *Escalated* is the system
deciding a human is needed. *Override* is a human deciding, unprompted, to take
over. Both rising together means the AI is struggling; only override rising
means it's answering, but not well enough for your team's liking.

---

## 3. Message volume — the line graph

One point per day. Each line is a channel, so you can see which channel drives
volume and when.

**What to look for:**

- **Weekly rhythm.** Most stores have one. A flat line where you expect peaks
  usually means ingestion stopped, not that customers went quiet.
- **A channel dropping to zero and staying there.** That's an integration
  problem, not a demand problem — check the connection before you check your
  marketing.
- **Spikes.** Usually a campaign or a post going out. Worth correlating with
  escalations: a spike the AI can't absorb shows up as escalations rising a day
  later.

**A caution:** the current day is always partial. The last point being low is
normal until the day closes. Compare like-for-like days, or use a closed period
("Yesterday", "Last week") when you want a clean read.

---

## 4. Top customer intents

What customers are actually asking about, classified per message.

Real example:

| Intent | Count | Share |
|---|---|---|
| greeting | 43 | 44.3% |
| unknown | 21 | 21.6% |
| stock_inquiry | 20 | 20.6% |
| product_inquiry | 18 | 18.6% |

### Why the percentages add up to more than 100%

**Because one message can carry several intents.** "Hi, do you have the black
wrap dress in M?" is a *greeting*, a *product_inquiry* and a *stock_inquiry* at
once, and is counted in all three. The percentages are each intent's share of
*messages*, not slices of a pie.

If you need them to sum to 100, they can't — that would mean forcing each
message into a single box and losing the fact that most real messages do several
things at once.

### What to act on

- **High `unknown`** is the useful signal. It means the classifier didn't
  recognise what was being asked. A rising `unknown` share is an early warning
  that customers are asking something new that the AI hasn't been set up for.
- **High `greeting`** is normal and mostly noise — people say hello first.

---

## 5. Channels

Where messages arrive. Real example: `instagram_dm` 74%, `whatsapp` 7.9%,
`instagram_comment` 7.1%, `facebook_dm` 3.9%.

Mostly a sanity check. The thing to notice is a channel you *expect* traffic on
sitting at or near zero — that's a connection to go and check, and this page is
often where you'll first spot it.

---

## 6. Most asked-about products

Which products customers ask about most, from the search terms the AI derived
from their messages.

**This will be empty or thin for now**, and that's expected rather than broken —
it only fills as conversations accumulate. It is *not* "best sellers"; it is
"most asked about", which is a different and sometimes more interesting thing:
a product with heavy interest and few sales is worth looking at.

---

## 7. AI failures by reason

Empty is the goal here, and empty is what it currently shows.

When it isn't empty, the reason is the point. It distinguishes the AI *failing*
from the AI being *switched off* — deliberately, because they used to be
conflated and a chat where the AI was never allowed to speak was being counted
as a failure.

---

## 8. Conversion funnel

> recommended → converted → attributed orders → attributed revenue

This answers the question the whole product exists to answer: **do the AI's
recommendations turn into sales?**

### It currently reads zero, and here is the honest reason

The chain is meant to be:

1. AI includes a tracked product link in its reply
2. Customer clicks it and lands on your store with tracking attached
3. Shopify records that on the order
4. A daily job matches it back to the conversation

**Step 1 never happened.** The link was placed in the AI's context and the code
searched its reply for one — but nothing ever *told* it to include a link. Every
mention of links in its instructions was a prohibition. So a link appeared only
by accident, and with no link there is nothing to attribute.

That is fixed. The AI is now instructed to paste the tracked link when it
recommends a product, with a fallback that records the product we put in front
of the customer if it drops the link anyway.

**What to expect:** this only affects *new* replies — history can't be
back-filled. Watch it start populating once real traffic flows. If it's still
zero after a few days of genuine volume, the next thing to check is whether
your checkout preserves tracking parameters through to the order.

---

## 9. The agent table

Supervisors and admins only. Agents never see it — not hidden in the interface,
**refused by the server**.

| Column | Means |
|---|---|
| **Active** | Open conversations assigned to them right now |
| **Assigned** | Everything ever assigned to them (lifetime, not the window) |
| **Resolved** | Conversations they closed *in the selected window* |
| **Human replies** | Messages they personally typed in the window |
| **AI on theirs** | AI replies sent on conversations assigned to them |

Sorted by **Active**, descending — busiest first.

### How to read it fairly

- **Assigned is lifetime; Resolved is windowed.** They are not a ratio. Dividing
  one by the other is meaningless.
- **High "AI on theirs" is not idleness.** It means the AI is carrying their
  queue, which is the system working. Read it alongside *Human replies*: high AI
  and low human means the AI is coping; high both means a heavy queue.
- **Active is a snapshot, not a workload measure.** An agent with 2 hard
  conversations may be busier than one with 10 simple ones.

This table shows *volume*, not *quality*. It cannot tell you who is good at the
job. Used as a leaderboard it will reward whoever claims the most easy chats.

---

## 10. Honest limitations

- **Products and conversions are thin or empty** until data accumulates. Fixed
  at the source; needs traffic.
- **The current day is always partial.** Use a closed period for clean reads.
- **Intent percentages exceed 100% by design** — messages carry several intents.
- **The agent table measures activity, not quality.**
- **Small samples make percentages jump.** The success rate always shows the
  fraction beneath it for exactly this reason — read it.

---

## 11. The one-paragraph version

The band at the top tells you whether the AI is doing its job on conversations
it was actually allowed to handle — read the fraction under it, not just the
percentage. The four tiles cover speed, volume, and how often humans step in.
The line graph shows where messages come from and when, and is the quickest
place to spot a channel that has silently stopped. Intents tell you what people
are asking and, through the `unknown` share, what the AI isn't ready for.
The funnel is meant to prove the AI drives sales and currently can't, for a
reason that has been found and fixed. And the agent table shows how work is
distributed — not how well it's being done.
