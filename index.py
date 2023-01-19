from flask import Flask, request
import requests, json

app = Flask(__name__)

@app.route("/")
def index():
    return "test"

@app.route("/api/indoorsend")
def sendIndoorData():

    a = request.args
    currentaqi = a["currentaqi"]
    deviceSerialNumber = a["deviceSerialNumber"]
    print(type(currentaqi))
    print("TEST")
    
    #Get the location of this device
    deviceInfo = None
    print('https://servicedeath.backendless.app/api/data/devices?where=deviceSerialNumber='+deviceSerialNumber)
    try:
        deviceInfo = requests.get(
        'https://servicedeath.backendless.app/api/data/devices?where=deviceSerialNumber='+deviceSerialNumber
        ).json()
        
    except Exception as e:
        print(e)
        print(str(e))
        print("Failed to get device info")
    
    # #get the weather for the location
    print(deviceInfo)
    weatherData = None
    weather_response = None
    aqi = None
    
    if not deviceInfo == None:
              try:
                url = "http://api.airvisual.com/v2/nearest_city"
                params = {'lat': deviceInfo[0]["latitude"], 'lon': deviceInfo[0]["longitude"], 'key': 'REDACTED_LEGACY_SECRET'}
                s = requests.Session()

                weatherData = requests.get(url, params = params).json()

                
    
                aqi = weatherData['data']['current']['pollution']['aqius']
                print(type(aqi))
              except Exception as e:
                print(e)
                print(str(e))
                print("Failed to get the weather data for the location of this device", deviceSerialNumber)

    #Insert data into Outdoor table
    if not weatherData == None:
              try:
                headers = {'content-type': 'application/json'}
                json_data_weather = {
                    "aqi": aqi,
                    "deviceSerialNumber": deviceSerialNumber
                }

                weather_response = requests.post(
                'https://servicedeath.backendless.app/api/data/OutdoorData', headers=headers, data=json.dumps(json_data_weather)
                ).json()
              except Exception as e:
                print(e)
                print(str(e))
                print("Failed to insert outdoor data for device", deviceSerialNumber)


    # #Insert data into Indoor table
    
    json_data = {
      "aqi" : int(currentaqi),
        "deviceSerialNumber": deviceSerialNumber
    }
    headers = {'content-type': 'application/json'}

    r = requests.post(
    'https://servicedeath.backendless.app/api/data/IndoorData', headers=headers, data=json.dumps(json_data)
    ).json()

    #check this data table for the oldest entry for the serialNumber. If it's older than 24hrs drop

    return { "deviceInfo": deviceInfo, "weather": weatherData, "weatherResponse": weather_response, "indoorDataResponse": r }




def outdoorAverage(average):

    json_data = {
      "aqi" : average
    }

    headers = {'content-type': 'application/json'}

    r = requests.post(
    'https://servicedeath.backendless.app/api/data/AverageOutdoorData', headers=headers, data=json.dumps(json_data)
    )


def outdoorDelete():

    headers = {'content-type': 'application/json'}

    r = requests.delete(
    'https://servicedeath.backendless.app/api/data/bulk/OutdoorData', headers=headers
    )


def indoorAverage(average):

    json_data = {
      "aqi" : average
    }

    headers = {'content-type': 'application/json'}

    r = requests.post(
    'https://servicedeath.backendless.app/api/data/AverageIndoorData', headers=headers, data=json.dumps(json_data)
    )


def indoorDelete():

    headers = {'content-type': 'application/json'}

    r = requests.delete(
    'https://servicedeath.backendless.app/api/data/bulk/IndoorData', headers=headers
    )


@app.route("/api/outdoorsend")
def sendOutdoorData():

    #a = request.args
    #ID = a["ID"]
    url = "http://api.airvisual.com/v2/nearest_city?"
    payload = {}
    headers = {}
    params = {'lat': "39.7066", 'lon': "-73.5493", 'key': 'REDACTED_LEGACY_SECRET'}

    response = requests.request("GET", url, headers=headers, data=payload, params = params)
    #response = requests.request("GET", "http://api.airvisual.com/v2/nearest_city?)
    data = json.loads(response.text)

    aqi = data['data']['current']['pollution']['aqius']
    print(type(aqi))
    headers = {'content-type': 'application/json'}
    json_data = {
    "aqi": aqi
    }

    r = requests.post(
    'https://servicedeath.backendless.app/api/data/OutdoorData', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"


@app.route("/api/averageoutdoor")
def createOutdoorAverage():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/OutdoorData', headers=headers
    )

    data = r.json()
    sum = 0

    for item in data:
        sum += item['aqi']

    try:

        average = int(sum / len(data))
        print(average)
        outdoorAverage(average)
        outdoorDelete()

    except ZeroDivisionError:

        print()

    return "<div></div>"




@app.route("/api/averageindoor")
def createIndoorAverage():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/IndoorData', headers=headers
    )


    data = r.json()
    print(data)
    sum = 0

    for item in data:
        sum += item['aqi']

    try:

        average = int(sum / len(data))
        indoorAverage(average)
        indoorDelete()

    except ZeroDivisionError:
        print()

    return "<div></div>"


@app.route("/api/indoorretrieve")
def pullIndoorData():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/IndoorData', headers=headers
    )

    return "<div></div>"


@app.route("/api/outdoorretrieve")
def pullOutdoorData():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/OutdoorData', headers=headers
    )

    return "<div></div>"


# ping url with all the things as query parameters
@app.route("/api/registration")
def registration():

    a = request.args
    email = a["email"]
    firstname = a["firstname"]
    lastname = a["lastname"]
    password = a["password"]
    phone = a["phone"]

    json_data = {
        "email" : email,
        "firstname" : firstname,
        "lastname" : lastname,
        "password" : password,
        "phone" : phone
    }

    headers = {'content-type': 'application/json'}

    r = requests.post(
    'https://servicedeath.backendless.app/api/data/User', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"


@app.route("/api/appindoornow")
def appIndoorNow():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/IndoorData', headers=headers
    )

    json_data = r.json()

    r = requests.post(
    'XXXXXXXXXXXXXX', headers=headers, data=json.dumps(json_data)
    )
    return "<div></div>"


@app.route("/api/appindoordaily")
def appIndoorDaily():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/AverageIndoorData', headers=headers
    )

    json_data = r.json()

    r = requests.post(
    'XXXXXXXXXXXXXX', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"


@app.route("/api/appoutdoornow")
def appOutdoorNow():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/OutdoorData', headers=headers
    )

    json_data = r.json()

    r = requests.post(
    'XXXXXXXXXXXXXX', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"


@app.route("/api/appoutdoordaily")
def appOutdoorDaily():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/AverageOutdoorData', headers=headers
    )

    json_data = r.json()

    r = requests.post(
    'XXXXXXXXXXXXXX', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"
