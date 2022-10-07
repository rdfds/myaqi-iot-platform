
from flask import Flask, request
import requests, json

app = Flask(__name__)

def iqAirAverage(average):

    json_data = {
      "aqi" : average
    }

    headers = {'content-type': 'application/json'}

    r = requests.post(
    'https://servicedeath.backendless.app/api/data/AverageAPICall', headers=headers, data=json.dumps(json_data)
    )


def iqAirDelete():

    headers = {'content-type': 'application/json'}

    r = requests.delete(
    'https://servicedeath.backendless.app/api/data/bulk/APICall', headers=headers

    )

def arduinoAverage(average):

    json_data = {
      "aqi" : average
    }

    headers = {'content-type': 'application/json'}
    r = requests.post(
    'https://servicedeath.backendless.app/api/data/AverageArduinoCall', headers=headers, data=json.dumps(json_data)
    )


def arduinoDelete():

    headers = {'content-type': 'application/json'}

    r = requests.delete(
    'https://servicedeath.backendless.app/api/data/bulk/ArduinoCall', headers=headers

    )

@app.route("/api/iqairsend")
def sendIQAirData():

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
    'https://servicedeath.backendless.app/api/data/APICall', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"



@app.route("/api/iqairretrieve")
def createIQAirAverage():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/APICall', headers=headers
    )


    data = r.json()
    sum = 0

    for item in data:
        sum += item['aqi']
    try: 
        average = int(sum / len(data))
        print(average)
        iqAirAverage(average)
        iqAirDelete()
    
    except ZeroDivisonError:
        print()

    return "<div></div>"



@app.route("/api/arduinosend")
def sendArduinoData():

    a = request.args
    currentaqi = a["currentaqi"]
    print(type(currentaqi))

    json_data = {
      "aqi" : int(currentaqi)
    }

    headers = {'content-type': 'application/json'}

    r = requests.post(
    'https://servicedeath.backendless.app/api/data/ArduinoCall', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"


@app.route("/api/arduinoretrieve")
def createArduinoAverage():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/ArduinoCall', headers=headers
    )


    data = r.json()
    print(data)
    sum = 0

    for item in data:
        sum += item['aqi']
    
    try:
        average = int(sum / len(data))

        arduinoAverage(average)
        arduinoDelete()

    except ZeroDivisionError:
        print()
        
    return "<div></div>"
