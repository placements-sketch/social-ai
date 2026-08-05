# The docs assistant — how it works

The **Ask the docs** button, bottom-right of every page. Staff ask how the
system works; it answers from the written explainers in `extras/`.

---

## The one-sentence version

It answers *how does this work?* from our own documentation, cites which
document it used, and says "the docs don't cover that" rather than guessing.

---

## Two assistants, deliberately not one

There are two AI assistants in this platform and they are easy to confuse:

| | **Docs assistant** | **Customer Profiling assistant** |
|---|---|---|
| Answers | How the system works | Questions about customers and orders |
| Source | The `*_EXPLAINED.md` files | Live database, via vetted query tools |
| Who can use it | **Everyone**, including agents | Admin and supervisor only |
| Sees customer data | Never | Yes — that is the point |

The access difference is the reason they are separate. The analytics assistant
is restricted *because its answers contain customer records*. A docs assistant
locked behind the same restriction would be useless to the people with the most
questions and the least context — agents.

---

## Why the whole corpus is sent every time

Most "chat with your docs" systems chunk the documents, embed them, and
retrieve the top few chunks per question. **This one does not**, and that is a
deliberate choice worth being able to defend.

The explainers total roughly **124 KB — about 31,000 tokens**. That fits
comfortably in a single request. Retrieval exists to solve a size problem we do
not have, and it introduces one we would rather avoid: when the top-k misses
the paragraph that actually answers the question, the assistant confidently
says "the docs don't cover that" about something the docs cover perfectly well.
That failure is invisible — it looks like a gap in the documentation rather
than a bug in the retrieval — which makes it exactly the kind of quiet wrongness
this codebase keeps trying to design out.

Sending everything means **perfect recall by construction**.

**The cost objection answers itself: prompt caching.** The corpus is byte-identical
on every request, so it is written to cache once and read back at a fraction of
the price. Measured on the real endpoint:

```
call 1: input=504  cache_read=43,256
call 2: input=504  cache_read=43,256
```

Only ~500 tokens are fresh per question. That works out to roughly **2 US cents
a question**, and the endpoint is rate-limited to 15 per minute per user.

This stops being the right design if the corpus passes ~150k tokens — about ten
times the documentation we have today.

---

## What stops it making things up

The system prompt is explicit that the documents are the only source, and:

- **Gaps are stated, not filled.** "The docs don't cover that" followed by what
  they *do* cover nearby. The rule spells out why: a confident wrong answer
  about this system is worse than no answer, because the person will repeat it
  to someone else.
- **Every answer names its document**, so you can go and read the original
  before a meeting. That is the whole reason these explainers exist.
- **It has no data access at all** — no customers, orders, conversations or
  metrics. Asked for a business number, it says so and points at the other
  assistant.

Verified behaviour:

> **Q: What is our refund policy for late deliveries?**
> *The docs don't cover that — I don't have access to Shop Zetu's business
> policies like refund terms. What the docs do cover, related to this:
> ANALYTICS_EXPLAINED.md and DASHBOARD_EXPLAINED.md explain how delivery
> questions get classified as "delivery_inquiry" intent…*

It also flags partial knowledge rather than papering over it — asked what turns
off the global AI switch, it answered from `DASHBOARD_EXPLAINED.md` and then
added that the docs don't say where that toggle lives in the UI.

---

## Keeping it current

The corpus is **every `*_EXPLAINED.md` in `extras/`, plus `ARCHITECTURE.md`**,
re-read from disk at most once every 10 minutes.

That means **writing a new explainer is all it takes** — no re-indexing, no
embedding job, no deploy step beyond shipping the file. This document became
answerable the moment it was saved.

It is an allow-list by filename suffix rather than "everything in `extras/`",
because that folder also holds exported analytics PDFs, a PowerPoint, and test
scripts — one of which contains credentials.

---

## Questions you will get

**"Which model?"** Claude Sonnet 5. The task is explaining from provided text,
where the quality of the explanation is the entire product.

**"What if the API key is missing or the docs aren't deployed?"** Two different
errors, on purpose. *"AI is not configured on this server"* versus
*"Documentation is not available on this server"* — the second is a packaging
problem someone can fix, and collapsing it into a generic AI failure would send
them looking in the wrong place.

**"Can agents see things they shouldn't?"** No. The corpus is internal
documentation about our own system. It contains no customer data, no
credentials, and no live figures.

**"Does it remember the conversation?"** Yes, the last 8 turns, so follow-ups
like "and what turns that off?" work. It does not persist between sessions —
closing the panel and reopening starts fresh.
