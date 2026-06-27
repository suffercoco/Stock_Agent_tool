# TODO
"""
step 1: move to specific coordination, then left lick
step 2: press enter, enter
step 3: check the time, start get data from 9:30.
In every 30 mins move to coordination(9:30) then coordiantion(10;00) for on and so forth untill cordination(15:00).
At each coordination get a screenshot from a specific area.
Step 4: pass that screenshot to a ocr model to extract the information from it. Only keep numbers from it, including positive and negtive numbers.
step 5: save that number with stoch number as a pair in database
"""

import base64
import io
import re
import sqlite3
import time
from datetime import datetime, time as dtime

import pyautogui as gui
from openai import OpenAI

# --------------------------------------------------------------------------- #
# Config  -- fill these in for your screen / setup
# --------------------------------------------------------------------------- #
# step 1: where to click first, then the keys to confirm in step 2.
START_COORD = (325, 69)          # (x, y) to click in step 1   <-- TODO set this

# step 3: the coordinate to move to for each 30-minute slot.
# Times run 9:30 -> 15:00 inclusive, every 30 minutes.
X_COORDINATION_SHIFT = 396
SLOT_Y = 882
SLOT_COORDS = {
    f"{10 + i // 2}:{'00' if i % 2 == 0 else '30'}": (521 + X_COORDINATION_SHIFT * i, SLOT_Y)
    for i in range(11)
}

# step 3: the fixed area to screenshot at each slot -> (left, top, width, height)
SCREENSHOT_REGION = (146, 1353, 583, 1388)   # <-- TODO set this

# step 4: OCR model served by LM Studio (must be vision-capable).
client = OpenAI(base_url="http://127.0.0.1:1234/v1", api_key="lm-studio")
OCR_MODEL = "google/gemma-4-e4b"

# step 5: sqlite database file.
DB_PATH = "stoch_data.db"

# matches integers and decimals, with an optional leading minus sign.
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


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
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at  TEXT NOT NULL,
                time_slot    TEXT NOT NULL,
                stoch_number REAL NOT NULL,
                value        REAL NOT NULL
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
            numbers = self.step4(shot)
            self.step5(slot, numbers)

    @staticmethod
    def _wait_until(slot):
        """Block until the local clock reaches `slot` (HH:MM). Past slots run now."""
        hh, mm = map(int, slot.split(":"))
        target = dtime(hour=hh, minute=mm)
        while datetime.now().time() < target:
            time.sleep(5)

    # --- step 4: OCR the screenshot, keep only the numbers ----------------- #
    def step4(self, image):
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        resp = client.chat.completions.create(
            model=OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe every number you see in this image, "
                            "exactly as shown, including any minus signs. "
                            "Return only the numbers separated by spaces.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
        )
        text = resp.choices[0].message.content or ""
        return [float(n) for n in NUMBER_RE.findall(text)]

    # --- step 5: save each number paired with the stoch number ------------- #
    def step5(self, slot, numbers):
        captured_at = datetime.now().isoformat(timespec="seconds")
        self.conn.executemany(
            "INSERT INTO readings (captured_at, time_slot, stoch_number, value) "
            "VALUES (?, ?, ?, ?)",
            [(captured_at, slot, self.stoch_number, value) for value in numbers],
        )
        self.conn.commit()

    def run(self):
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
