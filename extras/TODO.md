Here's the full board, roughly in priority order:

🔴 Active — AI accuracy (what we're mid-fight with)
Vision→catalog match precision — diagnostic edit written, not yet deployed. Next test answers one question: is the right product in the 12 candidates or not?
Not in list → fix search recall (search category+colour, not vision's adjectives; widen pool)
In list, not picked → fix the discrimination prompt + stop trusting high
Confirmed-match leak — the two edits (pass only the verified product; tighten the prompt) — deployed?
JSON parse bug in verify_product_match — fixed in the same pending edit
Double-reply — pre-dispatch re-check landed in services.py; the routes.py batched-events fix I'm not sure ever went in


🟡 Deploy / verify (small, unconfirmed)
Channel Performance — zero-activity channel filter (both card blocks + optional channelStats)
Per-comment post previews — CommentPostPreview building and rendering?
Notifications prune cron → add to GitHub Actions workflow
Discord sync alerts — confirm they went quiet post-migration


🔵 Meta (submitted, waiting ~20 days)
Keep Miles Zetu IG + webhooks live; don't touch admin@company.com
If Meta comes back with changes → bring me the feedback
On approval → connect the official Shop Zetu account for production
Data deletion callback — currently logs only, doesn't delete; also [email protected] placeholder on the status page


🟣 Needs your supervisor (not code)
Internal @vivo* staff accounts skewing top spenders / revenue-by-segment
Shopify read_all_orders scope — kills the 60-day bulk-sync blind spot


⚪ Deferred / optional
Embedding-based image search (CLIP vectors over product photos) — the real long-term fix for #1
Comment→DM (post-approval; private_replies + compliance)
9-segment taxonomy (skipped), windowed RFM (deferred)
End-to-end conversion-attribution test


Get these done:
- Remove profiling config as a main in the sidebar, put it UNDER customer profiling in a dropdown in the sidebar
- Forwarding of posts to dm should read image
- why are we describing the image when the ai should literally be looking at the image
- double messaging!!(Outbounds sometimes appear twice in-app only or sometimes it replies with 2 diff messages)
- Analytics page 'Conversion funnel' is UGLY and i dont even get it
- Does the AI learn with time, if yes, how??
- AI failed replies count in dashboard keeps increasing and idk why or what counts to those failures. The analytics page doesnt log the reasons for failure either, its blank!
- Channel performance sidebar and card section should show other channels
- Also it has a top gap
- The dashboard filters arent working on the KPIs
- The pop-up notification keeps re-popping up on every page refresh
- In the chat panel, make the links clickable and the images expandable
- Gross sales(Customer profiling page)- should be calculated by Cost of item / 1.16


- System issues detected in topbar should tell us exactly what issues otherwise its not helping us really

- Backup the DB!