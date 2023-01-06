import ipaddress
import ssl
import wifi
import socketpool
import adafruit_requests

import time
import board
import pwmio

import busio
from digitalio import DigitalInOut, Direction, Pull
from adafruit_pm25.i2c import PM25_I2C

#used for the adafruit requests object for making http requests
requests = None

reset_pin = None

pm25 = None

motorController = pwmio.PWMOut(board.A0, frequency=500, duty_cycle=0)
PWM_MIN = 20000
PWM_MAX = 65535

ARDUINO_UPDATE_ADDRESS = "https://myaqifinal.vercel.app/api/indoorsend"
IQAIR_UPDATE_ADDRESS = "https://myaqifinal.vercel.app/api/outdoorsend"

#AQI_UPDATE_INTERVAL = 5 * 60
AQI_UPDATE_INTERVAL = 20
AQI_last_update = 0

ARDUINO_RESET_ADDRESS = "https://myaqifinal.vercel.app/api/indoorretrieve"
IQAIR_RESET_ADDRESS = "https://myaqifinal.vercel.app/api/outdoorretrieve"
DB_RESET_INTERVAL = 24 * 60 * 60
DB_reset_last_executed = 0


def getAQI():

    try:
        aqdata = pm25.read()

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
        print(AQI25, AQI100)
        remainder = (AQI25 + AQI100) % 2
        print("remainder", remainder)
        return int((AQI25 + AQI100) / 2 + remainder)

    except RuntimeError:
        print()

def setupAQSensor():
    global pm25

    uart = busio.UART(board.TX, board.RX, baudrate=9600)

    # Connect to a PM2.5 sensor over UART
    from adafruit_pm25.uart import PM25_UART
    pm25 = PM25_UART(uart, reset_pin)

    print("Found PM2.5 sensor, reading data...")
def sendArduinoData():
    airQuality = getAQI()
    print(airQuality)

    try:
        response = requests.get(ARDUINO_UPDATE_ADDRESS+"?currentaqi="+str(airQuality))
    except AssertionError as error:
        print(response.text)

def clearArduinoDB():

    try:
        response = requests.get(ARDUINO_RESET_ADDRESS)
    except AssertionError as error:
        print(response.text)

def sendIqairData():

    try:
        response = requests.get(IQAIR_UPDATE_ADDRESS)

    except AssertionError:
        print()

def clearIqairDB():

    try:
        response = requests.get(IQAIR_RESET_ADDRESS)

    except AssertionError:
        print()

def connectToWifi():
    global requests

    pool = socketpool.SocketPool(wifi.radio)
    requests = adafruit_requests.Session(pool, ssl.create_default_context())
    try:
        from secrets import secrets
    except ImportError:
        print("WiFi secrets are kept in secrets.py, please add them there!")
        raise

    print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])

    print("Connecting to %s"%secrets["ssid"])
    wifi.radio.connect(secrets["ssid"], secrets["password"])
    print("Connected to %s!"%secrets["ssid"])
    print("My IP address is", wifi.radio.ipv4_address)



#Connect to WiFi
connectToWifi()
setupAQSensor()

#Setup 5 minute interval to send AQI Data to server

#Setup 24hr interval to delete data from database




while True:

    #check to see if it's time to send AQI info
    if time.monotonic() > AQI_last_update + AQI_UPDATE_INTERVAL:
        AQI_last_update = time.monotonic()
        print("SEND DATA")
        sendArduinoData()
        sendIqairData()

    if time.monotonic() > DB_reset_last_executed + DB_RESET_INTERVAL:
        DB_reset_last_executed = time.monotonic()
        print("Clear DB")
        clearArduinoDB()
        clearIqairDB()
