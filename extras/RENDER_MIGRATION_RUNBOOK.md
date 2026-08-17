# Moving Postgres from Supabase to a new Render service

Written 12 August 2026. Follow top to bottom. Nothing here is irreversible until
**Step 7**, and even that is a one-line rollback.

## Why this move

The app already runs on Render. The database is on Supabase, so every query
crosses the public internet and is metered as egress — which is how the free
allowance hit 120% (6.02 GB against 5 GB). Putting the database on Render **in
the same region as the app** makes that traffic internal and unmetered. The
egress problem does not get cheaper; it stops existing.

Storage improves as a side effect: Render's free Postgres has been 1 GB against
Supabase's 0.5 GB, and the database is currently ~356 MB and growing.

## Read this before you start

**A free Render Postgres is deleted after ~30 days.** The previous one was, which
is why a new service is needed. Expect the new one to go the same way. This buys
time to get a decision made; it is not a resting place. Render's cheapest paid
Postgres (~$7/month, verify current pricing) is a far easier ask than Supabase
Pro at ~$25 and solves the same problem — worth putting in front of whoever signs
off.

**Do not start while the order backfill is running.** A dump taken mid-sync
captures half-populated tables, and the running job writes into a database you
are about to abandon. Wait for it to finish and confirm Steps 37/38 populated.

---

## 1. Create the Render Postgres

In the Render dashboard: **New → PostgreSQL**.

Two settings matter and only one is obvious:

- **Region — must be identical to the web service's region.** This is the entire
  point of the move. A database in a different region talks to the app over the
  public internet and is billed exactly like Supabase was. Check the web service's
  region first and match it; do not accept the default.
- **PostgreSQL version — same or newer than Supabase's.** Check Supabase's version
  first (`SHOW server_version;` in its SQL editor). `pg_restore` into an *older*
  server than the dump came from will fail partway, after it has already written
  some tables.

Everything else can stay default.

## 2. Collect the two connection strings

Render shows several. You need both of these and they are not interchangeable:

| String | Use it for |
|---|---|
| **External** (`...oregon-postgres.render.com`) | The restore in step 4, from your laptop |
| **Internal** (`...:5432/dbname`, no public host) | `DATABASE_URL` on the app in step 7 |

Using the external string as `DATABASE_URL` will work perfectly and quietly bill
you for egress forever — the exact problem being solved. Internal for the app,
external only from your machine.

## 3. Dump Supabase

`pg_dump` is at `C:\Program Files\PostgreSQL\18\bin` and is version 18.4, which is
new enough for any current Supabase server.

```bash
"/c/Program Files/PostgreSQL/18/bin/pg_dump" \
  --no-owner --no-privileges --format=custom \
  -d "$SUPABASE_URL" -f prod-20260812.dump
```

- `--no-owner --no-privileges` strips Supabase's role names, which do not exist on
  Render. Leaving them in is the usual cause of a restore that errors on every
  table.
- `--format=custom` is compressed and restores in parallel. Do not use plain SQL —
  `database/social_ai_backup.sql` is 69 MB as plain text for the same data.

Check the file is a plausible size before continuing. A 2 KB dump means it failed
and printed the reason above the prompt.

## 4. Restore into Render

```bash
"/c/Program Files/PostgreSQL/18/bin/pg_restore" \
  --no-owner --no-privileges --clean --if-exists -j 4 \
  -d "$RENDER_EXTERNAL_URL" prod-20260812.dump
```

Some warnings are normal and harmless — `--clean` tries to drop objects that do
not exist yet on a fresh database. What matters is that it finishes and the counts
in the next step match. Errors mentioning **roles** or **extensions** are the ones
to read; everything else is usually noise.

## 5. Verify BEFORE switching anything

This is the step that makes the difference between a migration and an incident.
Run against **both** databases and compare the numbers:

```sql
SELECT 'customers' AS t, count(*) FROM customers_cache
UNION ALL SELECT 'orders',    count(*) FROM orders_cache
UNION ALL SELECT 'refunds',   count(*) FROM refunds_cache
UNION ALL SELECT 'products',  count(*) FROM products_cache
UNION ALL SELECT 'messages',  count(*) FROM messages
UNION ALL SELECT 'convos',    count(*) FROM conversations
UNION ALL SELECT 'users',     count(*) FROM auth_users
ORDER BY 1;
```

Every row must match. Then confirm the schema arrived intact, not just the data:

```sql
SELECT count(*) AS tables FROM information_schema.tables
 WHERE table_schema='public' AND table_type='BASE TABLE';          -- expect 23

SELECT count(*) AS indexes FROM pg_indexes WHERE schemaname='public';

SELECT count(*) AS step37_cols FROM information_schema.columns
 WHERE table_name='orders_cache'
   AND column_name IN ('gross_sales','total_discounts','total_tax',
                       'total_shipping','total_refunded','cancelled_at','is_test');  -- expect 7

SELECT kind, watermark FROM sync_state ORDER BY kind;
```

If anything is short, stop. Do not switch. Re-dump and re-restore — nothing has
changed on the live system yet.

## 6. Do not skip: sequences

`pg_restore` carries sequence values, but confirm before the first write, because
the failure mode is duplicate-key errors on inserts that look like application
bugs:

```sql
SELECT max(id) AS max_id, (SELECT last_value FROM auth_users_id_seq) AS seq
FROM auth_users;
```

`seq` must be greater than or equal to `max_id`. If not:

```sql
SELECT setval('auth_users_id_seq', (SELECT max(id) FROM auth_users));
```

## 7. Switch the app

On the Render **web service** → Environment → set `DATABASE_URL` to the
**internal** connection string from step 2. Save; Render restarts automatically.

Then confirm it is actually talking to the new database:

- Load the Customer Profiling page — counts should look normal
- Sign in — this exercises `auth_users`, which proves reads and writes
- Trigger one sync manually (Actions → Daily Sync → `orders`) and confirm a new
  job id appears

## 8. Keep Supabase alive for a week

Do not delete the Supabase project. If something surfaces in two days, rolling
back is pasting the old `DATABASE_URL` and restarting — ten seconds. Restoring
from a dump under pressure is not.

Note that during this week the two databases **diverge**: writes go to Render
only. Rolling back after that point loses anything written since the switch, so
after about a week either commit to Render or plan a fresh dump.

## 9. After it settles

- Re-run the daily sync once and confirm it completes end to end
- Check Render's metrics for storage headroom (1 GB free tier)
- Egress on Supabase stops accruing the moment the app stops querying it
- Diarise the ~30-day free-instance expiry, or upgrade before it arrives

---

## Rollback

At any point before step 7, there is nothing to roll back — the live system is
untouched. After step 7:

1. Set `DATABASE_URL` back to the Supabase string
2. Restart the web service

That is the whole procedure, which is the reason step 8 exists.
