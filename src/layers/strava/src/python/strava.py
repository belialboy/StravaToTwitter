import json
import time
import logging
import requests
import boto3
import datetime
import math
import os
import traceback
import random
import sys

logger = logging.getLogger()

logging.getLogger()
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger.setLevel(logging.INFO)

PAUSE = 1 #second
RETRIES = 5

ssm = boto3.client("ssm")

class Strava:
    STRAVA_API_URL = "https://www.strava.com/api/v3"
    STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
    STRAVA_DURATION_INDEX = "moving_time"
    VERBTONOUN = { "VirtualRun": "virtual run",
               "Run": "run",
               "VirtualRide": "virtual ride",
               "Ride": "ride",
               "Rowing": "row",
               "Walk": "walk",
               "Yoga": "yoga session",
               "WeightTraining": "weight training session",
               "StairStepper": "stair stepping session",
               "Workout": "workout",
               "Hike": "hike",
               "Swim": "swim"
             }
    ZERODISTANCE = [
        "yoga session",
        "workout",
        "stair stepping session",
        "weight training session"]
    
    STRETCH_PERCENT = 1.1
    
    def __init__(self, athleteId: int = None, auth:str = None, stravaClientId:str = None, stravaClientSecret:str = None):
        
        self.stravaClientId = stravaClientId
        if self.stravaClientId is None:
            self.stravaClientId=Utils.getSSM("StravaClientId")
        if self.stravaClientId is None:
            return None
        
        self.stravaClientSecret = stravaClientSecret
        if self.stravaClientSecret is None:
            self.stravaClientSecret=Utils.getSSM("StravaClientSecret")
        if self.stravaClientSecret is None:
            return None
            
        self.ddbTableName=Utils.getEnv("totalsTable")
        self.ddbDetailTableName=Utils.getEnv("detailsTable")
        
        self.solly = False ## If it's false, and we have the permission to, we'll write to the strava activity
        if auth is not None:
            self.registrationResult = self._newAthlete(auth)
        elif athleteId is not None:
            self.athleteId = athleteId
            self.athlete = self._getAthleteFromDDB()
            if self.athlete is not None:
                self.tokens = json.loads(self.athlete['tokens'])
                if 'spotify' in self.athlete:
                    self.spotify = json.loads(self.athlete['spotify'])
                if 'solly' in self.athlete:
                    self.solly = True
    
    def _newAthlete(self,code):
        
        new_tokens = self._getTokensWithCode(code)
        if new_tokens is not None:
            
            self.tokens = new_tokens
            self.athleteId = new_tokens['athlete']['id']
            logger.info("Checking to see if the athlete is already registered")
            athlete_record = self._getAthleteFromDDB()
            
            if athlete_record is None:
                # Just in case everythin else fails, write some stuff to the db
                self._putAthleteToDB()
                self._writeTokens()
                # Check to see if club mode is active, and if they are a member of the club
                clubId = Utils.getSSM("StravaClubId")
                logger.info("Required ClubId = '{CLUBID}'".format(CLUBID=clubId))
                found = False
                PER_PAGE = 30
                if clubId is not None:
                    logger.info("Club is NOT None, so now looking for the club in the athletes record.")
                    page = 1
                    while True:
                        logger.debug("Looking on page {PAGE} for athletes clubs".format(PAGE=page))
                        clubs = self._get(endpoint = "{STRAVA}/athlete/clubs?page={PAGE}&per_page={PER_PAGE}".format(STRAVA=self.STRAVA_API_URL,PAGE=page,PER_PAGE=PER_PAGE))
                        if len(clubs)==0:
                            break
                        logger.info(clubs)
                        for club in clubs:
                            if club['id'] == int(clubId):
                                found = True
                                break
                        if found:
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
                self.buildTotals()
            
            self._writeTokens()
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
            
    def flattenTotals(self):
        logger.info("Flattening totals for this athlete")
        
        current_year = datetime.datetime.now().year
        start_epoch = datetime.datetime(current_year,1,1,0,0).timestamp()
        
        athlete = self._getAthleteFromDDB()
        newbody = json.loads(athlete['body'])
        logger.info(newbody)
        newbody = newbody.pop(str(current_year))
        logger.info(newbody)
        self._updateAthleteOnDB(json.dumps(newbody))
        self._writeTokens()
        
        logger.info("Done flattening totals for this athlete")
            
    def buildTotals(self):
        logger.info("Building totals for this athlete")
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
                            duration=activity[self.STRAVA_DURATION_INDEX]
                            )
            ## Write what we have to the DDB table
            if page == 1:
                try:
                    self._putAthleteToDB(json.dumps(content))
                except:
                    self._updateAthleteOnDB(json.dumps(content))
            else:
                self._updateAthleteOnDB(json.dumps(content))
            ## Are there more activities?
            if len(activities) < PER_PAGE:
                break
            page+=1
        logger.info("Done building totals for this athlete")
        
    def refreshTokens(self):
        logger.debug("We should already have some tokens. Check if we need to refresh.")
        logger.debug(self.tokens)
        if int(time.time()) > int(self.tokens['expires_at']):
            logger.info("Need to refresh Strava Tokens")
            new_tokens = self._getTokensWithRefresh()
            logger.info("Got new Strava tokens")
            logger.debug(new_tokens)
            self._writeTokens(new_tokens)

                
    def _writeTokens(self,tokens=None):
        logger.info("Writing strava tokens to DDB")
        logger.info(tokens)
        table = self._getDDBTable()
        logger.debug("Building token dict for storage")
        if tokens is not None:
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
              'body': body_as_string,
            })
        self._writeTokens()
            
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
            logger.info("Got initial tokens for athlete.")
            logger.info(response.json())
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
        try:
            table.put_item(
                Item={
                  'activityId': int(activity['id']),
                  'athleteId': int(self.athleteId),
                  'eventEpoch': int(datetime.datetime.strptime(activity['start_date'],"%Y-%m-%dT%H:%M:%SZ").timestamp()),
                  'event': json.dumps(activity)
                })
        except:
            table.update_item(
                Key={'activityId': int(activity['id']),'athleteId': int(self.athleteId)},
                AttributeUpdates={
                  'event':{
                    'Value':json.dumps(activity),
                    'Action':'PUT'}
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
    
    def updateActivityDescription(self, athlete_year_stats: dict, latest_event: dict, spotifytracks = None):
        if self.solly:
            return False
        if spotifytracks is not None:
            body = {"description": "{PERFORMANCE}\n\n{TRACKS}".format(PERFORMANCE=self.makeStravaDescriptionString(athlete_year_stats,latest_event),TRACKS = spotifytracks)}
        else:
            body = {"description": self.makeStravaDescriptionString(athlete_year_stats,latest_event)}
        endpoint = "{STRAVA}/activities/{ID}".format(STRAVA=self.STRAVA_API_URL,ID=latest_event['id'])
        if self._put(endpoint,body) is None:
            return False
        return True
        
    def makeStravaDescriptionString(self, athlete_year_stats: dict, latest_event: dict):
        
        logger.info("Making Strava Description Update String")
        
        duration_sum =0
        distance_sum =0
        count_sum=0
        for activity_key, activity in athlete_year_stats.items():
            duration_sum+=activity['duration']
            distance_sum+=activity['distance']
            count_sum+=activity['count']
        
        ytd = athlete_year_stats[latest_event['type']]
            
        activity_type = latest_event['type']
        if activity_type in self.VERBTONOUN:
            activity_type =  self.VERBTONOUN[activity_type]
        
        template = "YTD for {TOTALCOUNT} {TYPE}s {TOTALDISTANCEMILES:0.2f}miles / {TOTALDISTANCEKM:0.2f}km in {TOTALDURATION} {TAGS}"
        if activity_type in self.ZERODISTANCE:
            template = "YTD for {TOTALCOUNT} {TYPE}s in {TOTALDURATION} {TAGS}"
        
        if self.getEffortQ(latest_event) is not None:
            template+="\n{EFFORT:0.1f}% Estimated Effort"
        
        tags = self.getTags(latest_event,ytd,distance_sum,duration_sum,count_sum)
        tag_string = ' '.join(tags)
        
        body = template.format(
            TYPE=activity_type,
            TOTALDISTANCEMILES=ytd['distance']/1609,
            TOTALDISTANCEKM=ytd['distance']/1000,
            TOTALDURATION=Utils.secsToStr(ytd['duration']),
            TOTALCOUNT=ytd['count'],
            EFFORT=self.getEffortQ(latest_event),
            TAGS = tag_string
            )
        
        if "description" in latest_event and latest_event['description'] is not None:
            body = "{DESC}\n\n{BODY}".format(DESC=latest_event['description'],BODY=body)
            
        logger.info("Updating Strava Description String: '{STRING}'".format(STRING=body))
            
        return body
        
    def getEffortQ(self,event):
        if "average_heartrate" not in event:
            return None
    
        wrt_sec = ((event['average_heartrate']*(event[self.STRAVA_DURATION_INDEX]/60))/200)*3600
        
        return (min(int(wrt_sec),4*24*60*60) / (4*24*60*60))*100
        
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
        
        latest_activity_mph = Utils.secAndMetersToMPH(latest_event['distance'],latest_event[self.STRAVA_DURATION_INDEX])
        ytd_activity_mph = Utils.secAndMetersToMPH(ytd['distance']-latest_event['distance'],ytd['duration']-latest_event[self.STRAVA_DURATION_INDEX])
        latest_activity_kmph = Utils.secAndMetersToKmPH(latest_event['distance'],latest_event[self.STRAVA_DURATION_INDEX])
        
        duration_sum =0
        distance_sum =0
        count_sum=0
        for activity_key, activity in athlete_year_stats.items():
            duration_sum+=activity['duration']
            distance_sum+=activity['distance']
            count_sum+=activity['count']
        
        name = "I"
        if Utils.getSSM("StravaClubId") is not None:
            name = "{FIRSTNAME} {LASTNAME}".format(FIRSTNAME=strava_athlete['firstname'],LASTNAME=strava_athlete['lastname'])
        
        tagtemplate = {
            'ytdall': "\nYTD for all {ALLACTIVITYCOUNT} activities {ALLACTIVITYDISTANCEMILES:0.2f}miles / {ALLACTIVITYDISTANCEKM:0.2f}km in {ALLACTIVITYDURATION} ",
            'ytdactivity': "\nYTD for {TOTALCOUNT} {TYPE}s {TOTALDISTANCEMILES:0.2f}miles / {TOTALDISTANCEKM:0.2f}km in {TOTALDURATION} ",
            'activity': "{NAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles / {DISTANCEKM:0.2f}km in {DURATION} at {ACTIVITYMPH}mph / {ACTIVITYKMPH}kmph - {ACTIVITYURL}"
            }
        
        if activity_type == self.VERBTONOUN['Walk']:
            tagtemplate['activity'] = "{NAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles / {DISTANCEKM:0.2f}km in {DURATION} - {ACTIVITYURL}"
        elif activity_type == self.VERBTONOUN['Run']:
            tagtemplate['activity'] = "{NAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles / {DISTANCEKM:0.2f}km in {DURATION} at {MINUTEMILES}min/mile / {MINUTEKM}min/km - {ACTIVITYURL}"
        elif activity_type in self.ZERODISTANCE:
            tagtemplate['activity'] = "{NAME} did a {TYPE} for {DURATION} - {ACTIVITYURL}"
            tagtemplate['ytdactivity'] = "\nYTD for {TOTALCOUNT} {TYPE}s in {TOTALDURATION} "
            tagtemplate['ytdall'] = "\nYTD for all {ALLACTIVITYCOUNT} activities in {ALLACTIVITYDURATION} "
        
        tags = self.getTags(latest_event,ytd,distance_sum,duration_sum,count_sum)
        
        if len(tags) == 0:
            # Nothing special. Go Home!
            return None
        elif "💪" in tags:
            ytdstring = ""
        elif "🇱" in tags or "🔥" in tags or "📏" in tags or "🔟" in tags or "🤩" in tags or "💨" in tags or "⏱️" in tags:
            ytdstring = tagtemplate['ytdactivity']
        else:
            ytdstring = tagtemplate['ytdall']
        
        ## Extra tags for the tweet text
        if "device_name" in latest_event:
            if latest_event['device_name'] == 'Zwift':
                tags.append("#RideOn")
                tags.append("@GoZwift")
                if "Group Ride: Tour de Zwift" in latest_event['name']:
                    tags.append("#TdZ")
        
        local_start = datetime.datetime.strptime(latest_event['start_date_local'],"%Y-%m-%dT%H:%M:%SZ")
        if (activity_type == self.VERBTONOUN['Run'] or activity_type == self.VERBTONOUN['Walk']) and ("parkrun" in latest_event['name'].lower() or (4900<=latest_event['distance']<=5100 and local_start.weekday()==5 and 8 <=local_start.hour <= 10)):
            tags.append("#parkrun")
        
        tag_string = ' '.join(tags)
        status_template = tagtemplate['activity']+ytdstring+tag_string
        
        status = status_template.format(
            NAME=name,
            TYPE=activity_type,
            DISTANCEMILES=latest_event['distance']/1609,
            DISTANCEKM=latest_event['distance']/1000,
            DURATION=Utils.secsToStr(latest_event[self.STRAVA_DURATION_INDEX]),
            TOTALDISTANCEMILES=ytd['distance']/1609,
            TOTALDISTANCEKM=ytd['distance']/1000,
            TOTALDURATION=Utils.secsToStr(ytd['duration']),
            TOTALCOUNT=ytd['count'],
            ACTIVITYURL="https://www.strava.com/activities/{}".format(latest_event['id']),
            ALLACTIVITYDURATION=Utils.secsToStr(duration_sum),
            ALLACTIVITYDISTANCEKM=distance_sum/1000,
            ALLACTIVITYDISTANCEMILES=distance_sum/1609,
            ALLACTIVITYCOUNT=count_sum,
            ACTIVITYMPH=latest_activity_mph,
            ACTIVITYKMPH=latest_activity_kmph,
            MINUTEMILES=Utils.getMinMiles(latest_event[self.STRAVA_DURATION_INDEX],latest_event['distance']),
            MINUTEKM=Utils.getMinKm(latest_event[self.STRAVA_DURATION_INDEX],latest_event['distance'])
            )

        logger.info("Returning Twitter String: '{STRING}'".format(STRING=status))
        
        return status
    
    def getTags(self,latest_event,ytd,distance_sum,duration_sum,count_sum):
        
        activity_type = latest_event['type']
        if activity_type in self.VERBTONOUN:
            activity_type =  self.VERBTONOUN[activity_type]
            
        latest_event_speed = latest_event['distance']/latest_event[self.STRAVA_DURATION_INDEX]
        ytd_speed = (ytd['distance']-latest_event['distance'])/(ytd['duration']-latest_event[self.STRAVA_DURATION_INDEX])
            
        tags = []
        if math.floor(distance_sum/100000) != math.floor((distance_sum-latest_event['distance'])/100000):
            # If the most recent activity puts the sum of all the activities in that category for the year over a 100km stone
            tags.append("🙌")
        elif math.floor(distance_sum/160900) != math.floor((distance_sum-latest_event['distance'])/160900):
            # If the most recent activity puts the sum of all the activities in that category for the year over a 100mile stone
            tags.append("🙌")
        if math.floor(duration_sum/86400) != math.floor((duration_sum-latest_event[self.STRAVA_DURATION_INDEX])/86400):
            # If the most recent activity puts the sum of all the activities' duration in that category for the year over a 1day stone
            if activity_type == self.VERBTONOUN['Ride']:
                tags.append("🚴")
            elif activity_type == self.VERBTONOUN['Run']:
                tags.append("🏃")
            else:
                tags.append("⌛")
        if count_sum%50 ==0:
            # If this is their n00th activity in this category this year 
            tags.append("🇱")
        if math.floor(ytd['distance']/100000) != math.floor((ytd['distance']-latest_event['distance'])/100000):
            # If the total distance for all activities this year has just gone over a 100km stone
            tags.append("🔥")
        if math.floor(ytd['distance']/160900) != math.floor((ytd['distance']-latest_event['distance'])/160900):
            # If the total distance for all activities this year has just gone over a 100mile stone
            tags.append("📏")
        if math.floor(ytd['duration']/86400) != math.floor((ytd['duration']-latest_event[self.STRAVA_DURATION_INDEX])/86400):
            # If the total duration for all activities this year has just gone over a 1day stone
            tags.append("🌍")
        if ytd['count'] == 1:
            # If they've just done their first activity for the year
            tags.append("💪")
        if ytd['count']%10 == 0:
            #  If they've just done a multiple of 10 activities for the entire year
            tags.append("🔟")
        if latest_event_speed > ytd_speed*self.STRETCH_PERCENT:
            # If they were more than n% faster than the year average for this activity
            tags.append("🤩")
        if latest_event['distance'] > ((ytd['distance']-latest_event['distance'])/(ytd['count']-1))*self.STRETCH_PERCENT:
            # If this was longer (distance) than the average by more than n%
            tags.append("💨")
        if latest_event[self.STRAVA_DURATION_INDEX] > ((ytd['duration']-latest_event[self.STRAVA_DURATION_INDEX])/(ytd['count']-1))*self.STRETCH_PERCENT:
            # If they spent n% longer than normal doing this activity
            tags.append("⏱️")
        
        if "achievement_count" in latest_event and latest_event['achievement_count'] > 0:
            pr_count = 0
            if "pr_count" in latest_event and latest_event['pr_count'] > 0:
                pr_count = latest_event['pr_count']
            tags.append('{PRs}{ACHs}'.format(PRs = "🌟"*min(pr_count,5), ACHs = "⭐"*max(min(latest_event['achievement_count']-pr_count,5),0)))
            
        ## RARE MILESTONES
        random.shuffle(tags)
        
        return tags
                
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


class Utils(object):
    
    @staticmethod
    def getSSM(parameterName):
        parameterFullName="{PREFIX}{PARAMNAME}".format(PREFIX=Utils.getEnv('ssmPrefix'),PARAMNAME=parameterName)
        logger.info("Getting {PARAM} from parameter store".format(PARAM=parameterName))
        try:
            return ssm.get_parameter(Name=parameterFullName)['Parameter']['Value']
        except Exception as e:
            logger.error(e)
            logger.error("No {PARAM} set in SSM parameter store".format(PARAM=parameterFullName))
            return None
    
    @staticmethod
    def setSSM(parameterName,parameterValue):
      parameterFullName="{PREFIX}{PARAMNAME}".format(PREFIX=Utils.getEnv('ssmPrefix'),PARAMNAME=parameterName)
      try:
        ssm.set_parameter(Name=parameterFullName,Value=parameterValue)
      except ssm.exceptions.ParameterAlreadyExists as e:
        ssm.delete_parameter(Name=parameterFullName)
        ssm.set_parameter(Name=parameterFullName,Value=parameterValue)
    
    @staticmethod
    def getEnv(variableName):
        if variableName in os.environ:
            return os.environ[variableName]
        logger.error("No {VAR} set in lambda environment".format(VAR=variableName))
        return None
    
    @staticmethod
    def secsToStr(seconds):
        if seconds > (86400*2)-1:
            return "{} days {}".format(math.floor(seconds/86400),time.strftime("%Hh", time.gmtime(seconds)))
        elif seconds > 86400-1:
            return "1 day {}".format(time.strftime("%Hh%Mm", time.gmtime(seconds)))
        elif seconds > 3600-1:
            return time.strftime("%Hh%Mm%Ss", time.gmtime(seconds))
        else:
            return time.strftime("%Mm%Ss", time.gmtime(seconds))
    
    @staticmethod        
    def secAndMetersToMPH( meters, seconds):
        if seconds == 0:
            return float('{:.1f}'.format(0))
            
        miles = meters/1609
        hours = seconds/3600
        
        mph = miles/hours
        
        return float('{:.1f}'.format(mph))
    
    @staticmethod    
    def secAndMetersToKmPH(meters, seconds):
        if seconds == 0:
            return float('{:.1f}'.format(0))
        
        km = meters/1000
        hours = seconds/3600
        
        kmph = km/hours
        
        return float('{:.1f}'.format(kmph))
    
    @staticmethod    
    def getMinMiles(seconds, meters):
        if seconds == 0 or meters == 0:
            return "0:00"
        
        minMile = 26.8224 / (meters/seconds)
        
        return "{MIN}:{SEC:02}".format(MIN=int(minMile//1),SEC=int((minMile%1)*60))
    
    @staticmethod    
    def getMinKm(seconds, meters):
        if seconds == 0 or meters == 0:
            return "0:00"
            
        minKm = ((seconds/60)/(meters/1000))
        
        return "{MIN}:{SEC:02}".format(MIN=int(minKm//1),SEC=int((minKm%1)*60))
    