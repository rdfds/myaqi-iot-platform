import io
import json
import wifi
import adafruit_requests
import socketpool
import ssl
import adafruit_httpserver.methods

CONFIG_DATA = None
pool = None
server =  None
requests = None

#File System Functions
def loadConfigFile():
    global CONFIG_DATA
    file = io.open("config.json", mode="r")
    CONFIG_DATA = json.load(file)

    pass

def writeConfigToFile():
    jsonString = json.dumps(CONFIG_DATA)
    print(jsonString)
    with open("/config.json", "w") as file:
        file.write(jsonString)

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

    return True

def setupWebServer():
    global CONFIG_DATA
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

    @server.route("/updateCredentials", adafruit_httpserver.methods.HTTPMethod.POST)
    def updateCreds(request: HTTPRequest):
        #print(request.body)
        #print(request.body.decode("utf-8"))
        ssid = request.body.decode("utf-8").split("&")[0].split("=")[1]
        password = request.body.decode("utf-8").split("&")[1].split("=")[1]

        print(ssid, password)
        CONFIG_DATA['ssid'] = ssid
        CONFIG_DATA['password'] = password
        print(CONFIG_DATA)
        removeError() # calling removeError will save config file
        #saveConfigFile()


    print(f"listening on http://{wifi.radio.ipv4_gateway_ap}:80")
    server.serve_forever(str(wifi.radio.ipv4_gateway_ap))


def startAP():



    print("Starting AP...")
    wifi.radio.enabled = False
    wifi.radio.stop_station()

    wifi.radio.start_ap(CONFIG_DATA["AP_SSID"], CONFIG_DATA["AP_PASSWORD"])

    wifi.radio.enabled = True

    setupWebServer()

def setupRequests():
    global requests

    pool = socketpool.SocketPool(wifi.radio)
    requests = adafruit_requests.Session(pool, ssl.create_default_context())

def connectToWifi():
    print("Connecting to Wifi...")
    try:

        wifi.radio.connect(CONFIG_DATA["ssid"], CONFIG_DATA["password"])
        if wifi.radio.ap_info.ssid == CONFIG_DATA["ssid"]:
            print("Connected to AP")
            #setup the requests object
            setupRequests()
            print(requests)
            #test the connection with a reque
            response = requests.get("https://google.com")
            #print(response.content)
     #       print(response.headers)
    #        print(response.text)
            if (response.status_code < 500):
                pass
                print("Connected to the internet!")
                #assume the request went through
            else:
                pass
                #assume the request failed
                #enter error state mode
                #write error message to CONFIG_DATA
                #write error flag to CONFIG_DATA
                #Indicate to user (via LED) than an error occured
                #restart the device
    except:
        addError("Unable to connect to home Wifi. Check ssid and password", 1)
        #write error message to CONFIG_DATA
        #write error flag to CONFIG_DATA
        #Indicate to user (via LED) than an error occured
        #restart the device
        import supervisor
        supervisor.reload()

def reset():
    pass

def checkForErrors():

    if not(CONFIG_DATA["errorMessage"] == "" and CONFIG_DATA["errorCode"] == -1):

        print("Error noted in config file")
        return True


    return False

#TODO:
    #Check is reset button is pressed during startup
        #if test run reset procedure
    #check for error code (Specifically for wifi connection issues)
        # if error code 1 - Unable to connecto to wifi access point
            #put device into conifg mode (AP Mode) and display error to user
        # if error code 2 - Unable to reach the internet
            #put device into conifg mode (AP Mode) and display error to user


loadConfigFile()

if checkForErrors():
    startAP()
else:
    if checkForWifiCredentials():
        # Connect to Wifi
        connectToWifi()

    else:
        # Start Wifi in access point mode

        startAP()

while True:

    pass

