import json
import time
import logging
import requests
import boto3
import datetime
import math


logger = logging.getLogger()
logger.setLevel(logging.INFO)

PAUSE = 1 #second
RETRIES = 5

class Strava:
    
    VERBTONOUN = { "VirtualRun": "virtual run",
               "Run": "run",
               "VirtualRide": "virtual ride",
               "Ride": "ride",
               "Rowing": "row",
               "Walk": "walk"
             }
    
    def __init__(self,auth,stravaClientId: str, stravaClientSecret: str,ddbTableName: str, athleteId = None):
        self.stravaClientId = stravaClientId
        self.stravaClientSecret = stravaClientSecret
        self.ddbTableName = ddbTableName
        if isinstance(auth,dict):
            self.athleteId = athleteId
            self.tokens = auth
        elif isinstance(auth,str):
            self._newAthlete(auth) 
    

    def _newAthlete(self,code):
        data = {
            'client_id': self.stravaClientId,
            'client_secret': self.stravaClientSecret,
            'code': code,
            'grant_type': "authorization_code"
        }
        response = requests.post("https://www.strava.com/oauth/token", json=data)
        if response.status_code == 200:
            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(self.ddbTableName)
            self.tokens = response.json()
            self.athleteId = response.json()['athlete']['id']
            logger.info("Checking to see if the athlete is already registered")
            athelete_record = table.get_item(Key={'Id': self.athleteId})
            if 'Item' not in athelete_record:
                # Get any existing data for runs, rides or swims they may have done, and add these as the starting status for the body element
                logger.info("Net new athelete. Welcome!")
                body_as_string="{}"
                try:
                    current_year = str(datetime.datetime.now().year)
                    data_to_add = {}
                    athelete_detail_json = self.getAthlete(self.athleteId)
                    if athelete_detail_json['ytd_ride_totals']['count']>0:
                        data_to_add['Ride']={"distance":athelete_detail_json['ytd_ride_totals']['distance'],"duration":athelete_detail_json['ytd_ride_totals']['elapsed_time'],"count":athelete_detail_json['ytd_ride_totals']['count']}
                    if athelete_detail_json['ytd_run_totals']['count']>0:
                        data_to_add['Run']={"distance":athelete_detail_json['ytd_run_totals']['distance'],"duration":athelete_detail_json['ytd_run_totals']['elapsed_time'],"count":athelete_detail_json['ytd_run_totals']['count']}
                    if athelete_detail_json['ytd_swim_totals']['count']>0:
                        data_to_add['Swim']={"distance":athelete_detail_json['ytd_swim_totals']['distance'],"duration":athelete_detail_json['ytd_swim_totals']['elapsed_time'],"count":athelete_detail_json['ytd_swim_totals']['count']}
                    if len(data_to_add)>0:
                        body_as_string=json.dumps({current_year:data_to_add})
                except Exception as e:
                    logger.error("Failed to collect details about the athletes previous activity. Sorry")
                    logger.error(e)
                table.put_item(
                    Item={
                      'Id': self.athleteId,
                      'body': body_as_string
                    })
            self._writeTokens(self.tokens)
        else:
            logger.error("Failed to get OAuth tokens")
            logger.error("{} - {}".format(response.status_code, response.content))
            exit()
        
    def refreshTokens(self):
        if int(time.time()) > int(self.tokens['expires_at']):
            logger.info("Need to refresh Strava Tokens")
            data = {
                'client_id': self.stravaClientId,
                'client_secret': self.stravaClientSecret,
                'grant_type': "refresh_token",
                'refresh_token': self.tokens['refresh_token']
            }
            
            response = requests.post("https://www.strava.com/oauth/token", json=data)
            
            if response.status_code == 200:
                
                logger.info("Got new Strava tokens")
                
                self._writeTokens(response.json())
                
            else:
                logger.error("Failed to get refreshed tokens")
                logger.error(response.raw)
                exit()
                
    def _writeTokens(self,tokens):
        logger.info("Writing strava tokens to DDB")
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(self.ddbTableName)
        
        self.tokens = {"expires_at":tokens['expires_at'],"access_token":tokens['access_token'],"refresh_token":tokens['refresh_token']}

        table.update_item(
            Key={
                'Id': str(self.athleteId)
            },
            UpdateExpression="set tokens=:c",
            ExpressionAttributeValues={
                ':c': json.dumps(self.tokens)
            }
        )
        
    def makeTwitterString(self,athlete_stats: dict,latest_event: dict):
        
        ytd = athlete_stats[str(datetime.datetime.now().year)][latest_event['type']]
        
        ## Convert activity verb to a noun
        activity_type = latest_event['type']
        if activity_type in self.VERBTONOUN:
            activity_type =  self.VERBTONOUN[activity_type]
        strava_athlete = self.getCurrentAthlete()
        
        status = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s: {TOTALDISTANCEMILES:0.2f}miles ({TOTALDISTANCEKM:0.2f}km) in {TOTALDURATION}".format(
            FIRSTNAME=strava_athlete['firstname'],
            LASTNAME=strava_athlete['lastname'],
            TYPE=activity_type,
            DISTANCEMILES=latest_event['distance']/1609,
            DISTANCEKM=latest_event['distance']/1000,
            DURATION=self.secsToStr(latest_event['elapsed_time']),
            TOTALDISTANCEMILES=ytd['distance']/1609,
            TOTALDISTANCEKM=ytd['distance']/1000,
            TOTALDURATION=self.secsToStr(ytd['duration']),
            TOTALCOUNT=ytd['count'],
            ACTIVITYURL="https://www.strava.com/activities/{}".format(latest_event['id']))
        if "device_name" in latest_event:
            if latest_event['device_name'] == 'Zwift':
                status += " #RideOn #Zwift"
        return status
    
    def secsToStr(self,seconds):
        if seconds > 86400:
            return "{} day(s) {}".format(math.floor(seconds/86400),time.strftime("%Hh %Mm %Ss", time.gmtime(seconds)))
        elif seconds > 3600:
            return time.strftime("%Hhr %Mmins %Sseconds", time.gmtime(seconds))
        else:
            return time.strftime("%M minutes and %S seconds", time.gmtime(seconds))

                
    def _get(self,endpoint):
        while True:
            counter = 0
            try:
                self.refreshTokens()
                activity = requests.get(
                    endpoint,
                    headers={'Authorization':"Bearer {ACCESS_TOKEN}".format(ACCESS_TOKEN=self.tokens['access_token'])}
                    )
                if activity.status_code == 200:
                    return activity.json()
                elif counter == RETRIES:
                    logger.error("Get failed even after retries")
                    logger.error("{} - {}".format(activity.status_code,activity.content))
                    exit()
                else:
                    counter+=1
                    time.sleep(PAUSE)
            except Exception as e:
                logger.error("An Exception occured while getting {} ".format(endpoint))
                logger.error(e)
                exit()
                
    def getActivity(self,activityId):
        endpoint = "https://www.strava.com/api/v3/activities/{ID}".format(ID=activityId)
        return(self._get(endpoint))
        
    def getCurrentAthlete(self):
        endpoint = "https://www.strava.com/api/v3/athlete"
        return(self._get(endpoint))
        
    def getAthlete(self,athleteId):
        endpoint = "https://www.strava.com/api/v3/athletes/{ID}/stats".format(ID=athleteId)
        return(self._get(endpoint))
        