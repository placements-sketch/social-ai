# What left to be done for MVP

A few things still parked for another day:

1. Customer Profiling page (deferred)
2. Conversion Rate dashboard card (still fake values)
3. High failure rate alert (needs cron)
4. SLA breach notifications (needs SLA config)
5. Customer-replied-after-silence (needs detection logic)
6. Token expiry cron (currently only fires when admin manually tests channel)
7. Meta Advanced Access submission
8. Real Claude swap (still USE_MOCK_AI = True)





What's done
The core product works end-to-end:

Inbound DMs land, customer is identified or created, conversation persists
AI replies with real Shopify data — products, prices, stock, store locations
AI respects stock + budget constraints (after the latest fixes)
AI hands off to humans without making fake promises
Human agents can edit/unsend/take over any conversation
Outbound replies actually deliver via Meta Graph API
Customer profiling layer — 161k customers + orders + segments + RFM + LTV projections
Internal dashboard is polished — Dashboard, Messages, Channels, Customers, CustomerDetail, Analytics, Products, AISettings, Automation, Users, Notifications
Auth + roles + audit logging for the internal team
OAuth flow + DB-stored tokens (replacing the env-var hack)
Physical shops context flowing into the AI
Memory-safe sync on Render (no more OOMs)

That's a real product. If a small team at Shop Zetu had this in front of them today, they could run real conversations through it tomorrow with their tester accounts.
What an MVP technically is vs what you've built
A true MVP is "smallest thing that delivers core value." By that definition, you passed MVP weeks ago — somewhere around the time the AI started replying to real DMs with real product data.
What you've built since is more like a v1.0 production-ready product, not an MVP. The dashboard polish, the customer profiling, the LTV projections, the segmented analytics — none of that is MVP-tier. That's all v1+ thinking. Which is fine, but worth naming.
What's NOT done (the honest list)
Hard blockers for live deployment with real customers:

Meta App Review submission + approval → 2-6 weeks once started, can't shortcut
Business Verification → requires Shop Zetu's legal docs, you don't have them
Webhook signature verification → currently OFF, code exists but env var disabled

Production hardening that any real launch needs:

Real conversion-rate tracking (currently a fake number on the dashboard)
Cron jobs for: token expiry alerts, sync watchdog, customer-replied-after-silence detection
Error monitoring tied into something like Sentry (you have audit logs but nothing fires alerts)
Rate limiting on your own endpoints
Proper backup strategy for the Render Postgres
A documented "what to do when X breaks" runbook

Nice-to-haves you mentioned across sessions:

Mobile responsiveness passes 3 and 4
Edit User modal, Edit Rule modal
Shipping zones sync (you have locations done, but not shipping zones or active discounts)
Analytics top-products with real names (reverted earlier; the precomputed table approach is still pending)
Phase 2 work — making AI replies leverage customer profile data (recognize VIP at first DM, etc.)

Stuff that doesn't matter for MVP but will matter eventually:

Multi-tenant (right now it assumes one Shop Zetu business per deployment)
WhatsApp integration (stubbed)
Facebook Messenger (stubbed)
TikTok integration (stubbed)