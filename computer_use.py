# TODO
"""
1. confrim what should be click and it's coordination
2. structure:
    2.1 capture application screenshot
    2.2 mouse and keyboard control
    2.3 
"""

import pyautogui as gui
import pygetwindow as gw

def click(x,y):
    gui.moveTo(x,y)
    gui.click

def enter(input):
    gui.write(input)
    gui.press('enter')

def get_screenshot():
    gui.screenshot()



# def plus(a,b):
#     return a+b