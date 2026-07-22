"""
Change the date of readings in stoch_data.db.

Selects rows by the date part of captured_at (optionally narrowed to one
time_slot or to specific row ids) and rewrites the date, keeping the clock
time untouched. By default the script only previews the rows that would
change; pass --apply to actually write.

    uv run change_time_slot.py --from 2026-07-21 --to 2026-07-20             # preview
    uv run change_time_slot.py --from 2026-07-21 --to 2026-07-20 --apply
    uv run change_time_slot.py --from 2026-07-21 --to 2026-07-20 --slot 15:00 --apply
    uv run change_time_slot.py --to 2026-07-20 --ids 12 13 14 --apply
    uv run change_time_slot.py --to 2026-07-20 --ids 12-20 25 --apply
    uv run change_time_slot.py --to 2026-07-20 --last 10 --apply

stoch_levels.db is derived from stoch_data.db, so after applying a change
rerun classify_levels.py (and build_dashboard.py) to keep them in sync.
"""

import argparse
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "stoch_data.db"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLOT_RE = re.compile(r"^\d{2}:\d{2}$")


def id_token(token):
    """Parse an --ids token: a single id ('12') or a range ('12-20')."""
    if "-" in token:
        lo, hi = token.split("-", 1)
        lo, hi = int(lo), int(hi)
        if lo > hi:
            raise argparse.ArgumentTypeError(f"empty range {token!r}")
        return list(range(lo, hi + 1))
    return [int(token)]


def select_rows(conn, old_date, slot, ids, last):
    where, params = [], []
    if old_date:
        where.append("substr(captured_at, 1, 10) = ?")
        params.append(old_date)
    if slot:
        where.append("time_slot = ?")
        params.append(slot)
    if ids:
        where.append(f"id IN ({','.join('?' * len(ids))})")
        params.extend(ids)
    sql = "SELECT id, captured_at, time_slot, stoch_number FROM readings"
    if where:
        sql += f" WHERE {' AND '.join(where)}"
    if last:
        rows = conn.execute(
            sql + " ORDER BY id DESC LIMIT ?", params + [last]
        ).fetchall()
        return rows[::-1]
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--from", dest="old_date", metavar="YYYY-MM-DD",
                        help="current date to match, e.g. 2026-07-21")
    parser.add_argument("--to", dest="new_date", metavar="YYYY-MM-DD",
                        required=True,
                        help="new date value, e.g. 2026-07-20")
    parser.add_argument("--slot", metavar="HH:MM",
                        help="only rows with this time_slot, e.g. 15:00")
    parser.add_argument("--ids", type=id_token, nargs="+", metavar="ID",
                        help="only these row ids; single ids or ranges "
                             "like 12-20")
    parser.add_argument("--last", type=int, metavar="N",
                        help="only the newest N matching rows (by id)")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--apply", action="store_true",
                        help="write the change (default is preview only)")
    args = parser.parse_args()
    if args.ids:  # each token parses to a list; merge and dedupe
        args.ids = sorted({i for chunk in args.ids for i in chunk})

    if not args.old_date and not args.ids and not args.last:
        parser.error("select rows with --from, --ids and/or --last")
    if args.last is not None and args.last < 1:
        parser.error("--last must be a positive number")
    for date in (args.old_date, args.new_date):
        if date and not DATE_RE.match(date):
            parser.error(f"bad date {date!r}, expected YYYY-MM-DD")
    if args.slot and not SLOT_RE.match(args.slot):
        parser.error(f"bad slot {args.slot!r}, expected HH:MM")
    if not args.db.exists():
        raise SystemExit(f"database not found: {args.db}")

    conn = sqlite3.connect(args.db)
    try:
        rows = select_rows(conn, args.old_date, args.slot, args.ids, args.last)
        if not rows:
            print("no matching rows")
            return

        for row_id, captured_at, slot, stock in rows:
            new_captured_at = args.new_date + captured_at[10:]
            print(f"  id={row_id}  {slot}  {stock}  "
                  f"{captured_at} -> {new_captured_at}")

        if not args.apply:
            print(f"{len(rows)} rows would change; rerun with --apply to write")
            return

        conn.execute(
            f"UPDATE readings SET captured_at = ? || substr(captured_at, 11) "
            f"WHERE id IN ({','.join('?' * len(rows))})",
            [args.new_date] + [r[0] for r in rows],
        )
        conn.commit()
        print(f"{len(rows)} rows updated in {args.db.name}")
        print("remember to rerun classify_levels.py to refresh stoch_levels.db")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
