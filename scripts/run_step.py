#!/usr/bin/env python
"""
Run a numbered step from database/PRODUCTION_CHANGES.md against the database.

    python scripts/run_step.py --list          # what steps exist
    python scripts/run_step.py 44              # show step 44's SQL (does NOT run)
    python scripts/run_step.py 44 --run        # actually run it
    python scripts/run_step.py 44 --run --local   # run against the local copy

Exists because Render, unlike Supabase, gives you no SQL console — so the steps
in PRODUCTION_CHANGES.md had nowhere to be pasted. Reading them straight out of
that file also removes the copy-paste step, which is where a half-selected
statement gets run.

Safe by default: printing is the default action and --run is required to execute.
Everything runs inside one transaction and rolls back on any error, except the
statements that cannot (VACUUM, CREATE INDEX CONCURRENTLY), which are detected
and run in autocommit instead.
"""
import argparse
import os
import re
import sys

# The step titles contain em-dashes and arrows, and the Windows console
# defaults to cp1252, which cannot encode them - printing the list would die
# on a character rather than on anything to do with the database.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHANGES = os.path.join(ROOT, 'database', 'PRODUCTION_CHANGES.md')

# Statements Postgres refuses to run inside a transaction block. Wrapping these
# in BEGIN/COMMIT fails with a message that reads like a syntax error.
NO_TRANSACTION = ('vacuum', 'create index concurrently', 'drop index concurrently',
                  'reindex', 'alter system')


def load_steps():
    """{number: (title, [sql blocks])} for every step in the file."""
    text = open(CHANGES, encoding='utf-8').read()
    steps = {}
    for chunk in re.split(r'^### Step ', text, flags=re.M)[1:]:
        m = re.match(r'(\d+)\s*[—-]\s*(.*)', chunk)
        if not m:
            continue
        num, title = int(m.group(1)), m.group(2).strip().splitlines()[0]
        blocks = re.findall(r'```sql\n(.*?)```', chunk, re.S)
        steps[num] = (title, blocks)
    return steps


def connect(local):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
    # External, not Internal: the internal hostname only resolves from inside
    # Render. Running this from a laptop needs the public one.
    key = 'DATABASE_URL' if local else 'External_Database_URL'
    url = os.getenv(key)
    if not url:
        sys.exit(f"{key} is not set in .env")
    import psycopg2
    return psycopg2.connect(url), url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('step', nargs='?', type=int)
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--run', action='store_true', help='actually execute (default is print only)')
    ap.add_argument('--local', action='store_true', help='use DATABASE_URL instead of the Render one')
    args = ap.parse_args()

    steps = load_steps()

    if args.list or args.step is None:
        print(f"{len(steps)} steps in database/PRODUCTION_CHANGES.md\n")
        for n in sorted(steps):
            title, blocks = steps[n]
            mark = f"{len(blocks)} sql block(s)" if blocks else "no sql - notes only"
            print(f"  {n:>3}  {title[:66]:<66} {mark}")
        print("\n  python scripts/run_step.py <n>        show the SQL")
        print("  python scripts/run_step.py <n> --run  execute it")
        return

    if args.step not in steps:
        sys.exit(f"No step {args.step}. Try --list.")

    title, blocks = steps[args.step]
    print(f"Step {args.step} - {title}\n")
    if not blocks:
        print("This step has no SQL (notes only). Nothing to run.")
        return

    for i, sql in enumerate(blocks, 1):
        print(f"--- block {i} of {len(blocks)} " + "-" * 46)
        print(sql.strip())
        print()

    if not args.run:
        print("Not executed. Re-run with --run to apply.")
        return

    conn, url = connect(args.local)
    host = url.split('@')[-1].split('/')[0]
    print(f"Running against {host}\n")

    for i, sql in enumerate(blocks, 1):
        body = sql.strip()
        low = body.lower()
        needs_autocommit = any(k in low for k in NO_TRANSACTION)
        # The step usually carries its own BEGIN/COMMIT; psycopg2 opens a
        # transaction anyway, so strip them rather than nesting.
        body = re.sub(r'^\s*BEGIN\s*;', '', body, flags=re.I)
        body = re.sub(r'COMMIT\s*;\s*$', '', body, flags=re.I).strip()
        if not body:
            continue
        try:
            conn.autocommit = needs_autocommit
            with conn.cursor() as cur:
                cur.execute(body)
                note = f"{cur.rowcount} row(s)" if cur.rowcount is not None and cur.rowcount >= 0 else "ok"
            if not needs_autocommit:
                conn.commit()
            print(f"  block {i}: {note}" + ("  [autocommit]" if needs_autocommit else ""))
        except Exception as e:
            if not needs_autocommit:
                conn.rollback()
            print(f"  block {i}: FAILED - {str(e).strip().splitlines()[0]}")
            print("\nRolled back. Nothing from this block was applied.")
            conn.close()
            sys.exit(1)

    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
