# The Products page, explained

Written so you can answer "how does this work?" and "why does it say that?"
without preparation. Plain English first, the mechanism second.

---

## 1. What this page is for

The assistant recommends products in chat. To do that it needs a copy of the
Shopify catalogue it can search in milliseconds — waiting on Shopify's API
mid-conversation would make every reply slow.

That copy is what this page shows. So the page answers three questions:

1. **What can the assistant sell?** — how big the catalogue is.
2. **What can't it sell right now?** — what's out of stock.
3. **Can I trust what it's saying?** — how fresh the copy is.

Everything on the page serves one of those. If you want to *edit* a product,
that's Shopify's job — this is a read-only mirror.

---

## 2. The three cards at the top

| Card | Means |
|---|---|
| **In the catalogue** | Products the assistant can recommend right now |
| **Cannot be sold** | Out of stock, with the share of the catalogue |
| **Catalogue freshness** | When we last copied from Shopify |

### What changed and why

There used to be four cards: Total / In Stock / Out of Stock / Untracked. On
this catalogue those read **7,713 / 7,701 / 12 / 0**.

Two of them couldn't tell you anything:

- **In Stock** was 99.8% of the total, so it just restated the first card.
- **Untracked** has been **zero since the page was built** — a card permanently
  displaying nothing.

The replacement leads with what changes and what you can act on. **Freshness**
is now a headline rather than small print, because it's the one with real
consequences: a stale catalogue means the assistant quotes wrong prices and
wrong stock to real customers, in public. The card says that in words rather
than showing a timestamp and leaving you to work it out.

---

## 3. Search — and why it matters more than it looks

Type anything and it searches the product **name, tags, variants and
description**.

### The bug this fixes

Search used to look at the **product name only**. The assistant searches all
four fields. So the two disagreed, badly:

| Search | This page found | The assistant searches |
|---|---|---|
| red | 916 | **1,568** |
| cotton | 184 | **438** |
| wrap | 210 | **308** |
| maxi | 456 | **565** |

That gap mattered for a specific reason. When the assistant recommends
something odd and you come here to ask *"what would it have matched for
'cotton'?"* — **you were looking at a different catalogue than it was.** You
could not reproduce what it saw, so you could not diagnose the recommendation.

Now the two are identical, and the results line says so explicitly.

The box also waits 300ms after you stop typing. It used to fire on every
keystroke — and it re-ran the three catalogue-wide counts with it, four COUNT
queries over 7,713 rows per character, even though none of those counts depend
on the search box.

---

## 4. Sync

**Check for changes** compares our copy against Shopify and shows what would be
added, updated and removed. **Apply Sync** does it.

### Who can do it

Supervisors and admins only.

It used to be **anyone with a login**. The sidebar hid the page from agents, but
that's the interface only — the endpoint was reachable directly by anyone
signed in. A sync walks the entire catalogue, deletes cached rows for products
that have disappeared from Shopify, and consumes Shopify API rate limit. Not
something an agent should be able to set off.

> This was the same shape of bug as the one found on the Messages page, where
> `delete_message` and `edit_message` skipped the access check every neighbouring
> route performed. Worth checking for on every page: **is the button hidden, or
> is the action actually prevented?**

---

## 5. Does the assistant recommend things that are out of stock?

**No** — and I checked rather than assumed.

The catalogue search sorts out-of-stock products last and then ranks by stock
level, so a well-stocked item beats a nearly-gone one. Out-of-stock products
aren't removed from the results entirely, because a customer asking about a
specific sold-out item should still be told it exists — but they're never the
first thing offered.

---

## 6. The bigger fix that came out of this page

While auditing, one question had no answer: **which recommendations led to
sales?** The page couldn't show it because the data didn't exist — zero messages
had a product URL recorded, and the attribution table was empty.

### Why the loop was open

The chain is meant to be:

1. Assistant includes a tracked product link in its reply
2. Customer clicks it and lands on Shopify with tracking parameters attached
3. Shopify records those on the order
4. A daily job matches them back to the conversation

**Step 1 never happened.** The link was placed in the assistant's context, and
the code searched its finished reply for the link — but nothing ever *told* it
to include one. Every mention of links in its instructions was a prohibition:
*"MUST NOT include a product link"*, *"do NOT link any other product"*. A link
appeared in a reply only by chance.

There was also a fallback designed for exactly this — a note in the code called
it a *"post-hoc attribution fallback"* — which was **set and never read by
anything**.

### What happens now

The assistant is told plainly: when recommending one of these products, paste
its link exactly as written, because the tracking on it is how we know the sale
came from you. If it recommends something but drops the link anyway, the
fallback records the product we put in front of the customer instead.

**This only affects new replies.** Historical messages have no link and can't be
back-filled.

> **After deploy, watch for:** `messages.product_url` starting to fill. Once
> orders land, the daily attribution job has something to match and the
> conversions table populates. If it's still empty after a day of real traffic,
> the next place to look is whether Shopify preserves the tracking parameters
> through your checkout.

---

## 7. Honest limitations

- **The page cannot yet show which products actually sell through chat.** The
  fix above starts collecting that data; the page has nothing to display until
  it accumulates.
- **83 products have no image**, so those rows show a placeholder. That's a
  Shopify data gap, not a bug here.
- **Stock is a snapshot.** It's as accurate as the last sync — hence the
  freshness card. Live stock changes reach us through Shopify webhooks between
  syncs, but a missed webhook is only corrected at the next full sync.
- **This is a mirror, not a source.** Everything shown comes from Shopify. If a
  number looks wrong, Shopify is the place to check it, and a sync is the way to
  correct it here.

---

## 8. The one-paragraph version

This page shows the copy of your Shopify catalogue that the assistant searches
when it recommends products. It now tells you the three things that matter —
how much it can sell, what's out of stock, and whether the copy is fresh enough
to trust — instead of four numbers, two of which never changed. Search now
covers exactly the fields the assistant searches, so when a recommendation looks
wrong you can reproduce what it saw. Syncing is restricted to supervisors and
admins, which it wasn't. And the assistant is now actually told to include its
tracked product links, which is what will finally let us answer the question
this page most wants to answer: which recommendations turned into sales.
