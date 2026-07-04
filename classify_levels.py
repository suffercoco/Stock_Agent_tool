"""
Classify readings from stoch_data.db by turnover_ratio and save the result
into a separate database (stoch_levels.db).

Levels:
    level 1:  5%  <= turnover_ratio < 10%
    level 2:  10% <= turnover_ratio < 15%
    level 3:  turnover_ratio >= 15%

Rows below 5% (or with no ratio) don't reach any level and are skipped.

Rerunning is safe: each row in stoch_levels.db keeps the id of the reading it
came from, so already-classified readings are updated in place, not duplicated.

    uv run classify_levels.py
"""

import sqlite3
from pathlib import Path

SOURCE_DB = Path(__file__).parent / "stoch_data.db"
LEVELS_DB = Path(__file__).parent / "stoch_levels.db"

# (threshold the ratio must reach, level). Checked from the highest down.
LEVEL_THRESHOLDS = (
    (15.0, 3),
    (10.0, 2),
    (5.0, 1),
)


def level_of(turnover_ratio):
    """Level for a ratio (percentage number, e.g. 12.3). None when below 5%."""
    if turnover_ratio is None:
        return None
    for threshold, level in LEVEL_THRESHOLDS:
        if turnover_ratio >= threshold:
            return level
    return None


def init_levels_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS levels (
            reading_id     INTEGER PRIMARY KEY,  -- id of the row in readings
            captured_at    TEXT NOT NULL,
            time_slot      TEXT NOT NULL,
            stoch_number   TEXT NOT NULL,
            net_buy        REAL,
            turnover_ratio REAL NOT NULL,
            level          INTEGER NOT NULL      -- 1: 5-10%, 2: 10-15%, 3: >=15%
        )
        """
    )
    conn.commit()


def classify():
    if not SOURCE_DB.exists():
        raise FileNotFoundError(f"source database not found: {SOURCE_DB}")

    src = sqlite3.connect(SOURCE_DB)
    dst = sqlite3.connect(LEVELS_DB)
    try:
        init_levels_db(dst)
        rows = src.execute(
            "SELECT id, captured_at, time_slot, stoch_number, net_buy, "
            "turnover_ratio FROM readings"
        ).fetchall()

        saved = 0
        for reading_id, captured_at, slot, stock, net_buy, ratio in rows:
            level = level_of(ratio)
            if level is None:
                continue
            dst.execute(
                "INSERT OR REPLACE INTO levels "
                "(reading_id, captured_at, time_slot, stoch_number, "
                " net_buy, turnover_ratio, level) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (reading_id, captured_at, slot, stock, net_buy, ratio, level),
            )
            saved += 1
        dst.commit()
        print(f"{len(rows)} readings scanned, {saved} at level 1+ "
            f"saved to {LEVELS_DB.name}")
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    classify()
