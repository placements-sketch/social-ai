# The customer assistant was overstating revenue by about 20%

**24 August 2026.** Plain English, for anyone who was given a number by the
"Ask about your customers" panel.

## What was wrong

Ask it *"Revenue by city this month"* and it counted **every order in the
system** — including orders that were voided, cancelled, never paid for, and
test orders placed by staff.

None of those are revenue. Voided orders in particular are money that never
changed hands.

## How far off

| Question | It said | Truth | Overstated by |
|---|---|---|---|
| This month | KES 8,939,615 | KES 7,435,260 | **20%** |
| Last 90 days | KES 37,801,497 | KES 33,265,986 | **14%** |
| All time | KES 792,762,672 | KES 648,156,830 | **22%** |

## Why it mattered more than it looks

*"Revenue by city this month"* was one of the four suggested questions printed
on the panel. It is the first thing anyone clicks. So this was not an obscure
path — it was the demonstration.

## What changed

The tool now counts **paid, non-cancelled, non-test orders only** — the same
population every other money figure on the Customers page uses. The table under
each answer now carries a fixed line saying so, which the AI cannot overwrite:

> Paid orders only · KES, VAT included · returns not deducted

## The other thing that was wrong

The assistant's instructions contained a hardcoded sentence: *"125,102 of
162,211 customers have never ordered."*

Both numbers were already stale, and they move with every sync — while writing
this the figure went from 125,123 to 125,125 in twenty minutes. The assistant
was repeating a fixed fact about a moving number.

That sentence is gone. It is now told that most customers have never ordered,
that it must say which denominator it used, and that if a count matters it has
to fetch one rather than recite one.

## What did NOT change

- Lifetime "Total spent" per customer — that comes from Shopify's own customer
  record and was always correct
- The segments themselves
- Anything a customer sees

## If someone quoted a figure from this panel

Anything phrased as revenue **over a time window** was roughly 14–22% high.
Anything phrased as a customer's lifetime spend was correct.
