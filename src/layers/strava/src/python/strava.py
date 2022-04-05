import json
import time
import logging
import requests
import boto3
import datetime
import math


logger = logging.getLogger()
logging.basicConfig(level=logging.DEBUG, format='%(message)s')

PAUSE = 1 #second
RETRIES = 5

class Strava:
    STRAVA_API_URL = "https://www.strava.com/api/v3"
    STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
    VERBTONOUN = { "VirtualRun": "virtual run",
               "Run": "run",
               "VirtualRide": "virtual ride",
               "Ride": "ride",
               "Rowing": "row",
               "Walk": "walk"
             }
    
    def __init__(self,stravaClientId: str, stravaClientSecret: str,ddbTableName: str, athleteId: int = None, auth:str = None):
        self.stravaClientId = stravaClientId
        self.stravaClientSecret = stravaClientSecret
        self.ddbTableName = ddbTableName
        if auth is not None:
            self._newAthlete(auth)
        elif athleteId is not None:
            self.athleteId = athleteId
            self.tokens = json.loads(self._getAthleteFromDDB()['tokens'])
    
    def _newAthlete(self,code):
        new_tokens = self._getTokensWithCode(code)
        if new_tokens is not None:
            
            self.tokens = new_tokens
            self.athleteId = new_tokens['athlete']['id']
            logger.info("Checking to see if the athlete is already registered")
            athlete_record = self._getAthleteFromDDB()
            if athlete_record is None:
                # Get any existing data for runs, rides or swims they may have done, and add these as the starting status for the body element
                logger.info("Net new athlete. Welcome!")
                body_as_string="{}"
                try:
                    current_year = str(datetime.datetime.now().year)
                    data_to_add = {}
                    athlete_detail_json = self.getAthlete(self.athleteId)
                    if athlete_detail_json['ytd_ride_totals']['count']>0:
                        data_to_add['Ride']={"distance":athlete_detail_json['ytd_ride_totals']['distance'],"duration":athlete_detail_json['ytd_ride_totals']['elapsed_time'],"count":athlete_detail_json['ytd_ride_totals']['count']}
                    if athlete_detail_json['ytd_run_totals']['count']>0:
                        data_to_add['Run']={"distance":athlete_detail_json['ytd_run_totals']['distance'],"duration":athlete_detail_json['ytd_run_totals']['elapsed_time'],"count":athlete_detail_json['ytd_run_totals']['count']}
                    if athlete_detail_json['ytd_swim_totals']['count']>0:
                        data_to_add['Swim']={"distance":athlete_detail_json['ytd_swim_totals']['distance'],"duration":athlete_detail_json['ytd_swim_totals']['elapsed_time'],"count":athlete_detail_json['ytd_swim_totals']['count']}
                    if len(data_to_add)>0:
                        body_as_string=json.dumps({current_year:data_to_add})
                except Exception as e:
                    logger.error("Failed to collect details about the athletes previous activity. Sorry")
                    logger.error(e)
                self._putAthleteToDB(body_as_string)
            self._writeTokens(self.tokens)
        else:
            exit()
        
    def refreshTokens(self):
        logger.debug("We should already have some tokens. Check if we need to refresh.")
        logger.debug(self.tokens)
        if int(time.time()) > int(self.tokens['expires_at']):
            logger.info("Need to refresh Strava Tokens")
            new_tokens = self._getTokensWithRefresh()
            logger.info("Got new Strava tokens")
            logger.debug(new_tokens)
            self._writeTokens(new_tokens)

                
    def _writeTokens(self,tokens):
        logger.info("Writing strava tokens to DDB")

        table = self._getDDBTable()
        logger.debug("Building token dict for storage")
        self.tokens = {"expires_at":tokens['expires_at'],"access_token":tokens['access_token'],"refresh_token":tokens['refresh_token']}
        logger.debug("Writing token dict to DB")
        table.update_item(
            Key={
                'Id': str(self.athleteId)
            },
            UpdateExpression="set tokens=:c",
            ExpressionAttributeValues={
                ':c': json.dumps(self.tokens)
            }
        )
        logger.debug("New tokens written")
    
    def _getAthleteFromDDB(self):
        logger.info("Getting athlete from DDB")
        table = self._getDDBTable()
        athlete_record = table.get_item(Key={'Id': str(self.athleteId)})
        if "Item" in athlete_record:
            return athlete_record['Item']
        logger.info("No athlete found")
        return None
    
    def _putAthleteToDB(self,body_as_string="{}"):
        logger.info("Writing basic athlete to DDB")
        table = self._getDDBTable()
        table.put_item(
            Item={
              'Id': str(self.athleteId),
              'body': body_as_string
            })
            
    def _updateAthleteOnDB(self,body_as_string: str):
        logger.info("Updating athlete on DDB")
        table = self._getDDBTable()
        table.update_item(
        Key={
                'Id': str(self.athleteId)
            },
            UpdateExpression="set body=:c",
            ExpressionAttributeValues={
                ':c': body_as_string
            }
        )
    
    def updateLastActivity(self, activityId):
        logger.info("Updating athlete on DDB")
        table = self._getDDBTable()
        table.update_item(
            Key={
                'Id': str(self.athleteId)
            },
            UpdateExpression="set last_activity_id=:c",
            ExpressionAttributeValues={
                ':c': activityId
            }
        )
    
    def _getTokensWithCode(self,code):
        data = {
            'client_id': self.stravaClientId,
            'client_secret': self.stravaClientSecret,
            'code': code,
            'grant_type': "authorization_code"
        }
        response = requests.post(self.STRAVA_TOKEN_URL, json=data)
        if response.status_code == 200:
            return response.json()
        logger.error("Failed to get OAuth tokens")
        logger.error("{} - {}".format(response.status_code, response.content))
        return None
        
    def _getTokensWithRefresh(self):
        data = {
            'client_id': self.stravaClientId,
            'client_secret': self.stravaClientSecret,
            'grant_type': "refresh_token",
            'refresh_token': self.tokens['refresh_token']
        }
        
        response = requests.post(self.STRAVA_TOKEN_URL, json=data)
        if response.status_code == 200:
            return response.json()
        logger.error("Failed to get refreshed tokens")
        logger.error(response.raw)
        exit()
        return None
    
    def _getDDBTable(self):
        try:
            return self.ddbTable
        except AttributeError:
            self.dynamodb = boto3.resource('dynamodb')
            self.ddbTable = self.dynamodb.Table(self.ddbTableName)
            return self.ddbTable
    
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
                logger.debug("Checking if tokens need a refresh")
                self.refreshTokens()
                logger.debug("Sending GET request to strava endpoint")
                logger.debug(self.tokens['access_token'])
                activity = requests.get(
                    endpoint,
                    headers={'Authorization':"Bearer {ACCESS_TOKEN}".format(ACCESS_TOKEN=self.tokens['access_token'])}
                    )
                if activity.status_code == 200:
                    logger.debug("All good. Returning.")
                    return activity.json()
                elif counter == RETRIES:
                    logger.error("Get failed even after retries")
                    logger.error("{} - {}".format(activity.status_code,activity.content))
                    exit()
                else:
                    logger.debug("Failed, but going to retry.")
                    counter+=1
                    time.sleep(PAUSE)
            except Exception as e:
                logger.error("An Exception occured while getting {} ".format(endpoint))
                logger.error(e)
                exit()
                
    def getActivity(self,activityId):
        endpoint = "{STRAVA}/activities/{ID}".format(STRAVA=self.STRAVA_API_URL,ID=activityId)
        return(self._get(endpoint))
        
    def getCurrentAthlete(self):
        endpoint = "{STRAVA}/athlete".format(STRAVA=self.STRAVA_API_URL)
        return(self._get(endpoint))
        
    def getAthlete(self,athleteId):
        endpoint = "{STRAVA}/athletes/{ID}/stats".format(STRAVA=self.STRAVA_API_URL,ID=athleteId)
        return(self._get(endpoint))
        