import pyautogui
import time

print("Press Ctrl+C to quit.")
try:
    while True:
        # Get the current X and Y coordinates
        x, y = pyautogui.position()
        
        # Print them on the same line
        print(f"Current Position: X: {x:>4} | Y: {y:>4}", end="\r")
        time.sleep(0.1)
        
except KeyboardInterrupt:
    print("\nTracking stopped.")