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
from strava import Strava

debug = False

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
    
    if "stravaId" in os.environ:
      if 'subscription_id' not in event or int(event['subscription_id']) != int(os.environ['stravaId']):
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
    strava = Strava(json.loads(athelete_record['Item']['tokens']), event['owner_id'],os.environ['stravaClientId'], os.environ['stravaClientSecret'],os.environ["totalsTable"])
    
    # get the activity details
    activity = strava.getActivity(event['object_id'])
   
    base_activity_type = activity['type'].replace("Virtual","")
    
    if "body" not in athelete_record['Item']:
        content = updateContent({},base_activity_type,activity['distance'],activity['elapsed_time'])
    else:
        content = updateContent(json.loads(athelete_record['Item']['body']),base_activity_type,activity['distance'],activity['elapsed_time'])
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

        strava_athlete = strava.getCurrentAthlete()
        
        ytd = content[str(datetime.now().year)][base_activity_type]
        
        ## Convert activity verb to a noun
        activity_type = base_activity_type
        if base_activity_type in VERBTONOUN:
            activity_type =  VERBTONOUN[base_activity_type]
            
        status = "{FIRSTNAME} {LASTNAME} did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s: {TOTALDISTANCEMILES:0.2f}miles ({TOTALDISTANCEKM:0.2f}km) in {TOTALDURATION}".format(
            FIRSTNAME=strava_athlete['firstname'],
            LASTNAME=strava_athlete['lastname'],
            TYPE=activity_type,
            DISTANCEMILES=activity['distance']/1609,
            DISTANCEKM=activity['distance']/1000,
            DURATION=secsToStr(activity['elapsed_time']),
            TOTALDISTANCEMILES=ytd['distance']/1609,
            TOTALDISTANCEKM=ytd['distance']/1000,
            TOTALDURATION=secsToStr(ytd['duration']),
            TOTALCOUNT=ytd['count'],
            ACTIVITYURL="https://www.strava.com/activities/{}".format(activity['id']))
        if "device_name" in activity:
            if activity['device_name'] == 'Zwift':
                status += " #RideOn #Zwift"

        if ("photos" in activity and 
            "primary" in activity['photos'] and 
            activity['photos']['primary'] is not None and 
            "urls" in activity['photos']['primary'] and 
            "600" in activity['photos']['primary']['urls']):
                
                image = requests.get(activity['photos']['primary']['urls']['600'])
                if image.status_code == 200:
                    try:
                        twitterImage = twitter.upload_media(media=image.content)
                    except Exception as e:
                        logger.error("Failed to upload media from {} to twitter".format(activity['photos']['primary']['urls']['600']))
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
