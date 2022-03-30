#!/usr/bin/env python
import json
# pylint: disable=fixme, import-error
from twython import Twython
from datetime import datetime
import time
import os
import requests
import boto3
import logging
import hashlib
import math
from botocore.exceptions import ClientError

debug = True

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VERBTONOUN = { "VirtualRun": "virtual run",
               "Run": "run",
               "VirtualRide": "virtual ride",
               "Ride": "ride",
               "Rowing": "row",
               "Walk": "walk"
             }

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    
    if "stravaId" in os.environ and int(event['subscription_id']) != int(os.environ['stravaId']):
        logger.error("This request does not have the subscription_id equal to the expected value.")
        return
    
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ["totalsTable"])
    
    athelete_record = table.get_item(Key={'Id': str(event['owner_id'])})
    logger.info("Checking for race condition")
    if "last_activity_id" in athelete_record['Item'] and event['object_id'] == athelete_record['Item']['last_activity_id']:
        logger.info("Bailing as this is a duplicate")
        exit()
    else:
        table.update_item(
            Key={
                'Id': str(event['owner_id'])
            },
            UpdateExpression="set last_activity_id=:c",
            ExpressionAttributeValues={
                ':c': event['object_id']
            }
        )
        
    # check tokens still valid
    tokens = json.loads(athelete_record['Item']['tokens'])
    if int(time.time()) > int(tokens['expires_at']):
        logger.info("Need to refresh Strava Tokens")
        data = {
            'client_id': os.environ['stravaClientId'],
            'client_secret': os.environ['stravaClientSecret'],
            'grant_type': "refresh_token",
            'refresh_token': tokens['refresh_token']
        }
        response = requests.post("https://www.strava.com/oauth/token", json=data)
        if response.status_code == 200:
            logger.info("Got new tokens")
            tokens = {"expires_at":response.json()['expires_at'],"access_token":response.json()['access_token'],"refresh_token":response.json()['refresh_token']}

            table.update_item(
                Key={
                    'Id': str(event['owner_id'])
                },
                UpdateExpression="set tokens=:c",
                ExpressionAttributeValues={
                    ':c': json.dumps(tokens)
                }
            )
        else:
            logger.error("Failed to get refreshed tokens")
            logger.error(response.raw)
            exit()
    
    # get the activity details
    activity = requests.get(
        "https://www.strava.com/api/v3/activities/{ID}".format(ID=event['object_id']),
        headers={'Authorization':"Bearer {ACCESS_TOKEN}".format(ACCESS_TOKEN=tokens['access_token'])}
        )
    
    if activity.status_code == 200:
        # read the activity and publish to twitter
        logger.info("Got the activity")
        logger.info(activity.json())
        activity_json = activity.json()
        
        if "body" not in athelete_record['Item']:
            content = {str(datetime.now().year):{activity_json['type']:{"distance":activity_json['distance'],"duration":activity_json['elapsed_time'],"count":1}}}
        else:
            content = updateContent(json.loads(athelete_record['Item']['body']),activity_json['type'],activity_json['distance'],activity_json['elapsed_time'])
        table.update_item(
            Key={
                'Id': str(event['owner_id'])
            },
            UpdateExpression="set body=:c",
            ExpressionAttributeValues={
                ':c': json.dumps(content)
            }
        )
        logger.info(content)

        if "twitter" in athelete_record['Item']:
            twitter_creds = json.loads(athelete_record['Item']['twitter'])
            twitter = Twython(twitter_creds["twitterConsumerKey"], 
                twitter_creds["twitterConsumerSecret"],
                twitter_creds["twitterAccessTokenKey"], 
                twitter_creds["twitterAccessTokenSecret"])

            strava_athlete = requests.get(
                "https://www.strava.com/api/v3/athlete",
                headers={'Authorization':"Bearer {ACCESS_TOKEN}".format(ACCESS_TOKEN=tokens['access_token'])}
                ).json()
            
            ytd = content[str(datetime.now().year)][activity_json['type']]
            logging.info(ytd)
            
            ## Convert activity verb to a noun
            activity_type = activity_json['type']
            if activity_json['type'] in VERBTONOUN:
                activity_type =  VERBTONOUN[activity_json['type']]
                
            status = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s: {TOTALDISTANCEMILES:0.2f}miles ({TOTALDISTANCEKM:0.2f}km) in {TOTALDURATION}".format(
                FIRSTNAME=strava_athlete['firstname'],
                LASTNAME=strava_athlete['lastname'],
                TYPE=activity_type,
                DISTANCEMILES=activity_json['distance']/1609,
                DISTANCEKM=activity_json['distance']/1000,
                DURATION=secsToStr(activity_json['elapsed_time']),
                TOTALDISTANCEMILES=ytd['distance']/1609,
                TOTALDISTANCEKM=ytd['distance']/1000,
                TOTALDURATION=secsToStr(ytd['duration']),
                TOTALCOUNT=ytd['count'],
                ACTIVITYURL="https://www.strava.com/activities/{}".format(activity_json['id']))
            if "device_name" in activity_json:
                if activity_json['device_name'] == 'Zwift':
                    status += " @GoZwift"

            if ("photos" in activity_json and 
                "primary" in activity_json['photos'] and 
                activity_json['photos']['primary'] is not None and 
                "urls" in activity_json['photos']['primary'] and 
                "600" in activity_json['photos']['primary']['urls']):
                    
                    image = requests.get(activity_json['photos']['primary']['urls']['600'])
                    if image.status_code == 200:
                        try:
                            twitterImage = twitter.upload_media(media=image.content)
                        except Exception as e:
                            logger.error("Failed to upload media from {} to twitter".format(activity_json['photos']['primary']['urls']['600']))
                            logger.error(e)
                            if not debug:
                                twitter.update_status(status=status)
                        else:
                            if not debug:
                              twitter.update_status(status=status, media_ids=[twitterImage['media_id']])
                    else:
                      if not debug:
                        twitter.update_status(status=status)
            else:
              if not debug:
                twitter.update_status(status=status)

            logging.info(status)
        else:
            logger.info("No twitter credentials found so passing on updating status")
    else:
        logger.error("Failed to get the activity")
        logger.error(response.raw)
        exit()

    logging.info("Profit!")


def updateContent(content, activityType, distance, duration):
    year = str(datetime.now().year)
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
    
def secsToStr(seconds):
    if seconds > 86400:
        return "{} day(s) {}".format(math.floor(seconds/86400),time.strftime("%Hh %Mm %Ss", time.gmtime(seconds)))
    elif seconds > 3600:
        return time.strftime("%Hhr %Mmins %Sseconds", time.gmtime(seconds))
    else:
        return time.strftime("%M minutes and %S seconds", time.gmtime(seconds))
