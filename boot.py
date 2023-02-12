import storage
import board
from digitalio import DigitalInOut, Direction, Pull

reset_button = DigitalInOut(board.D6)
reset_button.direction = Direction.INPUT
reset_button.pull = Pull.UP

if not reset_button.val:
    print("Storage is in read-only mode - Accessible to device")
    storage.remount("/", not reset_button.value)

else:
    print("Storage is accessible to user - Available to update code")

