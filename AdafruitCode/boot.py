import storage
import board
from digitalio import DigitalInOut, Direction, Pull
#import time

reset_button = DigitalInOut(board.D6)
reset_button.direction = Direction.INPUT
reset_button.pull = Pull.UP
#time.sleep(5)

"""
if not reset_button.val:
    print("Storage is in read-only mode")
    storage.remount("/", not reset_button.value)

else:
    print("Storage is accessible to user")
"""
storage.remount("/", False)
