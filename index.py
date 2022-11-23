
from flask import Flask, request
import requests, json

app = Flask(__name__)

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


@app.route("/api/outdoorretrieve")
def createOutdoorAverage():

    headers = {'content-type': 'application/json'}

    r = requests.get(
    'https://servicedeath.backendless.app/api/data/OutdoorData', headers=headers
    )

    data = r.json()
    sum = 0

    for item in data:
        sum += item['aqi']

    average = int(sum / len(data))
    print(average)
    outdoorAverage(average)
    outdoorDelete()

    return "<div></div>"


@app.route("/api/indoorsend")
def sendIndoorData():

    a = request.args
    currentaqi = a["currentaqi"]
    print(type(currentaqi))

    json_data = {
      "aqi" : int(currentaqi)
    }

    headers = {'content-type': 'application/json'}

    r = requests.post(
    'https://servicedeath.backendless.app/api/data/IndoorData', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"


@app.route("/api/indoorretrieve")
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

    average = int(sum / len(data))

    indoorAverage(average)
    indoorDelete()

    return "<div></div>"


# ping ur/ with all the things as query parameters
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
        "firstName" : firstname,
        "lastName" : lastname,
        "password" : password,
        "username" : username,
        "phone" : phone
    }

    headers = {'content-type': 'application/json'}

    r = request.post(
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

    r = request.post(
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

    r = request.post(
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

    r = request.post(
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

    r = request.post(
    'XXXXXXXXXXXXXX', headers=headers, data=json.dumps(json_data)
    )

    return "<div></div>"
