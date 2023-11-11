#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# MIT License
#
# Copyright 2023 KrzDvt
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.#!/usr/bin/env python

#
# Dependencies
#
# pip install flask flask-httpauth
# pip install APScheduler
# pip install asyncio
# pip install renault-api
# + pyhelp's dependencies


import sys
sys.path.insert(1, '../pyhelp/')


import json
import time
import argparse
import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

import asyncio

import aiohttp
from renault_api.renault_client import RenaultClient
from renault_api.renault_account import RenaultAccount
from renault_api.renault_vehicle import RenaultVehicle

from misc import *
from mqtt import *
from httpapi import *
from devnval import *


#
# Classes
#

class Values:
  def __init__(self):
    self._updateTick:int = None
    self._sentTick:int = None

    self._device:object = None


class VehicleValues(Values):
  TAG_COCKPIT_ODO_KM:str = 'cockpitOdoKm'
  TAG_COCKPIT_TEMP_C:str = 'cockpitTempC'

  TAG_LOCATION_TSTAMP:int = 'locationTstamp'
  TAG_LOCATION:str = 'location'

  TAG_BATTERY_TEMP_C:str = 'batteryTempC'
  TAG_BATTERY_AVAIL_NRG_KWH:str = 'batteryAvailNrgKwh'
  TAG_BATTERY_LEVEL_PCT:str = 'batteryLevelPct'

  TAG_PLUGGED:str = 'plugged'
  TAG_CHARGING:str = 'charging'
  TAG_CHARGING_POWER_W:str = 'chargingPowerW'

  def __init__(self):
    self.cockpitOdoKm:float = None
    self.cockpitTempC:float = None

    self.locationTstamp:int = None
    self.location:object = None

    self.batteryTempC:float = None
    self.batteryAvailNrgKwh = None
    self.batteryLevelPct:float = None

    self.plugged:bool = None
    self.charging:bool = None
    self.chargingPowerW:int = None

  def toDict(self):
    res:dict = {}

    if self.cockpitOdoKm is not None:
      res[VehicleValues.TAG_COCKPIT_ODO_KM] = self.cockpitOdoKm
    if self.cockpitTempC is not None:
      res[VehicleValues.TAG_COCKPIT_TEMP_C] = self.cockpitTempC

    '''
    if self.location is not None:
      if self.locationTstamp is not None:
        res[VehicleValues.TAG_LOCATION_TSTAMP] = self.locationTstamp
      res[VehicleValues.TAG_LOCATION] = self.location
    elif self._evLocation is not None:
      if self._evLocationTstamp is not None:
        res[VehicleValues.TAG_LOCATION_TSTAMP] = self._evLocationTstamp
      res[VehicleValues.TAG_LOCATION] = self._evLocation
    '''

    if self.batteryTempC is not None:
      res[VehicleValues.TAG_BATTERY_TEMP_C] = self.batteryTempC
    if self.batteryAvailNrgKwh is not None:
      res[VehicleValues.TAG_BATTERY_AVAIL_NRG_KWH] = self.batteryAvailNrgKwh
    if self.batteryLevelPct is not None:
      res[VehicleValues.TAG_BATTERY_LEVEL_PCT] = self.batteryLevelPct

    if self.plugged is not None:
      res[VehicleValues.TAG_PLUGGED] = self.plugged
    if self.charging is not None:
      res[VehicleValues.TAG_CHARGING] = self.charging
    if self.chargingPowerW is not None:
      res[VehicleValues.TAG_CHARGING_POWER_W] = self.chargingPowerW

    return res


class Vehicle:
  def __init__(self, type:str, settingsDict:dict=None):
    self.type:str = type

    self.group:str = None
    self.vin:str = None
    self.manufacturer:str = None
    self.model:str = None
    self.energy:str = None
    self.registration:str = None

    self.knownValues:[str] = []
    self.newKnownValues:bool = False

    self.lastValues:VehicleValues = None

    if settingsDict is not None:
      if 'group' in settingsDict:
        self.group = settingsDict['group']
      if 'vin' in settingsDict:
        self.vin = settingsDict['vin']
      if 'manufacturer' in settingsDict:
        self.manufacturer = settingsDict['manufacturer']
      if 'model' in settingsDict:
        self.model = settingsDict['model']
      if 'energy' in settingsDict:
        self.energy = settingsDict['energy']
      if 'registration' in settingsDict:
        self.registration = settingsDict['registration']
  
    if isStringEmpty(self.manufacturer):
      self.manufacturer = self.type

  def isSet(self) -> bool :
    if isStringEmpty(self.type):
      return False
    return True

  def dispSettings(self, tab:str=''):
    print('{0}type={1}'.format(tab, self.type))
    print('{0}group={1}'.format(tab, self.group))
    print('{0}vin={1}'.format(tab, self.vin))
    print('{0}manufacturer={1}'.format(tab, self.manufacturer))
    print('{0}model={1}'.format(tab, self.model))
    print('{0}energy={1}'.format(tab, self.energy))
    print('{0}registration={1}'.format(tab, self.registration))

  def getKnownValues(self) -> [str]:
    return self.knownValues if self.knownValues is not None else []

  def areNewKnownValues(self) -> bool:
    return self.newKnownValues

  def resetNewKnownValues(self):
    self.newKnownValues = False

  def _updateKnownValues(self, knownValues:[str], tag:str, value) -> [str]:
    if value is not None and not tag in knownValues:
      knownValues.append(tag)
    return knownValues

  def setLastValues(self, values:VehicleValues):
    if values is None:
      return

    knownValues:[str] = self.knownValues if self.knownValues is not None else []
    knownValuesCount:int = len(knownValues)

    self._updateKnownValues(knownValues, VehicleValues.TAG_COCKPIT_ODO_KM, values.cockpitOdoKm)
    self._updateKnownValues(knownValues, VehicleValues.TAG_COCKPIT_TEMP_C, values.cockpitTempC)

    '''
    self._updateKnownValues(knownValues, VehicleValues.TAG_LOCATION_TSTAMP, values.locationTstamp)
    self._updateKnownValues(knownValues, VehicleValues.TAG_LOCATION, values.location)
    self._updateKnownValues(knownValues, VehicleValues.TAG_LOCATION_TSTAMP, values._evLocationTstamp)
    self._updateKnownValues(knownValues, VehicleValues.TAG_LOCATION, values._evLocation)
    '''

    self._updateKnownValues(knownValues, VehicleValues.TAG_BATTERY_TEMP_C, values.batteryTempC)
    self._updateKnownValues(knownValues, VehicleValues.TAG_BATTERY_AVAIL_NRG_KWH, values.batteryAvailNrgKwh)
    self._updateKnownValues(knownValues, VehicleValues.TAG_BATTERY_LEVEL_PCT, values.batteryLevelPct)

    self._updateKnownValues(knownValues, VehicleValues.TAG_PLUGGED, values.plugged)
    self._updateKnownValues(knownValues, VehicleValues.TAG_CHARGING, values.charging)
    self._updateKnownValues(knownValues, VehicleValues.TAG_CHARGING_POWER_W, values.chargingPowerW)

    if knownValuesCount != len(knownValues):
      self.knownValues = knownValues
      self.newKnownValues = True

    self.lastValues = values

  def resetLastValues(self):
    self.lastValues = None

  async def retrieveValues(self) -> VehicleValues:
    raise NotImplementedError("Subclasses should implement this !")


class Renault(Vehicle):
  MIN_DELAY_BETWEEN_QUERIES_s:int = 1800

  def __init__(self, settingsDict:dict=None):
    super().__init__('renault', settingsDict)

    self.username = None
    self.password = None
    self.accountId = None

    if settingsDict is not None:
      if 'username' in settingsDict:
        self.username = settingsDict['username']
      if 'password' in settingsDict:
        self.password = settingsDict['password']
      if 'accountId' in settingsDict:
        self.accountId = settingsDict['accountId']

  def isSet(self) -> bool :
    if not super().isSet():
      return False
    if isStringEmpty(self.username):
      return False
    if isStringEmpty(self.password):
      return False
    return True

  def dispSettings(self, tab:str=''):
    super().dispSettings(tab)
    print('{0}username={1}'.format(tab, self.username))
    print('{0}password={1}'.format(tab, '***' if not isStringEmpty(self.password) else ''))
    print('{0}accountId={1}'.format(tab, '***' if not isStringEmpty(self.accountId) else ''))

  async def retrieveValues(self) -> VehicleValues:
    curTick:int = int(time.time())

    lastValues:VehicleValues = self.lastValues

    if lastValues is not None and \
       lastValues._updateTick is not None and \
       ( lastValues._updateTick + Renault.MIN_DELAY_BETWEEN_QUERIES_s ) > curTick:
      return lastValues

    websession: aiohttp.ClientSession = None

    try:
      vehicle: RenaultVehicle = None

      lastValues = VehicleValues()
      lastValues._updateTick = int(time.time())
      lastValues._sentTick = None
      lastValues._device = self

      websession = aiohttp.ClientSession()
      client: RenaultClient = RenaultClient(websession=websession, locale="fr_FR")
      await client.session.login(self.username, self.password)

      if not isStringEmpty(self.accountId):
        account: RenaultAccount = await client.get_api_account(self.accountId)

        if not isStringEmpty(self.vin):
          vehicle = await account.get_api_vehicle(self.vin)

          if isStringEmpty(self.manufacturer) or \
             isStringEmpty(self.model) or \
             isStringEmpty(self.energy) or \
             isStringEmpty(self.registration):
            details = await vehicle.get_details()
            if details.brand is not None and not isStringEmpty(details.brand.label):
              self.manufacturer = details.brand.label
            if details.model is not None and not isStringEmpty(details.model.label):
              self.model = details.model.label
            if details.energy is not None and not isStringEmpty(details.energy.label):
              self.energy = details.energy.label
            if details.registrationNumber is not None:
              self.registration = details.registrationNumber

          try:
            cockpit = await vehicle.get_cockpit()
            if cockpit.totalMileage is not None:
              lastValues.cockpitOdoKm = cockpit.totalMileage
          except Exception as excp:
            pass

          try:
            batteryStatus = await vehicle.get_battery_status()
            if batteryStatus.batteryTemperature:
              lastValues.batteryTempC = batteryStatus.batteryTemperature
            #if batteryStatus.batteryAvailableEnergy is not None:
            #  lastValues.batteryAvailNrgKwh = batteryStatus.batteryAvailableEnergy
            if batteryStatus.batteryLevel is not None:
              lastValues.batteryLevelPct = batteryStatus.batteryLevel
            if batteryStatus.plugStatus != None:
              lastValues.plugged = ( batteryStatus.plugStatus != 0 )
            if batteryStatus.chargingStatus != None:
              lastValues.charging = ( batteryStatus.chargingStatus != 0.0 )
            if batteryStatus.chargingInstantaneousPower is not None:
              lastValues.chargingPowerW = batteryStatus.chargingInstantaneousPower
          except Exception as excp:
            pass

          try:
            location = await vehicle.get_location()
            if location.gpsLatitude is not None and location.gpsLongitude is not None:
              lastValues._evLocationTstamp = ( int ) (datetime.datetime.strptime(location.lastUpdateTime, '%Y-%m-%dT%H:%M:%SZ').timestamp() * 1000)
              lastValues._evLocation = { 'latitude':location.gpsLatitude, 'longitude':location.gpsLongitude, 'gps_accuracy': 1 }
          except Exception as excp:
            pass
        else:
          print(f"Vehicles: {await account.get_vehicles()}") # List available vehicles, make a note of vehicle VIN
      else:
        print(f"RenaultPerson: {await client.get_person()}") # List available accounts, make a note of kamereon account id

      self.setLastValues(lastValues)
    except Exception as excp:
      pass
    finally:
      try:
        await websession.close()
      except Exception as excp:
        pass

    return self.lastValues

class Settings:
  def __init__(self, settingsDict:dict=None):
    self.group:str = None
    self.vehicles:[Vehicle] = []
    self.mqtts:list[MqttSettings] = []
    self.httpApi:[HttpApi] = None

    self.loop = True

    if settingsDict is not None:
      if 'group' in settingsDict:
        self.group = settingsDict['group'] 
      if 'loop' in settingsDict:
        self.loop = settingsDict['loop']
      if 'vehicles' in settingsDict:
        for vehicleDict in settingsDict['vehicles']:
          if not 'type' in vehicleDict:
            continue
          if not 'group' in vehicleDict and not isStringEmpty(self.group):
            vehicleDict['group'] = self.group
          if vehicleDict['type'] == 'renault':
            self.vehicles.append(Renault(vehicleDict))
      if 'mqtts' in settingsDict:
        for mqttDict in settingsDict['mqtts']:
          self.mqtts.append(MqttSettings(mqttDict))
      if 'httpApi' in settingsDict:
        self.httpApi = HttpApiSettings(settingsDict['httpApi'])
      elif 'httpapi' in settingsDict:
        self.httpApi = HttpApiSettings(settingsDict['httpapi'])

  def isSet(self) -> bool:
    # device is mandatory
    if self.vehicles is not None and len(self.vehicles) > 0:
      for vehicle in self.vehicles:
        if not vehicle.isSet():
          print('settings : vehicle not set')
          return False

    # mqtts is optional
    if self.mqtts is not None and len(self.mqtts) > 0:
      for mqtt in self.mqtts:
        if not mqtt.isSet():
          print('settings : mqtt not set')
          return False

    return True


#
#  Process methods
#

def readSettings(filePath:str) -> Settings:
  try:
    file = None
    fileDict = None
    with open(filePath, 'r') as file:
      fileDict = json.load(file)
    return Settings(fileDict)
  except Exception as excp:
    print('Failed reading settings file : ' + str(excp))
    return None

def dispSettings(settings:Settings):
  if settings.vehicles is not None:
    print('  vehicles')
    for vehicle in settings.vehicles:
      print('    vehicle')
      vehicle.dispSettings('      ')

  if settings.mqtts is not None:
    print('  mqtts')
    for mqtt in settings.mqtts:
      print('    mqtt')
      print('      hostname={0}'.format(mqtt.hostname))
      print('      port={0}'.format(mqtt.port))
      print('      clientId={0}'.format(mqtt.clientId))
      print('      username={0}'.format(mqtt.username))
      print('      password={0}'.format('***' if mqtt.password is not None and len(mqtt.password.strip()) > 0 else ''))
      print('      isHA={0}'.format(mqtt.isHA))

  if settings.httpApi is not None:
    print('  httpApi')
    dispHttpApiSettings(settings.httpApi, '    ')

def vehicle2DeviceSettings(vehicle:Vehicle) -> DeviceSettings:
  deviceSettings:DeviceSettings = DeviceSettings()
  deviceSettings.group = vehicle.group
  if isStringEmpty(deviceSettings.group):
    deviceSettings.group = 'vtrack'
  deviceSettings.serial = vehicle.vin
  deviceSettings.manufacturer = vehicle.manufacturer
  deviceSettings.model = vehicle.model
  deviceSettings.name = vehicle.registration
  deviceSettings.version = vehicle.energy
  return deviceSettings

def vehicle2DeclareValues(vehicle:Vehicle) -> [DeclareValue]:
  if not vehicle.areNewKnownValues():
    return None

  declareValues:[DeclareValue] = []

  for knownValue in vehicle.knownValues:
    if knownValue == VehicleValues.TAG_COCKPIT_ODO_KM:
      declareValues.append(DeclareValue(name='cockpit odometer', unit='km', tag=knownValue, icon='mdi:counter', withAttrs=True))
    elif knownValue == VehicleValues.TAG_COCKPIT_TEMP_C:
      declareValues.append(DeclareValue(name='cockpit temperature', unit='°C', tag=knownValue))
    elif knownValue == VehicleValues.TAG_BATTERY_TEMP_C:
      declareValues.append(DeclareValue(name='battery temperature', unit='°C', tag=knownValue))
    elif knownValue == VehicleValues.TAG_BATTERY_LEVEL_PCT:
      declareValues.append(DeclareValue(name='battery level', unit='%', tag=knownValue, icon='mdi:battery'))
    elif knownValue == VehicleValues.TAG_PLUGGED:
      declareValues.append(DeclareValue(name='plugged', unit='', tag=knownValue, type='binary_sensor', icon='mdi:ev-plug-type2'))
    elif knownValue == VehicleValues.TAG_CHARGING:
      declareValues.append(DeclareValue(name='charging', unit='', tag=knownValue, type='binary_sensor', icon='mdi:battery-charging'))
    elif knownValue == VehicleValues.TAG_CHARGING_POWER_W:
      declareValues.append(DeclareValue(name='charging power', unit='W', tag=knownValue))
    '''
    elif knownValue == VehicleValues.TAG_LOCATION_TSTAMP:
      pass
    elif knownValue == VehicleValues.TAG_LOCATION:
      declareValues.append(DeclareValue(name='location', unit='', tag=knownValue, type='device_tracker'))
    '''

  return declareValues

async def readValues(settings:Settings) -> dict[str, Values]:
  if settings.vehicles is None or len(settings.vehicles) <= 0:
    return None

  vehicleKey:str = None
  vehiclesValues:dict = dict()
  vehicleValues:VehicleValues = None
  for vehicle in settings.vehicles:
    if not isStringEmpty(vehicle.vin):
      vehicleKey = vehicle.vin
    else:
      vehicleKey = None
    if not isStringEmpty(vehicleKey):
      vehicleValues = await vehicle.retrieveValues()
      if vehicleValues is not None:
        vehiclesValues[vehicle.vin] = vehicleValues

  return vehiclesValues

def dispValues(values:Values):
  pass

def declareValues(settings:Settings) -> bool:
  if settings.vehicles is None or len(settings.vehicles) <= 0:
    return False

  sentCount:int = 0

  if settings.mqtts is not None and len(settings.mqtts) > 0:
    declareValues:[DeclareValue]

    for mqtt in settings.mqtts:
      for vehicle in settings.vehicles:
        declareValues = vehicle2DeclareValues(vehicle)
        if declareValues is not None and len(declareValues) > 0:
          if declareValues2Mqtt(vehicle2DeviceSettings(vehicle), mqtt, declareValues):
            vehicle.resetNewKnownValues()
            sentCount += 1

  if sentCount > 0:
    time.sleep(5)

  return True

def sendValues(values:dict[str, Values], settings:Settings) -> int:
  sentCount:int = 0
  if settings.mqtts and len(settings.mqtts) > 0:
    sendCount:int = 0

    for mqtt in settings.mqtts:
      for key in values:
        deviceValues = values[key]
        if deviceValues is not None and \
           deviceValues._device is not None and \
           deviceValues._updateTick is not None:
          if deviceValues._sentTick is None or deviceValues._updateTick > deviceValues._sentTick:
            sendCount += 1
            if type(deviceValues) == VehicleValues:
              if sendValues2Mqtt(deviceValues, vehicle2DeviceSettings(deviceValues._device), mqtt):
                deviceValues._sentTick = int(time.time())
                sentCount += 1

    if sentCount > 0:
      time.sleep(5)
    sentCount = sentCount * 100 / sendCount if sendCount > 0 else 100
  else:
    sentCount = 100
  return sentCount

async def readAndSendValues(settings:Settings):
  global inProgress

  if inProgress:
    return

  try:
    inProgress = True
    values:dict[str, Values] = await readValues(settings)
    if declareValues(settings):
      sentPct:int = sendValues(values, settings)
      if sentPct < 100:
        print('Values sent to only {0}% of destination(s)'.format(sentPct))
    else:
        print('Values not declared correclty')
  except Exception as excp:
    pass
  finally:
    inProgress = False

def readAndSendValuesBlocking():
  global settings
  asyncio.run(readAndSendValues(settings))

async def readAndDisplayValues(settings:Settings):
  global inProgress

  if inProgress:
    return

  try:
    inProgress = True
    values:Values = await readValues(settings)
    dispValues(values)
  except:
    pass
  finally:
    inProgress = False

def readAndDisplayValuesBlocking():
  global settings
  asyncio.run(readAndDisplayValues(settings))


#
# Main (sort of)
#

argParser = argparse.ArgumentParser(prog='vtrack', description='Vehicle Tracker')
argParser.add_argument('-s', '--set', default='vtrack.conf', help='settings file path')
argParser.add_argument('-v', '--vehicle', default='', help='vehicle type')
argParser.add_argument('-u', '--username', default='', help='username')
argParser.add_argument('-p', '--password', default='', help='password')
argParser.add_argument('-aid', '--accountId', default='', help='accountId')
argParser.add_argument('-ghaph', '--genHttpApiPasswordHash', default='', help='')
args = argParser.parse_args()

if not isStringEmpty(args.genHttpApiPasswordHash):
  print(generatePasswordHash(args.genHttpApiPasswordHash))
  exit()

inProgress:bool = False
settings:Settings = None
  
if not isStringEmpty(args.vehicle) and not isStringEmpty(args.username) and not isStringEmpty(args.password):
    vehicleSettingsDict:dict = { 'type':args.vehicle, 'username':args.username, 'password':args.password }
    if not isStringEmpty(args.accountId):
      vehicleSettingsDict['accountId'] = args.accountId
    settingsDict:dict = { 'vehicles': [ vehicleSettingsDict ] }
    settings = Settings(settingsDict)

if settings is None:
  settings = readSettings(args.set if not isStringEmpty(args.set) else 'vtrack.conf')

if settings is not None and settings.isSet():
  print('Loop with settings')
  dispSettings(settings)

  sched:BackgroundScheduler = BackgroundScheduler(daemon=True)
  sched.add_job(readAndSendValuesBlocking,'interval',seconds=10)
  sched.start()

  if settings.httpApi is not None:
    apiRefreshTstamp:int = None
    flask, flaskAuth = buildHttpApi(__name__, settings.httpApi)

    @flask.route("/api/values", methods = ['GET'])
    @flaskAuth.login_required
    def values():
      lastValues:VehicleValues = None
      allLastValues:dict[str, VehicleValues] = {}
      for vehicle in settings.vehicles:
        if not isStringEmpty(vehicle.registration):
          lastValues = vehicle.lastValues
          if lastValues is not None:
            allLastValues[vehicle.registration] = lastValues.toDict()
      return allLastValues, 200, {'Content-Type': 'application/json; charset=utf-8'}

    @flask.route("/api/refresh", methods = ['POST'])
    @flaskAuth.login_required
    def apiRefresh():
      global apiRefreshTstamp
      if apiRefreshTstamp is not None and ( time.time() - apiRefreshTstamp ) < 30:
        return "", 409
      apiRefreshTstamp = time.time()
      for vehicle in settings.vehicles:
        vehicle.resetLastValues()
      return ""

    runHttpApi(flask, settings.httpApi)
  else:
    while True:
      time.sleep(5)
elif settings is None:
  print('No settings found')
else:
  print('Bad settings found')