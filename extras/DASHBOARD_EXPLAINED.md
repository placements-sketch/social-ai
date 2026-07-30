# The Dashboard, explained in plain English

For answering "how does this work?" without notes. Every number here is
defined by what it counts, not by what it's called.

---

## The one idea behind the whole page

**We only judge the AI on conversations it was actually allowed to answer.**

Think of it like grading a goalkeeper. You only count the shots they were on
the pitch for. If the manager subbed them off, goals conceded afterwards
aren't theirs.

The AI has four switches that can keep it off the pitch:

1. **The master switch** — an admin turned the AI off for the whole platform
2. **The channel switch** — WhatsApp is switched off, say
3. **The conversation switch** — an agent took this one chat over
4. **The comment rule** — on public comments, the AI only answers *questions*.
   It stays out of "love this 😍" because replying to praise in public is odd

If any switch was off when a customer's message arrived, that conversation
doesn't count for or against the AI.

**The important part:** we record which switches were open *at the moment the
message arrived*, and we never change it afterwards. So if you turn the AI off
today, last month's score stays exactly as it was. Before this, switching the
AI off rewrote history and made the AI's own past look like failure.

---

## The top bar

| Thing | What it is |
| --- | --- |
| **Status pill** ("All systems operational") | Green when nothing is broken, amber for a few errors, red for 5+ errors or a failed sync job in the last hour. **Only admins and supervisors see it** — an agent can't fix a database problem, and the detail panel behind it shows raw error text including server addresses |
| **The clock** | Shows time in **the business timezone** (Settings → Business info), not your laptop's. Otherwise someone in London would see London time next to figures counted in Nairobi days |
| **Sun/moon** | Light and dark mode |
| **Bell** | Your notifications. Refreshes every 20 seconds, and **immediately the moment you come back to the tab** |
| **Avatar** | Your profile and log out |

There used to be a refresh button. It just reloaded the page, which threw away
everything. The page refreshes itself now, so it's gone.

---

## The sidebar

- **Menu items are filtered by who you are.** An agent literally cannot see
  Users or Settings — the links aren't rendered, and the pages refuse them
  server-side too.
- **The number on Inbox means different things by role**, on purpose:
  - **Agent:** conversations waiting on a *person*. The AI is handling the
    rest, so they don't need to see those.
  - **Admin/supervisor:** unread conversations.
  - Both exclude resolved ones. A closed chat isn't outstanding work.
- **Collapse button** sits at the bottom, in its own row, in the same place
  whether the sidebar is open or shut.

---

## The date filters (Today / This week / This month / Custom)

These are **real calendar periods in your business timezone**, not rolling
windows.

- **Today** = since midnight in Nairobi. Not "the last 24 hours."
- **This week** = since Monday (or Sunday — it's a setting).
- **This month** = since the 1st. Not "the last 30 days."

**The comparison is the clever bit.** On the 3rd of the month, "this month" is
only 3 days old. Comparing that against a *whole* previous month would make
every number look like it collapsed. So we compare against **the same slice**:
1st–3rd of this month vs 1st–3rd of last month.

**Custom** lets you pick any range, including a single day — useful for "what
happened on the 9th?"

---

## The six cards along the top

| Card | What it counts |
| --- | --- |
| **Inbound** | Messages customers sent you |
| **AI Replies** | Messages the AI sent |
| **Human Replies** | Messages a person sent |
| **Failed Replies** | Times the AI broke (see below) |
| **Escalated** | Times the AI handed a conversation to a person |
| **Success Rate** | See "AI Performance" below |

**The little arrow** is the change against the same slice of the previous
period. **The colour means "is this good news?", not "did it go up?"** — more
failures is red even though the number went up. Human Replies is grey, because
more human replies isn't inherently good or bad; it depends why.

**If there are fewer than 10 conversations, the arrow disappears** and it says
"too few to compare". With 7 conversations, one of them moves the rate 14
points — a trend line there is noise wearing a percentage sign.

---

## Channel Performance

**The chart.** "All channels" draws one line per channel so you can compare
them. Pick a single channel and it splits into three lines: what came in, what
the AI answered, what a human answered. It used to draw all twelve at once,
which nobody could read.

**The four tiles** show inbound volume, the change vs last period, and a
warning chip if something's wrong. Click one to open the details.

**The details panel** answers one question: *which channel needs attention?*
Each channel gets:

- How many messages came in, and whether that's up or down
- Who's answering — AI vs human
- **What happened to every conversation the AI was on duty for**, split three
  ways that always add up: answered by AI / picked up by a human / never
  answered
- Speed, escalations, and a verdict chip

The **"never answered"** number is the one to watch. Those are customers where
the AI was supposed to reply, didn't, and no human stepped in either. Dropped
customers.

Underneath it says *why*, in plain English — "channel disabled", "comment
wasn't a question", "send to platform failed", and so on — and then **lists
the actual conversations**, each one clicking straight through to that chat in
the Inbox. So it's a worklist, not just a statistic. The list caps at 10 per
channel with "+ N more"; the count above it stays exact.

The same number appears on the AI Performance card with a "see which →" link
that opens this panel.

---

## Live Activity

A running feed of things that happened **to customers**. Newest 12, refreshing
every 20 seconds.

It only shows events a human might act on: a customer wrote, the AI replied,
the AI *didn't* reply (and why), a conversation was escalated or assigned, and
faults. It deliberately hides internal engineering noise — before, 84% of the
feed was raw log output nobody could act on.

**Every row is clickable** and opens that exact conversation.

---

## System Alerts / "Needs Attention"

**What admins and supervisors see:** things that are broken. Faults only,
**grouped** so 300 copies of the same error are one line with a "300×" badge,
sorted worst-first, with when it last happened.

Before, this panel showed the last few log lines of *any* kind — so it
displayed things like "Access token obtained" while hundreds of real errors
sat unseen behind them.

**What agents see instead:** their own work. "3 conversations awaiting your
reply", "2 conversations waiting to be picked up". They used to get a
permanently empty box that said "All systems normal" — which was a lie; they
simply weren't allowed to see it.

---

## AI Performance

### Success rate — the headline

*Of the conversations the AI was on duty for, how many actually worked?*

**It counts as a win when the AI replied AND the customer stayed** — they sent
a second message, or they bought something. One message with a reply proves
nothing; they might have left annoyed.

Both halves matter. Counting only "the customer sent two messages" would score
someone who was *ignored and repeated themselves* as a success — because from
the inbound side alone, "engaged in conversation" and "asked twice because
nobody answered" look identical.

**Two things cancel a win:**

- **Punted** — the AI decided it couldn't cope and handed off to a human. A
  deliberate decision. Fine behaviour, but not a win.
- **Failed** — something broke. Not a decision, an accident.

So "3 of 7 = 42.9%" means: the AI was on duty for 7 conversations, and 3 of
them turned into a real exchange it handled itself.

### Punted vs Failed — people mix these up

- **Punted** = the AI *chose* to stop. It read "I want a refund", sent "let me
  get someone from our team", switched itself off and assigned an agent. The
  system worked exactly as designed.
- **Failed** = something *broke*. Three ways: the AI errored and a generic
  canned reply went out; a reply was written but the platform refused to send
  it; or the whole process crashed and nothing went out.

**A punt is a decision. A failure is an accident.** Both mean the customer
didn't get what they came for, which is why neither counts as a win — but they
tell you opposite things. Lots of punts means the AI is too cautious, or your
customers are unhappy. Lots of failures means something is broken.

### The other numbers

- **Response rate** — of the same conversations, how many got *any* AI reply.
  Counted **per conversation, not per message**: if a customer sends three
  messages and the AI answers all three in one reply, that's 100%, not 33%.
  It can be high while success rate is low — "did it speak?" vs "did it work?"
- **Avg response** — how fast the AI replies
- **Override rate** — how often a human took a conversation over by hand
  (without the AI escalating). Same denominator as success rate, so the two are
  comparable
- **Escalated / Failed** — the counts behind the two subtractions above
- **"N never answered"** — nobody replied at all. Turns red when it's a quarter
  or more of the period

---

## Conversion Rate

*Did talking to the AI make people buy?*

**How the tracking works.** When the AI recommends a product, the link it
sends carries a hidden tag identifying that exact message. If the customer
clicks it and buys, Shopify records the tag on the order, and a job that runs
daily matches the order back to the message that earned it.

- **Recommended** — conversations where the AI actually sent a product link
- **Converted** — how many of those produced an order
- **Conversion** — one divided by the other
- **Revenue driven** — the value of those orders, **excluding tax**, in one
  currency

**Two things worth knowing:**

- Tax is taken from Shopify's own figure for each order, not estimated. An
  untaxed order isn't wrongly reduced.
- If any order is in a different currency it's **left out and declared**
  rather than added to a total labelled KES. There's no exchange rate
  available, and guessing one would be worse than saying so.

**It runs itself.** A GitHub Action fires it daily at 04:00 EAT, the same way
products, orders and customers sync. Nobody has to run anything by hand.

**If it says zero,** either nobody bought through a tracked product link, or
the job hasn't been running. Nothing else writes that data, so a stalled job
means zero conversions no matter how many people actually bought. To check,
open GitHub → Actions → Daily Sync and look for recent runs, or ask the
database:

```sql
SELECT kind, status, max(started_at) AS last_run
FROM sync_jobs WHERE kind = 'attribute' GROUP BY 1, 2;
```

**One gotcha worth knowing:** GitHub disables scheduled workflows
automatically after 60 days with no commits to the repository. If the repo
goes quiet for two months, every scheduled job stops silently — attribution,
syncs, all of them. GitHub emails the repo owner when it happens.

---

## Export

The CSV and PDF contain **everything on the page** — all the headline numbers,
conversion, channel breakdown, and per-channel performance. The header shows
the exact date range, e.g. "This month (1 Jul 2026 – 29 Jul 2026)", because
"this month" means nothing in a file opened six months later.

---

## Rules that apply everywhere

**1. Everyone sees their own scope.** An agent's numbers cover their own
conversations. Admins and supervisors see everything. There's a line above the
cards saying so when you're an agent.

**2. Everything is in your business timezone.** Set once in Settings.

**3. Small numbers don't get trend lines.** Below 10 conversations, comparisons
are hidden rather than shown misleadingly.

**4. Events are counted when they happened**, not by the current state of
things. An escalation in June counts in June — even if someone later switched
the AI back on, which used to erase it entirely.

---

## Likely questions

**"Why is the success rate so low?"**
It only counts conversations the AI handled *end to end* where the customer
came back. Escalating to a human, or breaking, both cancel it. It's a strict
measure on purpose — it's about outcomes, not activity.

**"Why is response rate 96% but success rate 19%?"**
Response rate is "did it reply". Success rate is "did the conversation
actually work". The AI almost always replies; most conversations don't turn
into a real exchange.

**"Why does it say 0 conversions?"**
Either nobody bought via a tracked product link, or the daily attribution job
hasn't run. Check the job first.

**"Why is the AI not replying?"**
Check the master switch (Settings → AI), the channel switch, and whether
someone took the conversation over. Live Activity states the reason for every
non-reply in plain English.

**"Are these numbers real?"**
Yes — they come from the database, not estimates. The known soft spots are
labelled: escalation dates from before this system was built are approximate,
and history for the "was the AI allowed to reply" flag is reconstructed from
evidence where possible.
