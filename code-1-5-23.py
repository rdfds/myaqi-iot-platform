import io
import json
import wifi
import adafruit_requests
import socketpool
import ssl
import adafruit_httpserver.methods
import board
from digitalio import DigitalInOut, Direction, Pull
import time
import neopixel
import microcontroller
import mdns

server = None
#Setup reset button
reset_button = DigitalInOut(board.GP22)
reset_button.direction = Direction.INPUT
reset_button.pull = Pull.UP

RESET_HOLD_TIME = 3

buttonPressed = False
buttonPressTime = None

#setup neopixel status indicator 
pixel_pin = board.GP21
num_pixels = 1

pixels = neopixel.NeoPixel(pixel_pin, num_pixels, brightness=0.25, auto_write=False)

STATES = [
    {
        'state_number': 0,
        'state_name': "Normal",
        'state_color': (0, 255, 0),
        'state_description': "Normal operation of the device. No errors detected that need indicated to the user"
    },
    {
        'state_number': 1,
        'state_name': "Wifi connect Mode (AP Mode)",
        'state_color': (0, 0, 255),
        'state_description': "Mode used to allow the user to provide wifi credentials to device to connect to network"
    },
    {
        'state_number': 2,
        'state_name': "Error Mode",
        'state_color': (255, 0, 0),
        'state_description': "An error has occured and the user should be notified. After resetting the deviec, it should go into AP mode and display the error to the user on the built-in web page"
    },
    {
        'state_number': 3,
        'state_name': "Resetting Mode",
        'state_color': (255, 255, 0),
        'state_description': "The device is resetting for some reason. Either user initiated or some error was encountered"
    }
]

def updateStatusLED():
    
    pixels[0] = STATES[current_state]["state_color"]
    pixels.show()
    
#File System Functions
def loadConfigFile():
    global CONFIG_DATA
    file = io.open("config.json", mode="r")
    CONFIG_DATA = json.load(file)

    pass

def writeConfigToFile():
    try:
        jsonString = json.dumps(CONFIG_DATA)
        print(jsonString)
        with open("/config.json", "w") as file:
            file.write(jsonString)
    except:
        print("Unable to save config file to disk")

def saveConfigFile():
    global CONFIG_DATA
    CONFIG_DATA["test"] = "test"

    writeConfigToFile()

def addError(message, errCode=0):
    global CONFIG_DATA

    CONFIG_DATA["errorMessage"] = message
    CONFIG_DATA["errorCode"] = errCode

    writeConfigToFile()

def removeError():
    global CONFIG_DATA

    CONFIG_DATA["errorMessage"] = ""
    CONFIG_DATA["errorCode"] = -1

    writeConfigToFile()

def checkForWifiCredentials():
    try:
        CONFIG_DATA["ssid"]
        CONFIG_DATA["password"]
    except KeyError:
        print("Error getting credentials from file")
        return False
    
    if CONFIG_DATA["ssid"] == "" or CONFIG_DATA["password"] == "":
        
        return False
        
    return True

def setupWebServer():
    global CONFIG_DATA
    global server
    
    #TO DO: TEST TO ENSURE THE INDEX.HTML FILE IS ACTUALLY BEING SERVED
    print("Starting web server...")

    import socketpool
    from adafruit_httpserver.mime_type import MIMEType
    from adafruit_httpserver.request import HTTPRequest
    from adafruit_httpserver.response import HTTPResponse
    from adafruit_httpserver.server import HTTPServer

    pool = socketpool.SocketPool(wifi.radio)
    server = HTTPServer(pool)

    @server.route("/")
    def base(request: HTTPRequest):

        print("request received")

        with HTTPResponse(request, content_type=MIMEType.TYPE_HTML) as response:
            response.send_file("index.html")
    
    @server.route("/updateCredentials")
    def reservePage(request: HTTPRequest):


        with HTTPResponse(request, content_type=MIMEType.TYPE_HTML) as response:
            response.send_file("index.html")
    
    @server.route("/updateCredentials", adafruit_httpserver.methods.HTTPMethod.POST)
    def updateCreds(request: HTTPRequest):
        #print(request.body)
        #print(request.body.decode("utf-8"))
        ssid = request.body.decode("utf-8").split("&")[0].split("=")[1]
        password = request.body.decode("utf-8").split("&")[1].split("=")[1]

        print(ssid, password)
        CONFIG_DATA['ssid'] = ssid
        CONFIG_DATA['password'] = password
        removeError() # calling removeError will save config file
        print(CONFIG_DATA)
        

        
        response = HTTPResponse(request)
        response.send("Credentials Updated")
        #saveConfigFile()
        time.sleep(5)
        microcontroller.reset()


    print(f"listening on http://{wifi.radio.ipv4_gateway_ap}:80")
    server.start(str(wifi.radio.ipv4_gateway_ap))


def startAP():
    global current_state
    current_state = 1
    updateStatusLED()
    
    try:
        print("Starting AP...")
        wifi.radio.enabled = False
        wifi.radio.stop_station()
        wifi.radio.enabled = True
        wifi.radio.start_ap(CONFIG_DATA["AP_SSID"], CONFIG_DATA["AP_PASSWORD"])
        
        setupWebServer()
        
    except Exception as e:
        print(Exception)
        print(str(e))
        print("Error setting up access point")
        print("resetting...")
        time.sleep(5)
        microcontroller.reset()

def setupRequests():
    global requests

    pool = socketpool.SocketPool(wifi.radio)
    requests = adafruit_requests.Session(pool, ssl.create_default_context())

def connectToWifi():
    global current_state
    
    print("Connecting to Wifi...")
    try:
        print(CONFIG_DATA["ssid"], CONFIG_DATA["password"])
        wifi.radio.enabled = False
        wifi.radio.stop_station()

        wifi.radio.start_station()
        wifi.radio.enabled = True
        wifi.radio.connect(CONFIG_DATA["ssid"], CONFIG_DATA["password"])

        
    except Exception as e:
        print(str(e))
        addError("Unable to connect to home Wifi. Check ssid and password", 1)
        #write error message to CONFIG_DATA
        #write error flag to CONFIG_DATA
        #Indicate to user (via LED) than an error occured
        current_state = 2
        updateStatusLED()
        time.sleep(10)
        #restart the device
        #import supervisor
        #supervisor.reload()
        microcontroller.reset()

def testRequest():
    
    try:
        response = requests.get("https://google.com")
        print(response.status_code)
        print("Make http request successfully")
    except:
        print("Error reaching out to the internet")
        addError("Unable to reach the internet", 2)


def reset():

    global CONFIG_DATA
    global current_state
    print("Resetting...")
    file = io.open("config.bak", mode="r")
    CONFIG_DATA = json.load(file)
    
    writeConfigToFile()

    
    current_state = 3
    updateStatusLED()
    time.sleep(3)

    microcontroller.reset()

def checkForErrors():

    if not(CONFIG_DATA["errorMessage"] == "" and CONFIG_DATA["errorCode"] == -1):

        print("Error noted in config file")
        return True

    return False

def checkResetButton():
    global reset_button
    global buttonPressed
    global buttonPressTime
    
    if not buttonPressed:
        
        if not reset_button.value:
            buttonPressed = True
            buttonPressTime = time.monotonic()
            
            
            time.sleep(0.5)
    else:
        if (time.monotonic() - buttonPressTime > RESET_HOLD_TIME):
            reset()

        if reset_button.value:
            buttonPressed = False

################################### START OF PROGRAM ###########################################################

pixels[0] = (255, 0, 0)

current_state = 0

updateStatusLED()

time.sleep(2)



CONFIG_DATA = None
pool = None
server =  None
requests = None


loadConfigFile()

#if checkForErrors():
#    pass
#else:
if checkForWifiCredentials():
    # Connect to Wifi
    connectToWifi()
    setupRequests()
    testRequest()

else:
    # Start Wifi in access point mode
    current_state = 3
    updateStatusLED()
    time.sleep(3)
    startAP()

while True:
    
    try:
        server.poll()
    except:
        pass
        
    checkResetButton()

    updateStatusLED()

