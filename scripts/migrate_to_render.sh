#!/usr/bin/env bash
#
# Supabase -> Render Postgres migration.
#
#   ./scripts/migrate_to_render.sh "<SUPABASE_URL>" "<RENDER_EXTERNAL_URL>"
#
# Dumps the source, restores into the target, then compares row counts table by
# table and refuses to declare success unless every one matches.
#
# It does NOT switch the application over. That is a dashboard change and it is
# the only irreversible-ish step, so it stays a deliberate human action. Nothing
# here touches the source database except to read it.
#
set -uo pipefail

PGBIN="/c/Program Files/PostgreSQL/18/bin"
DUMP="prod-$(date +%Y%m%d-%H%M).dump"

SRC="${1:-}"
DST="${2:-}"
if [ -z "$SRC" ] || [ -z "$DST" ]; then
  echo "usage: $0 '<SUPABASE_URL>' '<RENDER_EXTERNAL_URL>'" >&2
  exit 2
fi

say() { printf '\n=== %s ===\n' "$1"; }
q()   { "$PGBIN/psql" -X -A -t -d "$1" -c "$2" 2>/dev/null; }

# ── 0. Both ends reachable, and versions compatible ────────────────────────
say "Checking both databases"
SRCV=$(q "$SRC" 'show server_version')
DSTV=$(q "$DST" 'show server_version')
[ -z "$SRCV" ] && { echo "FAIL: cannot connect to source"; exit 1; }
[ -z "$DSTV" ] && { echo "FAIL: cannot connect to target"; exit 1; }
echo "source (Supabase): $SRCV"
echo "target (Render)  : $DSTV"

# Restoring into an older major version fails partway, after writing some tables.
if [ "${DSTV%%.*}" -lt "${SRCV%%.*}" ]; then
  echo "FAIL: target major version ${DSTV%%.*} is older than source ${SRCV%%.*}."
  echo "      Recreate the Render database on ${SRCV%%.*} or newer."
  exit 1
fi

# ── 1. Refuse to run mid-sync ──────────────────────────────────────────────
# A dump taken while the backfill is writing captures half-populated tables,
# and the job would keep writing into a database we are about to abandon.
say "Checking for running sync jobs"
RUNNING=$(q "$SRC" "select count(*) from sync_jobs where status='running'")
RUNNING="${RUNNING//[[:space:]]/}"
if [ "${RUNNING:-0}" != "0" ]; then
  echo "FAIL: $RUNNING sync job(s) still running on the source."
  q "$SRC" "select id||' '||kind||' started '||started_at from sync_jobs where status='running'"
  echo
  echo "Wait for them to finish (or stop them) and re-run. Migrating now would"
  echo "capture a half-written database."
  exit 1
fi
echo "none running - safe to proceed"

# ── 2. Dump ────────────────────────────────────────────────────────────────
say "Dumping source -> $DUMP"
# --no-owner/--no-privileges strip Supabase role names, which do not exist on
# Render and would otherwise error on nearly every object.
"$PGBIN/pg_dump" --no-owner --no-privileges --format=custom -d "$SRC" -f "$DUMP"
if [ $? -ne 0 ] || [ ! -s "$DUMP" ]; then
  echo "FAIL: dump did not complete"; exit 1
fi
echo "dump size: $(du -h "$DUMP" | cut -f1)"

# ── 3. Restore ─────────────────────────────────────────────────────────────
say "Restoring into target"
# Warnings are expected here: --clean tries to drop objects that do not exist
# yet on a fresh database. Row counts below are the real verdict, not this.
"$PGBIN/pg_restore" --no-owner --no-privileges --clean --if-exists -j 4 \
  -d "$DST" "$DUMP" 2>&1 | grep -Ei 'error|role|extension' | head -20
echo "(restore finished - any lines above are warnings to skim, not a verdict)"

# ── 4. Verify: counts must match exactly ───────────────────────────────────
say "Comparing row counts"
TABLES="customers_cache orders_cache refunds_cache products_cache messages conversations auth_users sync_state store_info_cache logs"
FAILED=0
printf '%-20s %12s %12s   %s\n' TABLE SUPABASE RENDER RESULT
for t in $TABLES; do
  a=$(q "$SRC" "select count(*) from $t"); a="${a//[[:space:]]/}"
  b=$(q "$DST" "select count(*) from $t"); b="${b//[[:space:]]/}"
  [ -z "$a" ] && a="(absent)"
  [ -z "$b" ] && b="(absent)"
  if [ "$a" = "$b" ]; then r="ok"; else r="MISMATCH"; FAILED=1; fi
  printf '%-20s %12s %12s   %s\n' "$t" "$a" "$b" "$r"
done

# ── 5. Schema landed, not just rows ────────────────────────────────────────
say "Schema checks"
for label in "tables:select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'" \
             "indexes:select count(*) from pg_indexes where schemaname='public'" \
             "step37_cols:select count(*) from information_schema.columns where table_name='orders_cache' and column_name in ('gross_sales','total_discounts','total_tax','total_shipping','total_refunded','cancelled_at','is_test')"; do
  name="${label%%:*}"; sql="${label#*:}"
  a=$(q "$SRC" "$sql"); a="${a//[[:space:]]/}"
  b=$(q "$DST" "$sql"); b="${b//[[:space:]]/}"
  if [ "$a" = "$b" ]; then r="ok"; else r="MISMATCH"; FAILED=1; fi
  printf '%-20s %12s %12s   %s\n' "$name" "$a" "$b" "$r"
done

# ── 6. Sequences ───────────────────────────────────────────────────────────
# pg_restore normally carries these, but a sequence left behind its table's
# max(id) surfaces later as duplicate-key errors that look like app bugs.
say "Sequence check on target"
"$PGBIN/psql" -X -d "$DST" -c "
SELECT s.relname AS sequence,
       last_value,
       CASE WHEN last_value >= COALESCE(m.mx,0) THEN 'ok' ELSE 'BEHIND - run setval' END AS state
FROM pg_class s
JOIN pg_sequences q ON q.sequencename = s.relname
LEFT JOIN LATERAL (SELECT max(id) AS mx FROM auth_users) m ON s.relname='auth_users_id_seq'
WHERE s.relkind='S' AND s.relname LIKE '%auth_users%';" 2>/dev/null

# ── Verdict ────────────────────────────────────────────────────────────────
echo
if [ "$FAILED" -eq 0 ]; then
  cat <<'DONE'
=== MIGRATION VERIFIED ===

Data is on Render and matches Supabase. The app is still pointed at Supabase.

To switch:
  1. Render dashboard -> your WEB SERVICE -> Environment
  2. Set DATABASE_URL to the INTERNAL connection string (NOT the external one
     you passed to this script). The internal string is what makes the traffic
     free - that is the entire reason for this move.
  3. Save. Render restarts on its own.
  4. Sign in to the app and load Customer Profiling to confirm.

Keep the Supabase project for about a week. Rolling back is pasting the old
DATABASE_URL and restarting. After that the two diverge and rollback loses
anything written since.
DONE
else
  echo "=== MISMATCH - DO NOT SWITCH ==="
  echo "Some counts differ. The live system is untouched, so re-run this script."
  exit 1
fi
