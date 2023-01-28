import json
import time
import logging
import requests
import boto3
import datetime
import math
import os
import traceback
from . import utils


logger = logging.getLogger()

logging.getLogger()
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger.setLevel(logging.INFO)

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
    
    def __init__(self, athleteId: int = None, auth:str = None):
        
        self.stravaClientId=utils.getSSM("StravaClientId")
        if self.stravaClientId is None:
            return None
        self.stravaClientSecret=utils.getSSM("StravaClientSecret")
        if self.stravaClientSecret is None:
            return None
        self.ddbTableName=utils.getEnv("totalsTable")
        self.ddbDetailTableName=utils.getEnv("detailsTable")
        
        if auth is not None:
            self.registrationResult = self._newAthlete(auth)
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
                
                # Check to see if club mode is active, and if they are a member of the club
                clubId = utils.getSSM("StravaClubId")
                logger.info("Required ClubId = '{CLUBID}'".format(CLUBID=clubId))
                found = False
                PER_PAGE = 30
                if clubId is not None:
                    logger.info("Club is NOT None, so now looking for the club in the athletes record.")
                    page = 1
                    while True:
                        logger.debug("Looking on page {PAGE} for athletes clubs".format(PAGE=page))
                        clubs = self._get(endpoint = "{STRAVA}/athlete/clubs?page={PAGE}&per_page={PER_PAGE}".format(STRAVA=self.STRAVA_API_URL,PAGE=page,PER_PAGE=PER_PAGE))
                        for club in clubs:
                            if club['id'] == int(clubId):
                                found = True
                                break
                        page+=1
                    if found == False:
                        logger.error("Athlete is not a member of the Club! Returning 401.")
                        unauthorised = {
                            "statusCode": 401,
                            "headers": {
                                "Content-Type": "text/html"
                            },
                            "body": "Unauthorised registration attempt."
                        }
                        return unauthorised
                        
                logger.info("Net new athlete. Welcome!")
                
                # Get any existing data for runs, rides or swims they may have done, and add these as the starting status for the body element
                current_year = datetime.datetime.now().year
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
                            # if the activity is already in the DDB, this will excpetion
                            self.putDetailActivity(activity)
                        except Exception as e:
                            logger.error(traceback.format_exc())
                            logger.error("Failed to add activity {ID}; trying to continue. This event will not be added to the totals.".format(ID=activity['id']))
                        else:
                            # if the activity is not already in the ddb, then we can add it to the running totals
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
            success = {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "text/html"
                    },
                    "body": "Looking good. I've grabbed all your activity for this year, and will monitor your efforts as you upload to Strava."
                }
            return success
        else:
            exit() # Don't give them any detail about the failure
            
        
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
              'activityId': int(activity['id']),
              'athleteId': int(self.athleteId),
              'eventEpoch': int(datetime.datetime.strptime(activity['start_date'],"%Y-%m-%dT%H:%M:%SZ").timestamp()),
              'event': json.dumps(activity)
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
    
    def updateActivityDescription(self, athlete_year_stats: dict, latest_event: dict):
        body = {"description": self.makeStravaDescriptionString(athlete_year_stats,latest_event)}
        endpoint = "{STRAVA}/activities/{ID}".format(STRAVA=self.STRAVA_API_URL,ID=latest_event['id'])
        if self._put(endpoint,body) is None:
            return False
        return True
        
    def makeStravaDescriptionString(self, athlete_year_stats: dict, latest_event: dict):
        
        logger.info("Making Strava Description Update String")
        
        ytd = athlete_year_stats[latest_event['type']]
        
        duration_sum =0
        distance_sum =0
        count_sum=0
        
        for activity_key, activity in athlete_year_stats.items():
            duration_sum+=activity['duration']
            distance_sum+=activity['distance']
            count_sum+=activity['count']
            
        activity_type = latest_event['type']
        if activity_type in self.VERBTONOUN:
            activity_type =  self.VERBTONOUN[activity_type]
        
        template = "YTD for {TOTALCOUNT} {TYPE}s {TOTALDISTANCEMILES:0.2f}miles / {TOTALDISTANCEKM:0.2f}km in {TOTALDURATION}"
        
        if self.getRecoveryTime(latest_event) is not None:
            template+="\nRecovery Time {RECOVERYTIME}"
            
        body = template.format(
            TYPE=activity_type,
            TOTALDISTANCEMILES=ytd['distance']/1609,
            TOTALDISTANCEKM=ytd['distance']/1000,
            TOTALDURATION=utils.secsToStr(ytd['duration']),
            TOTALCOUNT=ytd['count'],
            RECOVERYTIME=utils.getRecoveryTime(latest_event)
            )
        
        if "description" in latest_event and latest_event['description'] is not None:
            body = "{DESC}\n\n{BODY}".format(DESC=latest_event['description'],BODY=body)
            
        logger.info("Updating Strava Description String: '{STRING}'".format(STRING=body))
            
        return body
        
    def getRecoveryTime(self,event):
        if "average_heartrate" not in event:
            return None
    
        wrt_sec = ((event['average_heartrate']*(event['elapsed_time']/60))/200)*3600
        
        return utils.secsToStr(min(int(wrt_sec),4*24*60*60))
        
    def makeTwitterString(self,athlete_year_stats: dict,latest_event: dict):
        
        logger.info("Making Twitter String")
        
        ytd = athlete_year_stats[latest_event['type']]
        
        if "private" in latest_event and latest_event['private']:
            return None 
        
        ## Convert activity verb to a noun
        activity_type = latest_event['type']
        if activity_type in self.VERBTONOUN:
            activity_type =  self.VERBTONOUN[activity_type]
        strava_athlete = self.getCurrentAthlete()
        
        latest_activity_mph = utils.secAndMetersToMPH(latest_event['distance'],latest_event['elapsed_time'])
        ytd_activity_mph = utils.secAndMetersToMPH(ytd['distance']-latest_event['distance'],ytd['duration']-latest_event['elapsed_time'])
        latest_activity_kmph = utils.secAndMetersToKmPH(latest_event['distance'],latest_event['elapsed_time'])
        
        achievement_count = 0
        pr_count = 0
        
        duration_sum =0
        distance_sum =0
        count_sum=0
        for activity_key, activity in athlete_year_stats.items():
            duration_sum+=activity['duration']
            distance_sum+=activity['distance']
            count_sum+=activity['count']
        
        status_template = None
        
        name = "I"
        if utils.getSSM("StravaClubId") is not None:
            name = "{FIRSTNAME} {LASTNAME}".format(FIRSTNAME=strava_athlete['firstname'],LASTNAME=strava_athlete['lastname'])
        
        ytdall = "\nYTD for all {ALLACTIVITYCOUNT} activities {ALLACTIVITYDISTANCEMILES:0.2f}miles / {ALLACTIVITYDISTANCEKM:0.2f}km in {ALLACTIVITYDURATION} "
        ytdactivity = "\nYTD for {TOTALCOUNT} {TYPE}s {TOTALDISTANCEMILES:0.2f}miles / {TOTALDISTANCEKM:0.2f}km in {TOTALDURATION} "
        
        
        activity = "{NAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles / {DISTANCEKM:0.2f}km in {DURATION} at {ACTIVITYMPH}mph / {ACTIVITYKMPH}kmph - {ACTIVITYURL}"
        if activity_type == self.VERBTONOUN['Walk']:
            activity = "{NAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles / {DISTANCEKM:0.2f}km in {DURATION} - {ACTIVITYURL}"
        elif activity_type == self.VERBTONOUN['Run']:
            activity = "{NAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles / {DISTANCEKM:0.2f}km in {DURATION} at {MINUTEMILES}min/mile / {MINUTEKM}min/km - {ACTIVITYURL}"
        
        tags = []
        
        ytdstring = " "
        
        ## COMMON MILESTONES
        if math.floor(distance_sum/100000) != math.floor((distance_sum-latest_event['distance'])/100000):
            # If the most recent activity puts the sum of all the activities in that category for the year over a 100km stone
            ytdstring = ytdall
            tags.append("🙌")
        if math.floor(distance_sum/160900) != math.floor((distance_sum-latest_event['distance'])/160900):
            # If the most recent activity puts the sum of all the activities in that category for the year over a 100mile stone
            ytdstring = ytdall
            tags.append("🙌")
        if math.floor(duration_sum/86400) != math.floor((duration_sum-latest_event['elapsed_time'])/86400):
            # If the most recent activity puts the sum of all the activities' duration in that category for the year over a 1day stone
            ytdstring = ytdall
            if activity_type == self.VERBTONOUN['Ride']:
                tags.append("🚴")
            elif activity_type == self.VERBTONOUN['Run']:
                tags.append("🏃")
            else:
                tags.append("🌍")
        if count_sum%100 ==0:
            # If this is their n00th activity in this category this year 
            ytdstring = ytdactivity
            tags.append("👏")
        if math.floor(ytd['distance']/100000) != math.floor((ytd['distance']-latest_event['distance'])/100000):
            # If the total distance for all activities this year has just gone over a 100km stone
            ytdstring = ytdactivity
            tags.append("🔥")
        if math.floor(ytd['distance']/160900) != math.floor((ytd['distance']-latest_event['distance'])/160900):
            # If the total distance for all activities this year has just gone over a 100mile stone
            ytdstring = ytdactivity
            tags.append("📏")
        if math.floor(ytd['duration']/86400) != math.floor((ytd['duration']-latest_event['elapsed_time'])/86400):
            # If the total duration for all activities this year has just gone over a 1day stone
            ytdstring = ytdactivity
            tags.append("🌍")
        if ytd['count'] == 1:
            # If they've just done their first activity for the year
            tags.append("⭐")
        if ytd['count']%10 == 0:
            #  If they've just done a multiple of 10 activities for the entire year
            ytdstring = ytdactivity
            tags.append("🔟")
        if latest_activity_mph > ytd_activity_mph*1.05:
            # If they were more than 5% faster than the year average for this activity
            ytdstring = ytdactivity
            tags.append("🤩")
        if latest_event['distance'] > ((ytd['distance']-latest_event['distance'])/(ytd['count']-1))*1.05:
            # If this was longer (distance) than the average by more than 5%
            logger.info("{EVENTDISTANCE} gt {AVG}".format(EVENTDISTANCE=latest_event['distance'],AVG=((ytd['distance']-latest_event['distance'])/(ytd['count']-1))*1.05))
            ytdstring = ytdactivity
            tags.append("💨")
        if latest_event['elapsed_time'] > ((ytd['duration']-latest_event['elapsed_time'])/(ytd['count']-1))*1.05:
            # If they spent longer than normal doing this activity
            ytdstring = ytdactivity
            tags.append("⏱️")
        if "pr_count" in latest_event and latest_event['pr_count'] > 0:
            tags.append("{PRCOUNT}x🔥")
            pr_count = latest_event['pr_count']
        if "achievement_count" in latest_event and latest_event['achievement_count'] > 0:
            tags.append("{NUMACHIEVEMENTS}x😤")
            achievement_count=latest_event['achievement_count']
        
        ## RARE MILESTONES
        
        if len(tags) == 0:
            return None
        
        if "device_name" in latest_event:
            if latest_event['device_name'] == 'Zwift':
                tags.append("#RideOn")
                tags.append("@GoZwift")
                if "Group Ride: Tour de Zwift" in latest_event['name']:
                    tags.append("#TdZ")
        
        local_start = datetime.datetime.strptime(latest_event['start_date_local'],"%Y-%m-%dT%H:%M:%SZ")
        if (activity_type == self.VERBTONOUN['Run'] or activity_type == self.VERBTONOUN['Walk']) and ("parkrun" in latest_event['name'].lower() or (4950<=latest_event['distance']<=5050 and local_start.weekday()==5 and 8 <=local_start.hour <= 10)):
            tags.append("#parkrun")
        
        tag_string = ' '.join(tags)
        status_template = activity+ytdstring+tag_string
        
        status = status_template.format(
            NAME=name,
            TYPE=activity_type,
            DISTANCEMILES=latest_event['distance']/1609,
            DISTANCEKM=latest_event['distance']/1000,
            DURATION=utils.secsToStr(latest_event['elapsed_time']),
            TOTALDISTANCEMILES=ytd['distance']/1609,
            TOTALDISTANCEKM=ytd['distance']/1000,
            TOTALDURATION=utils.secsToStr(ytd['duration']),
            TOTALCOUNT=ytd['count'],
            ACTIVITYURL="https://www.strava.com/activities/{}".format(latest_event['id']),
            ALLACTIVITYDURATION=utils.secsToStr(duration_sum),
            ALLACTIVITYDISTANCEKM=distance_sum/1000,
            ALLACTIVITYDISTANCEMILES=distance_sum/1609,
            ALLACTIVITYCOUNT=count_sum,
            ACTIVITYMPH=latest_activity_mph,
            ACTIVITYKMPH=latest_activity_kmph,
            NUMACHIEVEMENTS=achievement_count,
            PRCOUNT=pr_count,
            MINUTEMILES=utils.getMinMiles(latest_event['elapsed_time'],latest_event['distance']),
            MINUTEKM=utils.getMinKm(latest_event['elapsed_time'],latest_event['distance'])
            )

        logger.info("Returning Twitter String: '{STRING}'".format(STRING=status))
        
        return status
    

                
    def _get(self,endpoint):
        counter = 0
        while True:
            try:
                #logger.setLevel(logging.DEBUG)
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
                elif 400 <= activity.status_code <= 599:
                    logger.error("Got an error returned")
                    logger.error("code:{CODE}\nmessage:{MESSAGE}".format(CODE=activity.status_code,MESSAGE=activity.text))
                    return {}
                elif counter == RETRIES:
                    logger.error("Get failed even after retries")
                    logger.error("{} - {}".format(activity.status_code,activity.content))
                    return {}
                else:
                    logger.debug("Failed ({COUNT}<{RETRIES}), but going to retry.".format(COUNT=counter,RETRIES=RETRIES))
                    counter+=1
                    time.sleep(PAUSE)
            except Exception as e:
                logger.error("An Exception occured while getting {} ".format(endpoint))
                logger.error(e)
                return {}
    
    def _put(self,endpoint,body):
        counter = 0
        while True:
            try:
                #logger.setLevel(logging.DEBUG)
                logger.debug("Checking if tokens need a refresh")
                self.refreshTokens()
                logger.debug("Sending PUT request to strava endpoint")
                logger.debug(self.tokens['access_token'])
                activity = requests.put(
                    endpoint,
                    headers={'Authorization':"Bearer {ACCESS_TOKEN}".format(ACCESS_TOKEN=self.tokens['access_token'])},
                    data=body,
                    timeout=PAUSE*5
                    )
                logger.debug("Returned from PUT request")
                if activity.status_code == 200:
                    logger.debug("All good. Returning.")
                    return activity.json()
                elif 400 <= activity.status_code <= 599:
                    logger.error("Got an error returned")
                    logger.error("code:{CODE}\nmessage:{MESSAGE}".format(CODE=activity.status_code,MESSAGE=activity.text))
                    return None
                elif counter == RETRIES:
                    logger.error("Get failed even after retries")
                    logger.error("{} - {}".format(activity.status_code,activity.content))
                    return None
                else:
                    logger.debug("Failed ({COUNT}<{RETRIES}), but going to retry.".format(COUNT=counter,RETRIES=RETRIES))
                    counter+=1
                    time.sleep(PAUSE)
            except Exception as e:
                logger.error("An Exception occured while putting to {} ".format(endpoint))
                logger.error(e)
                return None
                
    def getActivity(self,activityId):
        endpoint = "{STRAVA}/activities/{ID}".format(STRAVA=self.STRAVA_API_URL,ID=activityId)
        return(self._get(endpoint))
        
    def getCurrentAthlete(self):
        endpoint = "{STRAVA}/athlete".format(STRAVA=self.STRAVA_API_URL)
        return(self._get(endpoint))
        
    def getAthlete(self,athleteId):
        endpoint = "{STRAVA}/athletes/{ID}/stats".format(STRAVA=self.STRAVA_API_URL,ID=athleteId)
        return(self._get(endpoint))
        
    def getRegistrationResult(self):
        return self.registrationResult
