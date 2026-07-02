# TODO
"""
step 1: move to specific coordination, then left lick
step 2: press enter, enter
step 3: check the time, start get data from 9:30.
In every 30 mins move to coordination(9:30) then coordiantion(10;00) for on and so forth untill cordination(15:00).
At each coordination get a screenshot from a specific area.
Step 4: run the screenshot through RapidOCR and pull the two numbers that follow
        the labels 主力净买额 (net buy, normalized to 万) and 占成交额比 (turnover ratio %).
step 5: save those two numbers with the stoch number as a row in the database

"""

import re
import sqlite3
import time
from datetime import datetime, time as dtime

import numpy as np
import pyautogui as gui
from rapidocr_onnxruntime import RapidOCR

# --------------------------------------------------------------------------- #
# Config  -- fill these in for your screen / setup
# --------------------------------------------------------------------------- #
# step 1: where to click first, then the keys to confirm in step 2.
START_COORD = (547, 41)

# step 3: the coordinate to move to for each 30-minute slot.
# Times run 9:30 -> 15:00 inclusive, every 30 minutes.
X_COORDINATION_SHIFT = 226
SLOT_Y = 337
SLOT_COORDS = {
    f"{10 + i // 2}:{'00' if i % 2 == 0 else '30'}": (226 + X_COORDINATION_SHIFT * i, SLOT_Y)
    for i in range(11)
}

# step 3: the fixed area to screenshot at each slot -> (left, top, width, height)
SCREENSHOT_REGION = (100, 662, 369, 683)

# step 4: local OCR engine (RapidOCR, ONNXRuntime backend). Instantiated once
# and reused for every screenshot.
ocr_engine = RapidOCR()

# step 5: sqlite database file.
DB_PATH = "stoch_data.db"

# step 4: the two labels we care about and the value that follows each.
#   主力净买额 -> a 净买额 in 万 / 亿  (stored normalized to 万)
#   占成交额比 -> a percentage        (stored as the bare number, e.g. 19.42)
LABEL_NET_BUY = "主力净买额"
LABEL_RATIO = "占成交额比"

# A signed decimal optionally followed by a 万/亿 unit. We allow any run of
# non-numeric "filler" (colon, spaces, full-width punctuation, OCR noise)
# between the label and its number.
_NUMBER = r"(-?\d+(?:\.\d+)?)"
_FILLER = r"[^\d\-]*"
NET_BUY_RE = re.compile(LABEL_NET_BUY + _FILLER + _NUMBER + r"\s*(万|亿)?")
RATIO_RE = re.compile(LABEL_RATIO + _FILLER + _NUMBER)

# how many 万 each unit represents (values are normalized to 万).
_UNIT_TO_WAN = {"万": 1, "亿": 10_000}


def click(x, y):
    gui.moveTo(x, y)
    gui.click()


def enter(input):
    gui.write(input)
    gui.press("enter")


class get_data:
    def __init__(self, stoch_number, db_path=DB_PATH):
        # the stoch number this run's readings are paired with (step 5).
        self.stoch_number = stoch_number
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at    TEXT NOT NULL,
                time_slot      TEXT NOT NULL,
                stoch_number   REAL NOT NULL,
                net_buy        REAL,   -- 主力净买额, normalized to 万
                turnover_ratio REAL    -- 占成交额比, percentage number (e.g. 19.42)
            )
            """
        )
        self.conn.commit()

    # --- step 1: move to a coordinate and left click ----------------------- #
    def step1(self):
        click(*START_COORD)

    # --- step 2: press enter twice ----------------------------------------- #
    def step2(self):
        gui.press("enter")
        gui.press("enter")

    # --- step 3: loop the 30-minute slots, screenshot each area ------------ #
    def step3(self):
        for slot, coord in SLOT_COORDS.items():
            self._wait_until(slot)
            gui.moveTo(*coord)
            shot = gui.screenshot(region=SCREENSHOT_REGION)

            # step 4 + 5 happen for each captured slot.
            net_buy, turnover_ratio = self.step4(shot)
            self.step5(slot, net_buy, turnover_ratio)

    @staticmethod
    def _wait_until(slot):
        """Block until the local clock reaches `slot` (HH:MM). Past slots run now."""
        hh, mm = map(int, slot.split(":"))
        target = dtime(hour=hh, minute=mm)
        while datetime.now().time() < target:
            time.sleep(5)

    # --- step 4: OCR the screenshot, pull the two labelled numbers --------- #
    def step4(self, image):
        # RapidOCR takes a numpy array (RGB). pyautogui returns a PIL image.
        result, _ = ocr_engine(np.asarray(image))

        # result is a list of [box, text, score]; None when nothing is found.
        # Join the recognized text boxes (reading order) so a label and the
        # number next to it land in the same string for the regexes below.
        text = " ".join(line[1] for line in result) if result else ""

        net_buy = self._parse_net_buy(text)
        turnover_ratio = self._parse_ratio(text)
        return net_buy, turnover_ratio

    @staticmethod
    def _parse_net_buy(text):
        """Number after 主力净买额, normalized to 万 (亿 -> ×10000). None if absent."""
        m = NET_BUY_RE.search(text)
        if not m:
            return None
        value = float(m.group(1))
        unit = m.group(2) or "万"          # bare number is already in 万
        return value * _UNIT_TO_WAN[unit]

    @staticmethod
    def _parse_ratio(text):
        """Number after 占成交额比, e.g. 19.42. None if absent."""
        m = RATIO_RE.search(text)
        return float(m.group(1)) if m else None

    # --- step 5: save the two numbers paired with the stoch number --------- #
    def step5(self, slot, net_buy, turnover_ratio):
        captured_at = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO readings "
            "(captured_at, time_slot, stoch_number, net_buy, turnover_ratio) "
            "VALUES (?, ?, ?, ?, ?)",
            (captured_at, slot, self.stoch_number, net_buy, turnover_ratio),
        )
        self.conn.commit()

    @staticmethod
    def is_market_day(date=None):
        """True on weekdays. The market is closed Sat/Sun (holidays not handled)."""
        date = date or datetime.now()
        return date.weekday() < 5      # Mon=0 ... Fri=4, Sat=5, Sun=6

    def run(self):
        if not self.is_market_day():
            print(f"{datetime.now():%Y-%m-%d} is a weekend; market closed, skipping.")
            return
        self.step1()
        self.step2()
        self.step3()

    def close(self):
        self.conn.close()


def plus(a, b):
    return a + b


if __name__ == "__main__":
    job = get_data(stoch_number=0)   # <-- TODO pass the stoch number for this run
    try:
        job.run()
    finally:
        job.close()
