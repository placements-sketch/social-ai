# Customer export — CSV and PDF

Plain-English notes on the Export button on the Customer Profiling page, and
the reasoning behind the choices, so the decisions can be defended without
reading the code.

## What it does

The **Export** button on Customer Profiling opens a menu with two options.
Both export **every customer matching what you are currently looking at** — the
search box, the segment filter and the sort order are all carried through — not
just the 20 rows visible on the page.

| | CSV | PDF |
|---|---|---|
| What it is | The raw data | A document |
| Rows | Up to 20,000 | Up to 500 |
| Contains | Nothing but rows | Segment mix + the customer table |
| Made for | Excel, pivot tables, mail-merge | Emailing, printing, meetings |

## Why the two limits are different

This is the question most likely to be asked, so it is worth being direct.

They are **not the same export in two file formats**. They are two different
tools:

- **CSV is the data.** Somebody opens it in Excel and works on it. It should
  carry as many rows as it reasonably can. 20,000 rows is about a 3MB file,
  which Excel handles without complaint. The limit exists because everything is
  assembled in the browser's memory first, and there is a point past which the
  tab stops responding.

- **PDF is a document.** Somebody emails it, or brings it to a meeting. If we
  put 20,000 rows into a PDF it would be roughly **600 pages and about 40MB** —
  technically an export, practically un-openable, and too large for most email
  systems to accept. So it carries a bounded top 500 **under the sort you
  already chose**, which is what makes it useful: sorted by highest spend, it is
  your top 500 customers by spend.

## The part that matters most: it tells you when it is a sample

Every export states its own coverage, on the file itself:

> *"Showing the top 500 of 162,224 matching customers, by highest spend.
> This is a sample, not the full list."*

or, when nothing was cut off:

> *"All 1,842 matching customers."*

In the PDF this sits in bold under the header, above the table. In the CSV it is
a `Coverage` row in the preamble, before the column headings.

This exists because of a specific failure: a file that quietly stops at N reads
as *"this is all of them"* to whoever receives it. That is how a partial list
becomes "our customer base" in somebody else's inbox, and how a number gets
quoted in a meeting that nobody can later reproduce. The previous version of
this button exported the 20 rows on screen out of 162,224 and said nothing about
it.

Both files also record the filters applied, the sort order, and when they were
generated — so a file found six months later can still explain itself.

## Other details worth knowing

- **The PDF's segment mix is counted over the rows in the document**, not over
  the whole result set, and is labelled *"Segment mix of these 500"*. Quoting
  the mix of 162,000 customers above a table showing the top 500 by spend would
  describe a population the reader cannot see.

- **The CSV opens correctly in Excel with accented names.** It is written with a
  UTF-8 byte-order mark; without it, Excel guesses the system codepage and
  mangles every non-English name on open.

- **Names containing quotes or commas do not break the columns.** A customer
  named `O"Brien` or an address with a comma in it is escaped to the CSV
  standard. A subtly misaligned spreadsheet is worse than one that fails to
  open, because somebody will use it.

- **Progress is shown while exporting.** At 20,000 rows the browser makes 200
  separate requests to the server, which takes a while. The button counts up
  (`Exporting 4,300 / 20,000…`) so a slow export cannot be mistaken for a frozen
  one.

- **The money column is labelled `Total Spent (KES, incl. tax)`** — matching what
  Shopify reports, rather than a figure we recalculated.

## What was tested

The export was run end-to-end against generated data before shipping: the PDF
was produced and checked for page count and layout, the CSV was checked for the
byte-order mark, line endings, quote escaping, and the coverage wording in both
the truncated and complete cases. The row-limit and progress reporting were
verified against a paged source.

The PDF layout was verified by generating real files outside the browser; it has
not been visually confirmed in-browser, which is worth a quick look on first use.
