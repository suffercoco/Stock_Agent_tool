"""
Build dashboard.html from stoch_data.db.

Reads the readings table, keeps the newest reading per (stock, day) for the
chosen slot, and injects the rows as JSON into dashboard_template.html. The
result is one self-contained static file -- no server needed, so it can be
dropped on the NAS next to the databases (upload_to_nas.py picks it up).

Run after classify_levels.py in the daily pipeline:

    uv run build_dashboard.py                  # last 28 trading days, 15:00 slot
    uv run build_dashboard.py --days 60
    uv run build_dashboard.py --db some.db --out out.html
"""

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

# The notch thresholds come from the classifier so the dashboard can never
# disagree with stoch_levels.db.
from classify_levels import LEVEL_THRESHOLDS

HERE = Path(__file__).parent
TEMPLATE = HERE / "dashboard_template.html"
PLACEHOLDER = "__STOCH_DATA_JSON__"

# Same ordering the capture sweep uses (computer_use.py is not imported here
# because importing it instantiates the OCR engine).
STOCK_PREFIX_ORDER = ("60", "68", "00", "30", "92")


def stock_sort_key(code):
    prefix = code[:2]
    group = (
        STOCK_PREFIX_ORDER.index(prefix)
        if prefix in STOCK_PREFIX_ORDER
        else len(STOCK_PREFIX_ORDER)
    )
    return (group, code)


def load_readings(db_path, slot, n_days):
    """Return (days, stocks, ratio, net_buy) matrices for the last n_days.

    ratio/net_buy are stocks x days lists; None marks a missing reading.
    Multiple rows for the same (stock, day) keep the newest captured_at.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT stoch_number, substr(captured_at, 1, 10) AS day, "
            "       net_buy, turnover_ratio "
            "FROM readings WHERE time_slot = ? "
            "ORDER BY captured_at",  # later rows overwrite earlier ones below
            (slot,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        raise SystemExit(f"no readings for slot {slot!r} in {db_path}")

    latest = {}  # (stock, day) -> (net_buy, ratio)
    for stock, day, net_buy, ratio in rows:
        latest[(stock, day)] = (net_buy, ratio)

    days = sorted({day for _, day in latest})[-n_days:]
    day_index = {day: i for i, day in enumerate(days)}
    stocks = sorted({stock for stock, _ in latest}, key=stock_sort_key)

    ratio = [[None] * len(days) for _ in stocks]
    net_buy = [[None] * len(days) for _ in stocks]
    for s, stock in enumerate(stocks):
        for day, d in day_index.items():
            entry = latest.get((stock, day))
            if entry is None:
                continue
            net_buy[s][d], ratio[s][d] = entry
    return days, stocks, ratio, net_buy


def build(db_path, out_path, slot, n_days):
    days, stocks, ratio, net_buy = load_readings(db_path, slot, n_days)

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "slot": slot,
        "thresholds": sorted(th for th, _ in LEVEL_THRESHOLDS),
        "days": days,
        "stocks": stocks,
        "ratio": ratio,
        "net_buy": net_buy,
    }

    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"{TEMPLATE.name} has no {PLACEHOLDER} placeholder")
    # <\/ keeps a hypothetical "</script>" inside the JSON from closing the tag
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    out_path.write_text(template.replace(PLACEHOLDER, data_js), encoding="utf-8")
    print(
        f"{out_path.name}: {len(stocks)} stocks x {len(days)} days "
        f"({days[0]} .. {days[-1]}, slot {slot})"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--db", type=Path, default=HERE / "stoch_data.db")
    parser.add_argument("--out", type=Path, default=HERE / "dashboard.html")
    parser.add_argument("--slot", default="15:00", help="time_slot to chart")
    parser.add_argument(
        "--days", type=int, default=28, help="how many trading days to include"
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"database not found: {args.db}")
    build(args.db, args.out, args.slot, args.days)


if __name__ == "__main__":
    main()
