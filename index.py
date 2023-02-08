from flask import Flask, request, jsonify
import requests, json
import time
from datetime import datetime

app = Flask(__name__)

@app.route("/")
def index():
    return "test"

@app.route("/api/indoorsend")
def sendIndoorData():

    a = request.args
    currentaqi = a["currentaqi"]
    deviceSerialNumber = a["deviceserialnumber"]
    
    
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
    sensorData = deleteOlderDataEntries(deviceSerialNumber)
    return "Done"


@app.route("/api/activate", methods=["PUT"])
def activateDevice():
    deviceSerialNumber = request.args["deviceserialnumber"]
    
    #Get the location of this device
    deviceInfo = None
    try:
        deviceInfo = requests.get(
        'https://servicedeath.backendless.app/api/data/devices?where=deviceSerialNumber='+deviceSerialNumber
        ).json()
        
    except Exception as e:
        print(e)
        print(str(e))
        print("Failed to get device info")
    print(deviceInfo)
    json_data = {
        "active": True
    }

    headers = {
        "Content-Type": "application/json"
    }

    r = requests.put(
    'https://servicedeath.backendless.app/api/data/devices/'+deviceInfo[0]["objectId"], data=json.dumps(json_data), headers=headers
    ).json()
    print(r)

    
    return {"activationReponse": r}
    


@app.route("/api/registerdevice", methods=["PUT","GET"])
def register():
    
    deviceSerialNumber = request.args["deviceserialnumber"]
    userId = request.args["userid"]
    latitude = request.args["latitude"]
    longitude = request.args["longitude"]
    
    #Get the location of this device
    deviceInfo = None
    try:
        deviceInfo = requests.get(
        'https://servicedeath.backendless.app/api/data/devices?where=deviceSerialNumber='+deviceSerialNumber
        ).json()
        
    except Exception as e:
        print(e)
        print(str(e))
        print("Failed to get device info")
    print(deviceInfo)
    
    json_data = {
        "device_owner": userId,
        "latitude" : latitude,
        "longitude" : longitude
    }

    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        r = requests.put(
        'https://servicedeath.backendless.app/api/data/devices/'+deviceInfo[0]["objectId"], data=json.dumps(json_data), headers=headers
        )
        print(r.url)
        print(r.json())
        return "Device Registered"
    
    except Exception as e:
        print(e)
        print(str(e))
    
    return "Failed to register device"

def deleteOlderDataEntries(dsn):
    print("Deleting old data...")
    sensorData = None
    time24HrsAgo = None
    time24HrsAgoString = None
    
    try:
        sensorData = requests.get(
        'https://servicedeath.backendless.app/api/data/IndoorData?where=deviceSerialNumber='+ dsn + '&sortBy=%60created%60%20desc'
        ).json()

        #get first entry
        
        mostRecent = sensorData[0]["created"]
        # print(mostRecent)
        time24HrsAgo = mostRecent/1000 - (24 * 60 * 60) + (5 * 60 * 60) 
        # print(time24HrsAgo)
        print(time.strftime('%m-%d-%Y %H:%M:%S', time.localtime(mostRecent/1000)))
        time24HrsAgoString = time.strftime('%m-%d-%Y %H:%M:%S', time.localtime(time24HrsAgo))
        
    except Exception as e:
        print(e)    
        print(str(e))

    if not time24HrsAgo == None:

        try:
            deleteRequest = requests.delete(
            'https://servicedeath.backendless.app/api/data/bulk/IndoorData?where=deviceSerialNumber='+ dsn + 'and created<\'' + time24HrsAgoString.replace(":", "%3A") + '\''
            )
            print("/data/bulk/IndoorData?where=deviceSerialNumber%3D1000000000%20and%20created%3C'01-19-2023%2012%3A00%3A00'")
            print(deleteRequest.url)
            print("############")
            print(deleteRequest.json())
        except Exception as e:
            print(e)
            print(str(e))

    
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
    
    #finding the correct entry
    entry = requests.get(   
    'https://servicedeath.backendless.app/api/data/User?where=userID%20=%20%27'+email+'%27
    )
    
    json_data = entry.json();
    userID = json_data['objectID']
    
    return jsonify(json_data)
    #return "<div></div>"


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
