# The Messages page, explained

Written so you can answer "how did you do this?" about any part of the inbox
without preparation. Plain English first, the mechanism second.

---

## 1. What this page is for

Every customer message from every channel — Instagram DMs and comments,
Facebook DMs and comments, TikTok DMs and comments, WhatsApp — lands in one
list. An agent picks a conversation, reads it, and either lets the AI keep
handling it or takes over and replies by hand.

Three things have to be true for that to work:

1. What the page says has to match what the database holds.
2. Every element has to help someone do something.
3. Nothing may fail quietly.

Most of what follows is one of those three.

---

## 2. The filter chips (Unclaimed / With agent / AI handling / Resolved)

### What they mean

| Chip | Means |
|---|---|
| **Unclaimed** | Not resolved, nobody assigned, AI switched off. **Nobody is dealing with this.** |
| **With agent** | Not resolved, someone assigned, AI off. A person owns it. |
| **AI handling** | Not resolved, AI on. The robot is answering. |
| **Resolved** | Closed. |

They add up to your whole inbox — every conversation is in exactly one, none in
two. That is worth saying out loud, because it means the four numbers are a
complete picture, not four overlapping samples.

### The bug that was here

The chips showed one number and the list showed a different set of rows.
"Resolved 27" over a list of 11. "Unclaimed 2" over the words *No unclaimed
conversations*.

**Why.** The count was calculated on the server across every conversation. The
filtering was done in the browser, across the 20 rows it had downloaded. Two
different questions being asked in two different places. If both unclaimed
conversations happened to be older than the newest 20, the list found none.

There was a second symptom of the same cause. A "show unclaimed" link elsewhere
in the app worked correctly — because it asked the server. The chip beside it
didn't — because it filtered the browser's copy.

### The fix

One function, `_bucket_filter` in `app/messages.py`, expresses the four
buckets as database conditions. **Both** the counting endpoint and the listing
endpoint call it. The number on a chip and the rows behind it are now literally
the same query. The JavaScript copy of the rules was deleted — keeping a second
definition is what let them drift apart in the first place.

> **If asked "how do you know it's right now?"** — the four buckets sum to
> exactly the number of conversations in the database. Any overlap or gap would
> break that.

---

## 3. Search

### What it does

Type anything and it looks in the customer's name, their handle, and — this is
the new part — **everything ever said in the conversation.**

### What it used to do

It searched only the *most recent* line of each conversation. Searching
"refund" found a conversation only if "refund" happened to be the last thing
said in it. Measured on the development database:

| Search | Found before | Finds now |
|---|---|---|
| refund | 1 | **8** |
| dress | 4 | **14** |
| delivery | 3 | **6** |

Seven conversations mentioning a refund were invisible.

### Showing why a row matched

Finding the conversation is only half the job. Search "refund", get a row whose
visible line reads *"ok thanks!"*, and you still have to open it to find out
why it matched. So each result now carries the line it actually matched on,
says who said it, and highlights the word:

> **They said:** Hi, is the black wrap **dress** available in size M?

It only appears when the visible line doesn't already contain the word, so a
row never says the same thing twice.

### Two things worth knowing about the mechanism

- It uses an `EXISTS` check, not a join. A join would return one row per
  matching *message*, so a conversation saying "dress" five times would appear
  in the results five times.
- The box waits 300ms after you stop typing before asking the server. Typing
  "dress" used to fire five separate searches.

### The database change (Step 13)

Searching inside text with wildcards on both sides can't use an ordinary
index, so the database would read every message row on every search. Step 13
in `PRODUCTION_CHANGES.md` adds a **trigram index**, which it can use. Verified
before writing it down: the query plan changes from a full scan to an index
scan.

---

## 4. Reading a photo the customer sends

This is the part most worth understanding, because it was quietly producing
wrong answers.

### The situation

A customer sends a photo of a dress, then writes **"Is this still available?"**

### What used to happen

The AI works out what to search the catalogue for by stripping common words
out of the customer's message and keeping the rest. For that sentence, what
survived was the word **"still"**. So it searched the catalogue for "still" and
recommended whatever came back.

| Customer wrote | Catalogue was searched for |
|---|---|
| "Is this still available?" | **still** |
| "Can I get this?" | **Can I get this?** |
| "Do you have this in red?" | **red** |

All three return essentially random products.

### Why the photo didn't save it

The system *does* look at photos — it describes what's in the image and stores
that description. And it *does* have a fallback that looks back through recent
messages. But that fallback only ran for greetings and unrecognised messages.
"Is this still available?" is recognised — it's a stock question — so it took
the other path and never looked back. **The description of the photo was sitting
one row back in the database the whole time, unread.**

### The fix

The system now recognises a **referential** message: one that points at
something without naming it ("this", "that", "it") and contains no product
word. For those, it uses what the customer was last pointing at.

And if they add detail, that detail is kept:

| Customer wrote | Now searches for |
|---|---|
| "Is this still available?" | Floral Wrap Dress |
| "Do you have this in red?" | Floral Wrap Dress **red** |

When nothing is remembered and the message names nothing, it no longer searches
on rubbish — it records `services.keyword_unresolved` in the logs and lets the
AI ask what they mean. **Worth checking that log after a few days**: it tells you
how often customers point at something the system can't work out.

> **If asked "how did you test it?"** — against a real conversation in the
> database that had "Floral Wrap Dress" stored from an earlier photo.

### Forwarded posts

Separately: when a customer forwards one of our own Instagram posts, we now
read the post's caption and search on that. Our caption usually names the
garment outright ("Vivo Lani Maxi Dress in Satin"), which beats anything the
image-reader could guess. It also now asks the image-reader to copy any text
visible *in* the picture first — a screenshot of a product page literally has
the product name written on it.

---

## 5. The conversation header

Three controls, one per question an agent has:

| Control | Answers |
|---|---|
| ● AI replying / AI paused / AI off · global | Is the robot answering this? |
| **Resolve** / Re-open | Is this finished? |
| Assign: *name* | Who owns it? |

**What changed.** There used to be four controls, and two of them said the same
thing — a button reading "⚠ AI Off" next to a separate badge reading "AI
Disabled". The state is now shown once, by the control that changes it.

---

## 6. The context panel

Three cards. Nothing in it repeats what's already on screen — not the handle,
not the channel, not the last message you can read in the thread beside it.

1. **What the AI made of this** — the detected intent, what it searched the
   catalogue for, and how long its last reply took (green under 3 seconds,
   amber under 10, red beyond).
2. **This conversation** — messages in and out, when it started, the channel,
   the last thing the customer said.
3. **Who's handling it** — the current handler, the customer, the assignee.

If the conversation was escalated, an amber block sits above all three and
explains **why** in words rather than a code word: *"The customer used a word we
always escalate on."*

**Design rule:** an empty field never shows a dash. It says why it's empty —
*"Nothing classified on the last customer message"*. A column of dashes makes a
working panel look broken.

The "searched the catalogue for" line is the most useful thing here. It's how
you diagnose a bad recommendation: if it doesn't match what the customer asked
for, that's your answer.

---

## 7. Things that used to fail silently

This is the theme of the whole audit. Four examples from this page:

### A failed send said nothing useful

If a reply failed to send, the error was written into the same place used for
*"the conversation failed to load"* — whose Retry button reloads the
conversation. So the one button offered after a failed send did nothing about
the message that hadn't been sent.

Now: a red panel above the box saying **Message not sent**, the reason, the text
that didn't go, and a **Retry** that sends *that* message. The typed text stays
in the box either way.

### Turning the AI off could fail without telling anyone

The switch flipped instantly and quietly flipped back if the server rejected
it. The agent saw the AI go quiet, started typing a manual reply — and the AI
was still live, answering underneath them. Now a failure is announced:
*"Could not pause the AI — it is STILL replying to this customer."*

The same fix went to Resolve, which previously only wrote to a developer
console no agent will ever open.

### Expired photos rendered as nothing

Instagram and Facebook serve attachments from links that expire. An old photo
became a broken-image icon — and because the message text in those cases is a
hidden placeholder, the whole bubble came out **completely empty**. Now it says
*"Image unavailable — the link from the platform has expired"* with a way to
open it directly.

### Links in messages were invisible

Links inside the AI's replies were painted white. In dark mode that bubble
turns lime green, so the text flipped to dark — but the rule that does the
flipping didn't apply to links, because they use a slightly different style
name. White text on lime. Links are now coloured per bubble.

---

## 8. Load and performance

**The open conversation used to re-check for new messages every 3 seconds,
forever** — 20 requests a minute, per open chat, per agent, whether or not
anyone was looking at the screen. The server runs 8 requests at a time, so ten
agents with a chat open was 200 requests a minute of pure checking before
anybody did any work.

Now: every 3 seconds while the conversation is live, dropping to every 20
seconds once nothing has changed for two minutes, and **stopping entirely while
the browser tab is hidden**. Coming back to the tab refreshes immediately.

---

## 9. Two correctness fixes behind the scenes

### Unread counts were shared when they should be personal

The Channels page counted unread messages using a single shared counter that
gets zeroed whenever **anyone** opens a conversation. So an admin glancing at a
chat marked it read for every agent.

The size of the error, measured: the shared counter said **4** unread. Counting
each person's own reading position — which is what the inbox itself uses —
gives **19**, for every user. Roughly a fivefold under-count. The Channels page
now uses the same per-person source as the inbox.

### The post-context endpoint wasn't scoped

The endpoint that fetches an Instagram post's caption accepted any post ID from
any logged-in user. The data it returns is public, so this was never a serious
leak — but it made the endpoint an open door onto our Instagram API allowance,
and an agent could pull posts from conversations outside their own queue. It
now requires the post to appear in a conversation the caller is allowed to open.

---

## 10. Honest limitations

Things I could not fully verify, so you aren't caught out:

- **The development database has no image attachments and no post IDs** (0 rows
  each — it's seeded data). The attachment fallback and the post-context
  scoping are correct by construction and the code paths are exercised, but
  they have not been run against real Instagram data.
- **The trigram index may not be used immediately.** On a small table the
  database will still prefer reading everything, and that's the right choice.
  The index earns its keep as messages accumulate. Not a failed step.
- **`services.keyword_unresolved` has never fired** — it's new. Its absence in
  the logs today means nothing yet.

---

## 11. The one-paragraph version

The inbox now agrees with itself: the number on a filter and the rows behind it
come from the same database query, and unread counts mean the same thing on
every page. Search reaches into what was actually said instead of only the last
line, and shows you why each result matched. When a customer sends a photo and
follows it with "is this still available?", the system now understands what
"this" refers to instead of searching the catalogue for the word "still". And
the things that used to fail in silence — a send that didn't go, an AI switch
that didn't take, a photo whose link expired — now say so.
