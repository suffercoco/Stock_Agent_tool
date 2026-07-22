# TODO verify db is correctly save data or not
"""
step 1: move to specific coordination, then left lick
step 2: press enter
step 3: check the current time first -- a slot can only be captured after it has
        actually happened. For each captured slot (currently only 15:00):
        wait until the slot time is reached, then sweep ALL stocks for that slot:
        move to the slot coordination, screenshot the data area, OCR the current
        stock number from its own area, then click to the next stock and repeat.
        The stock list is ordered (prefix groups 60, 68, 00, 30, 92, codes
        increasing within each group) but of unknown length; when the OCR'd
        code sorts lower than the previous one the list has wrapped, the lap
        is complete and we move on to the next slot.
Step 4: run the screenshot through MinerU's OCR and pull the two numbers that follow
        the labels 主力净买额 (net buy, normalized to 万) and 占成交额比 (turnover ratio %).
step 5: save those two numbers keyed by the OCR'd stock number as a row in the
        database

"""

import logging
import re
import sqlite3
import time
from datetime import datetime, time as dtime
from pathlib import Path

import cv2
import numpy as np
import pyautogui as gui
from mineru.model.ocr.pytorch_paddle import PytorchPaddleOCR

# --------------------------------------------------------------------------- #
# Config  -- fill these in for your screen / setup
# --------------------------------------------------------------------------- #
# step 1: where to click first, then the keys to confirm in step 2.
START_COORD = (547, 41)

# step 3: the coordinate to move to for each 30-minute slot.
# The market breaks for lunch 11:30 -> 13:00, and slots are labelled by their
# end time, so the tradable slots are the 8 below. Each slot's x-position is
# set manually; y is the shared SLOT_Y.
SLOT_Y = 390
SLOT_X = {
    "10:00": 235,
    "10:30": 413,
    "11:00": 577,
    "11:30": 741,
    "13:30": 905,
    "14:00": 1069,
    "14:30": 1233,
    "15:00": 1305,
}
# Only these slots are captured; the others are listed for completeness.
CAPTURE_SLOTS = ("15:00")
SLOT_COORDS = {
    slot: (x, SLOT_Y)
    for slot, x in SLOT_X.items()
    if slot in CAPTURE_SLOTS
}

# step 3: the fixed area to screenshot at each slot -> (left, top, width, height)
SCREENSHOT_REGION = (100, 662, 269, 23)

# step 3: click here to switch to the next stock.
NEXT_STOCK_COORD = (125, 61)

# step 3: the area showing the current stock number -> (left, top, width, height)
STOCK_NUMBER_REGION = (1522, 79, 58, 20) 

# The list is ordered: prefix groups appear as 60, 68, 00, 30, 92, and codes
# increase within each group. How many stocks the list holds is unknown, so the
# wrap-around signal is the ordering going backwards (see stock_sort_key).
STOCK_PREFIX_ORDER = ("60", "68", "00", "30", "92")
# Anchoring on those prefixes keeps stray OCR digits from being read as a code.
STOCK_NUMBER_RE = re.compile(r"(?:60|68|00|30|92)\d{4}")


def stock_sort_key(code):
    """Position of `code` in the list: prefix-group order, then numeric value."""
    return (STOCK_PREFIX_ORDER.index(code[:2]), int(code))

# seconds to let the UI redraw after switching stocks
SWITCH_DELAY = 1.0

# An OCR miss on one stock is skipped (logged, then on to the next stock), but
# this many misses in a row means the screen itself is broken (popup, lock
# screen, app closed) -- and since wrap-around detection needs readable codes,
# clicking blindly past it could loop forever. Stop instead.
MAX_CONSECUTIVE_OCR_MISSES = 10

# Failures and progress go to this file as well as the console.
LOG_PATH = str(Path(__file__).parent / "computer_use.log") 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# step 4: local OCR engine (MinerU's PaddleOCR-in-PyTorch port). Instantiated
# once and reused for every screenshot; models auto-download on first run.
ocr_engine = PytorchPaddleOCR(lang="ch")


def ocr_text(image):
    """OCR a PIL screenshot with MinerU, joining the lines in reading order.

    MinerU's engine expects a BGR numpy array and returns, per image,
    a list of [box, (text, score)] -- or None when nothing is found.
    """
    bgr = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    result = ocr_engine.ocr(bgr)[0]
    return " ".join(line[1][0] for line in result) if result else ""

# step 5: sqlite database file.
DB_PATH = str(Path(__file__).parent / "stoch_data.db")

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
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at    TEXT NOT NULL,
                time_slot      TEXT NOT NULL,
                stoch_number   TEXT NOT NULL,  -- OCR'd from STOCK_NUMBER_REGION
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
        # gui.press("enter")

    # --- step 3: for each slot that has happened, sweep every stock --------- #
    def step3(self):
        for slot, coord in SLOT_COORDS.items():
            self._wait_until(slot)
            self._sweep_stocks(slot, coord)

    def _sweep_stocks(self, slot, coord):
        """Capture `slot` for every stock, clicking through the whole list.

        The list is ordered (prefix groups 60/68/00/30/92, increasing codes
        within each group) but its length is unknown, so the wrap-around signal
        is the sort key going backwards: the code we just OCR'd sorts lower than
        the previous one only when the list has looped back to the first stock.
        Leaves the UI on the first stock, ready for the next slot's sweep.
        """
        prev_key = None
        misses = 0
        while True:
            stock_number = self._read_stock_number()
            if stock_number is None:
                # Logged inside _read_stock_number; skip this stock and keep
                # sweeping -- unless the misses pile up, which means the whole
                # screen is unreadable and the wrap can no longer be detected.
                misses += 1
                if misses >= MAX_CONSECUTIVE_OCR_MISSES:
                    raise RuntimeError(
                        f"[{slot}] {misses} consecutive OCR misses -- "
                        f"screen looks broken, aborting the sweep"
                    )
                click(*NEXT_STOCK_COORD)
                time.sleep(SWITCH_DELAY)
                continue
            misses = 0

            key = stock_sort_key(stock_number)
            if prev_key is not None and key < prev_key:
                break               # order went backwards: lap done
            prev_key = key

            gui.moveTo(*coord)
            shot = gui.screenshot(region=SCREENSHOT_REGION)

            # step 4 + 5 happen for each stock at this slot.
            net_buy, turnover_ratio = self.step4(shot)
            if net_buy is None and turnover_ratio is None:
                # Delisted stock: the code still exists in the app but its
                # data panel is empty, so there is no row worth saving.
                log.info("[%s] %s: no data (delisted?), skipping", slot, stock_number)
            else:
                self.step5(slot, stock_number, net_buy, turnover_ratio)

            click(*NEXT_STOCK_COORD)
            time.sleep(SWITCH_DELAY)        # let the next stock's page render

    def _read_stock_number(self, retries=3):
        """OCR the current stock number from STOCK_NUMBER_REGION (e.g. '600000').

        Returns None when all retries fail, logging what OCR saw on each try
        so the miss can be diagnosed later; the caller skips this stock.
        """
        attempts = []
        for _ in range(retries):
            shot = gui.screenshot(region=STOCK_NUMBER_REGION)
            text = ocr_text(shot)
            m = STOCK_NUMBER_RE.search(text)
            if m:
                return m.group(0)
            attempts.append(text)
            time.sleep(1)                   # screen may still be redrawing
        log.warning(
            "no stock number OCR'd from %s after %d tries, skipping "
            "(texts per try: %r)",
            STOCK_NUMBER_REGION, retries, attempts,
        )
        return None

    @staticmethod
    def _wait_until(slot):
        """Block until the local clock reaches `slot` (HH:MM). Past slots run now."""
        hh, mm = map(int, slot.split(":"))
        target = dtime(hour=hh, minute=mm)
        while datetime.now().time() < target:
            time.sleep(5)

    # --- step 4: OCR the screenshot, pull the two labelled numbers --------- #
    def step4(self, image):
        # Join the recognized text boxes (reading order) so a label and the
        # number next to it land in the same string for the regexes below.
        text = ocr_text(image)

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

    # --- step 5: save the two numbers keyed by the OCR'd stock number ------- #
    def step5(self, slot, stock_number, net_buy, turnover_ratio):
        captured_at = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO readings "
            "(captured_at, time_slot, stoch_number, net_buy, turnover_ratio) "
            "VALUES (?, ?, ?, ?, ?)",
            (captured_at, slot, stock_number, net_buy, turnover_ratio),
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
    job = get_data()
    try:
        job.run()
    finally:
        job.close()
