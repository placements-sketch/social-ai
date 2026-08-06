# How the assistant handles public comments

*Instagram comments only. Facebook comments are switched off (Step 18) — we
cannot reply on that channel yet, so the AI never touches them.*

---

## The question it has to answer first

A DM is private and one-to-one. Someone sent it, so they want something, and
replying is always appropriate.

A comment is public. It sits under a post where everyone can see it, and most
comments are not requests at all — they are compliments, emoji, someone tagging
a friend. Replying to those with a product blurb makes the account look
automated in the one place customers actually judge it.

So every comment has to pass a filter that DMs do not: **is anybody waiting on
us here?**

---

## How that used to be decided, and why it was replaced

`is_question()` — a list of question words (`what`, `where`, `how`, `is`, `do`
…) plus stock phrases (`how much`, `in stock`, `do you have` …). If the comment
ended in a `?` or contained one of those, it got a reply.

It is a reasonable first approximation and it was wrong in both directions:

| Comment | Old verdict | Actually |
|---|---|---|
| `need this in a 38` | ignored | a customer, mid-purchase |
| `obsessed, take my money` | ignored | a customer, wallet out |
| `is she gorgeous or what` | replied to | praise |
| `how stunning 😍` | replied to | praise |

Nothing about the vocabulary of a sentence tells you whether it is a request.
Every miss was fixed the same way — add another word to the list — and there is
no end to that list.

## How it is decided now

The classifier reads the comment and returns its intents, and one of them is
`praise`:

> **praise:** compliments, excitement, emoji-only reactions, tagging a friend —
> anything appreciative that asks for NOTHING.

The rule is then a single line: **praise, and nothing else, means nobody is
waiting.**

| The AI reads it as | What happens |
|---|---|
| `["praise"]` | the comment is **liked**, no reply |
| `["praise", "product_inquiry"]` | answered — there is a real question inside the compliment |
| `["product_inquiry"]` | answered |
| `["unknown"]` | answered |

`unknown` deliberately counts as answerable. It means the classifier could not
tell what the message was, which is a reason to look closer — not a reason to
assume there is nothing there.

### If the classifier is down

It falls straight back to `is_question()`. This matters more than it sounds:
the keyword fallback has no concept of praise, so everything it cannot place
comes back as `unknown` — which the table above answers. Without the fallback,
one classifier outage turns the bot into something that replies to every
`🔥🔥🔥` on a public post. Under-replying is the cheaper mistake here.

---

## Liking, instead of ignoring

Praise gets a like. It costs nothing, it acknowledges someone who said
something nice, and it is what a person running the account would do.

Whether Meta actually permits it depends on how the Instagram account is
connected, and the published accounts of the 2026 like/unlike API disagree with
each other on that point — some say it requires Facebook Business Login, which
is not what we use. Rather than take a side, `like_instagram_comment()` attempts
it and logs exactly what Meta answers, so production settles the question.

**A refused like is not a failure.** It returns us to the behaviour we already
had — the comment goes unanswered, which is what it was going to be either way.
It is logged at `warning`, not `error`, for that reason: it describes our Meta
setup, not a fault in the pipeline, and it should not paint a red line through
Live Activity under every compliment the store receives.

Watch for `integrations.meta.comment_like` in Live Activity to see which way it
went.

---

## What happens to the comments that do get answered

They go to a **DM**, not a public reply — see `trigger_dm_flow` in
[AUTOMATION_ENGINE_EXPLAINED.md](AUTOMATION_ENGINE_EXPLAINED.md). The full
answer, with product, price, stock and link, is sent privately; a short teaser
goes under the post.

The rule that routes them no longer carries a keyword list. It triggers on the
channel — *any Instagram comment* — because praise has already been filtered
out one step earlier. Anything still standing is something a person wants an
answer to.

---

## The scorecard

`ai_eligible` is stamped on a message when it is saved, which happens before
the classifier runs — at that moment all the code can do is guess from the
text. Once the AI has read the comment and we have chosen to like rather than
reply, `_mark_ineligible_for_ai()` corrects the stamp.

Without that correction every "love this 😍" would count as a conversation the
AI failed to answer, and **the reported failure rate would rise with the
store's popularity.** A post going viral would look like an outage.

---

## Answering "how did you achieve this?"

> **"How does it know not to reply to compliments?"**
> The classifier returns a `praise` intent. If praise is the *only* thing it
> finds, nobody is waiting on us, so we like the comment instead of replying.
> If there is a question inside the compliment, it is answered normally.

> **"What if it gets it wrong?"**
> Two directions. Wrongly treating a request as praise means a customer is
> liked instead of answered — visible in Live Activity as a `praise_no_question`
> no-reply, with the comment text right there. Wrongly treating praise as a
> request means one unnecessary DM. We tuned toward the second.

> **"Why not just use a list of keywords?"**
> We did. It ignored "need this in a 38" and replied to "how stunning 😍",
> because neither the presence nor absence of a question word tells you whether
> someone wants something.

> **"Does this cost more?"**
> Yes — every public comment now goes to Haiku, including ones we only like.
> The keyword check was free. At our comment volume the difference is
> negligible, and it buys a decision made on meaning instead of vocabulary.
