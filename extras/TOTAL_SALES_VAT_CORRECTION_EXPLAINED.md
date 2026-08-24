# Why Total sales dropped by KES 95 million

**24 August 2026.** Plain English, for anyone who asks why the number changed.

## The short version

Our Total sales figure was **too high by KES 95,483,070 — about 18%.**

It said **KES 625,690,260**. It should have said **KES 530,207,190**.

Nothing was stolen, nothing was lost, and no data was wrong. We were adding VAT
to a figure that already had VAT inside it.

## How it happened

Shopify publishes the formula for Total sales, and we followed it exactly:

```
gross sales − discounts − returns + shipping + taxes = total sales
```

That formula is correct **for shops that add VAT at the checkout** — where the
price on the tag is KES 1,000, and the customer pays KES 1,160.

**Shop Zetu does not work that way.** Our prices are VAT-inclusive. The tag says
KES 1,160 and that is what the customer pays; the KES 160 of VAT is already
inside it.

So when the formula said "+ taxes", we added VAT that was already counted. The
same KES 81.4 million went in twice.

## The second, smaller error

Returns were being subtracted **without** VAT while gross sales included it. So
every returned item gave back less than it had taken. That understated returns
by **KES 14.1 million**.

Both errors pushed the same way — upward.

| | |
|---|---|
| VAT counted twice | KES 81,407,953 |
| Returns understated | KES 14,075,117 |
| **Total overstatement** | **KES 95,483,070** |

## How we know this is right, and not just a different opinion

Three checks, all run against the live database, all agreeing.

**1. The arithmetic of every single order.**
For each order, does `gross − discounts + delivery` equal what the customer was
charged?

- Without adding tax: correct on **133,360 out of 133,360 orders (100%)**
- Adding tax as well: correct on **2.3%**

**2. The size of the VAT figure itself.**
Kenyan VAT is 16%. If VAT is added on top of the price, VAT is 16% of the price.
If VAT is inside the price, VAT is 16/116 = **13.79%** of it.

Across 105,761 orders, our VAT averages **13.89%** of the price. Inside.

**3. The simplest orders we have.**
Take the 26,105 paid orders with no discount and no delivery charge. If VAT were
added at checkout, the total would be higher than the product price.

- Total equals the product price: **26,102 of 26,105 (100.0%)**
- Total equals product price + VAT: **5.2%**

**4. Two different routes now meet.**
Total sales is built from the component formula. "Kept" is built a completely
different way — take what customers were actually charged, subtract returns.

- Total sales: **530,207,190**
- Kept: **530,212,643**

They differ by **KES 5,453** out of 530 million — rounding. Before the fix these
two numbers were 95 million apart, and nobody noticed because they sit in
different parts of the page.

## What changed on the page

- VAT is no longer a line that gets added. It now reads **"of which VAT"**, in
  grey, with no plus sign — reported, not applied.
- Returns are now subtracted VAT-inclusive, matching the basis of everything
  else in the column.
- The explanation under the table used to say *"Taxes and shipping are added,
  not deducted."* That was wrong, and the code agreed with it, which is how the
  error survived. It now says VAT is already inside, and explains why Shopify's
  published formula does not apply to us.

## What did NOT change

- **Order totals.** What each customer was charged was always correct.
- **Gross sales** (KES 637,111,485) — unchanged.
- **Revenue / Total spent** figures from Shopify's own customer records —
  untouched.
- **Discounts and delivery** — unchanged.

Only the Total sales line, and Returns, moved.

## If someone asks "so which figure was Shopify showing?"

Shopify's own Reports will show its own Total sales. If it differs, that is a
separate and known issue: Reports (the `read_reports` analytics layer) has been
found by Shop Zetu's data and finance teams to omit orders. Everything on this
page is computed from the Orders API directly, order by order, which is the
instruction we were given. That is also why we can check the arithmetic on
133,360 individual orders — you cannot do that against a report.
