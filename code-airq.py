# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Example sketch to connect to PM2.5 sensor with either I2C or UART.
"""

# pylint: disable=unused-import
import time
import board
import busio
from digitalio import DigitalInOut, Direction, Pull
from adafruit_pm25.i2c import PM25_I2C

reset_pin = None

# For use with microcontroller board:
# (Connect the sensor TX pin to the board/computer RX pin)
uart = busio.UART(board.TX, board.RX, baudrate=9600)

# Connect to a PM2.5 sensor over UART
from adafruit_pm25.uart import PM25_UART
pm25 = PM25_UART(uart, reset_pin)

print("Found PM2.5 sensor, reading data...")

def getAQI():


    if (aqdata["pm25 standard"] <= 12.0):
        AQI25 = (50/12) * (aqdata["pm25 standard"])
    elif (aqdata["pm25 standard"] <= 35.4):
        AQI25 = (49/23.3) * (aqdata["pm25 standard"] - 12.1) + 51
    elif (aqdata["pm25 standard"] <= 55.4):
        AQI25 = (49/19.9) * (aqdata["pm25 standard"] - 35.5) + 101
    elif (aqdata["pm25 standard"] <= 150.4):
        AQI25 = (49/94.9) * (aqdata["pm25 standard"] - 55.5) + 151
    elif (aqdata["pm25 standard"] <= 250.4):
        AQI25 = (99/99.9) * (aqdata["pm25 standard"] - 150.5) + 201
    elif (aqdata["pm25 standard"] <= 350.4):
        AQI25 = (99/99.9) * (aqdata["pm25 standard"] - 250.5) + 301
    elif (aqdata["pm25 standard"] <= 500.4):
        AQI25 = (99/149.9) * (aqdata["pm25 standard"] - 350.5) + 401

    if (aqdata["pm100 standard"] <= 54):
        AQI100 = (50/54) * (aqdata["pm100 standard"])
    elif (aqdata["pm100 standard"] <= 154):
        AQI100 = (49/99) * (aqdata["pm100 standard"] - 55) + 51
    elif (aqdata["pm100 standard"] <= 254):
        AQI100 = (49/99) * (aqdata["pm100 standard"] - 155) + 101
    elif (aqdata["pm100 standard"] <= 354):
        AQI100 = (49/99) * (aqdata["pm100 standard"] - 255) + 151
    elif (aqdata["pm100 standard"] <= 424):
        AQI100 = (99/69) * (aqdata["pm100 standard"] - 355) + 201
    elif (aqdata["pm100 standard"] <= 504):
        AQI100 = (99/79) * (aqdata["pm100 standard"] - 425) + 301

    remainder = (AQI25 + AQI100) % 2
    return int((AQI25 + AQI100) / 2 + remainder)

while True:
    time.sleep(1)

    try:
        aqdata = pm25.read()
        # print(aqdata)
    except RuntimeError:
        print("Unable to read from sensor, retrying...")
        continue

    print()
    print("Concentration Units (standard)")
    print("---------------------------------------")
    print(
        "PM 1.0: %d\tPM2.5: %d\tPM10: %d"
        % (aqdata["pm10 standard"], aqdata["pm25 standard"], aqdata["pm100 standard"])
    )
    print("---------------------------------------")
    print("AQI:", getAQI())

