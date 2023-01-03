import json
import time
import logging
import requests
import boto3
import datetime
import math
import os


logger = logging.getLogger()
logging.basicConfig(level=logging.DEBUG, format='%(message)s')

PAUSE = 1 #second
RETRIES = 5

ssm = boto3.client("ssm")

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
    
    def __init__(self, athleteId: int = None, auth:str = None):
        
        self.stravaClientId=self._getSSM("StravaClientId")
        self.stravaClientSecret=self._getSSM("StravaClientSecret")
        self.ddbTableName=self._getEnv("totalsTable")
        self.ddbDetailTableName=self._getEnv("detailsTable")
        
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
                current_year = str(datetime.datetime.now().year)
                start_epoch = datetime.datetime(current_year,1,1,0,0).timestamp()
                page = 1
                PER_PAGE = 30
                content = {}
                while True:
                    activities = self._get(endpoint = "{STRAVA}/activities?after={EPOCH}&page={PAGE}&per_page={PER_PAGE}".format(STRAVA=self.STRAVA_API_URL,EPOCH=start_epoch,PAGE=page,PER_PAGE=PER_PAGE))
                    ## Add all activities to the details table
                    for activity in activities:
                        activity['type'] = activity['type'].replace("Virtual","")
                        try:
                            # if the activity is alread in the DDB, this will excpetion
                            self.putDetailActivity(activity)
                        except Exception as e:
                            logger.error("Failed to add activity {ID}; trying to continue. This event will not be added to the totals.".format(ID=activity['id']))
                        else:
                            content=self.updateContent(
                                    content=content,
                                    activityType=activity['type'],
                                    distance=activity['distance'], 
                                    duration=activity['elapsed_time']
                                    )
                    ## Write what we have to the DDB table
                    if page == 1:
                        self._putAthleteToDB(json.dumps(content))
                    else:
                        self._updateAthleteOnDB(json.dumps(content))
                    ## Are there more activities?
                    if len(activities) < PER_PAGE:
                        break
                    page+=1
                        
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
        logger.info("Updating athlete body on DDB")
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
        logger.info("Updating athlete last activity on DDB")
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
    
    def _getDDBDetailTable(self):
        try:
            return self.ddbDetailTable
        except AttributeError:
            self.dynamodb = boto3.resource('dynamodb')
            self.ddbDetailTable = self.dynamodb.Table(self.ddbDetailTableName)
            return self.ddbDetailTable
            
    def putDetailActivity(self,activity):
        table = self._getDDBDetailTable()
        table.put_item(
            Item={
              'id': str(activity['id']),
              'body': json.dumps(activity)
            })
            
    def updateContent(self, content, activityType, distance, duration):
        year = str(datetime.datetime.now().year)
        logging.info(content)
        logging.info(year)
        if year in content:
            logging.info("Found year")
            if activityType in content[year]:
                logging.info("Found activity")
                content[year][activityType]['distance']=content[year][activityType]['distance']+int(distance)
                content[year][activityType]['duration']=content[year][activityType]['duration']+int(duration)
                content[year][activityType]['count']+=1
            else:
                logging.info("New activity for the year")
                content[year][activityType] = {
                  "distance":distance,
                  "duration":duration,
                  "count":1
                }
        else:
            logging.info("New year!")
            content[year]={
                activityType:{
                    "distance":distance,
                    "duration":duration,
                    "count":1
                }
            }
        return content
    
    def makeTwitterString(self,athlete_year_stats: dict,latest_event: dict):
        
        ytd = athlete_year_stats[latest_event['type']]
        
        logger.info("Latest Event = ")
        logger.info(latest_event)
        
        ## Convert activity verb to a noun
        activity_type = latest_event['type']
        if activity_type in self.VERBTONOUN:
            activity_type =  self.VERBTONOUN[activity_type]
        strava_athlete = self.getCurrentAthlete()
        latest_activity_mph = float('{:.1f}'.format((latest_event['distance']/160900)/(latest_event['elapsed_time']/3600)))
        ytd_activity_mph = float('{:.1f}'.format(((ytd['distance']-latest_event['distance'])/160900)/((ytd['duration']-latest_event['elapsed_time'])/3600)))
        
        duration_sum =0
        distance_sum =0
        count_sum=0
        for activity_key, activity in athlete_year_stats.items():
            duration_sum+=activity['duration']
            distance_sum+=activity['distance']
            count_sum+=activity['count']
        
        status_template = None
        
        ## COMMON MILESTONES
        if math.floor(distance_sum/100000) != math.floor((distance_sum-latest_event['distance'])/100000):
            # If the most recent activity puts the sum of all the activities in that category for the year over a 100km stone
            status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for all {ALLACTIVITYCOUNT} activities {ALLACTIVITYDISTANCEKM:0.2f}km #SelfPropelledKilos"
        if math.floor(distance_sum/160900) != math.floor((distance_sum-latest_event['distance'])/160900):
            # If the most recent activity puts the sum of all the activities in that category for the year over a 100mile stone
            status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for all {ALLACTIVITYCOUNT} activities {ALLACTIVITYDISTANCEMILES:0.2f}km #SelfPropelledMiles"
        if math.floor(duration_sum/86400) != math.floor((duration_sum-latest_event['elapsed_time'])/86400):
            # If the most recent activity puts the sum of all the activities' duration in that category for the year over a 1day stone
            if activity_type == self.VERBTONOUN['Ride']:
                status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for all {ALLACTIVITYCOUNT} {TYPE}s is {ALLACTIVITYDURATION} #SaddleSoreDays"
            elif activity_type == self.VERBTONOUN['Run']:
                status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for all {ALLACTIVITYCOUNT} {TYPE}s {ALLACTIVITYDURATION} #RunningDaze"
            else:
                status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for all {ALLACTIVITYCOUNT} {TYPE}s {ALLACTIVITYDURATION} #Another24h"
        if count_sum%100 ==0:
            # If this is their n00th activity in this category this year 
            status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nThat's {ALLACTIVITYCOUNT} total activities in this year. #ActiveAllTheTime"
        if math.floor(ytd['distance']/100000) != math.floor((ytd['distance']-latest_event['distance'])/100000):
            # If the total distance for all activities this year has just gone over a 100km stone
            status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEKM:0.2f}km in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s {TOTALDISTANCEKM:0.2f}km #KiloWhat"
        if math.floor(ytd['distance']/160900) != math.floor((ytd['distance']-latest_event['distance'])/160900):
            # If the total distance for all activities this year has just gone over a 100mile stone
            status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s {TOTALDISTANCEMILES:0.2f}miles #MilesAndMiles"
        if math.floor(ytd['duration']/86400) != math.floor((ytd['duration']-latest_event['elapsed_time'])/86400):
            # If the total duration for all activities this year has just gone over a 1day stone
            status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s {TOTALDURATION} #AnotherDay"
        if ytd['count'] == 1 or ytd['count']%10 == 0:
            # If they've just done their first activity for the year, or a multiple of 10 activities for the entire year
            status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s: {TOTALDISTANCEMILES:0.2f}miles ({TOTALDISTANCEKM:0.2f}km) in {TOTALDURATION} #Another10"
        if latest_activity_mph > ytd_activity_mph*1.05:
            # If they were more than 5% faster than the year average for this activity
            status_template = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} at ({ACTIVITYMPH:0.2f})mph average #BackYourself - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s {TOTALDURATION}"
        ## RARE MILESTONES
        
        if status_template is None:
            return None
        status = status_template.format(
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
            ACTIVITYURL="https://www.strava.com/activities/{}".format(latest_event['id']),
            ALLACTIVITYDURATION=self.secsToStr(duration_sum),
            ALLACTIVITYDISTANCEKM=distance_sum/1000,
            ALLACTIVITYDISTANCEMILES=distance_sum/1609,
            ALLACTIVITYCOUNT=count_sum,
            ACTIVITYMPH=latest_activity_mph
            )
        if "device_name" in latest_event:
            if latest_event['device_name'] == 'Zwift':
                status += " #RideOn @GoZwift"
        return status
    
    def secsToStr(self,seconds):
        if seconds > 86399:
            return "{} day(s) {}".format(math.floor(seconds/86400),time.strftime("%Hh %Mm %Ss", time.gmtime(seconds)))
        elif seconds > 3599:
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
        
    def _getSSM(self,parameterName):
        return ssm.get_parameter(Name="{PREFIX}{PARAMNAME}".format(PREFIX=os.environ['ssmPrefix'],PARAMNAME=parameterName))
        
    def _getEnv(self,variableName):
        return os.environ[variableName]