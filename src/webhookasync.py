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

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    
    body = json.loads(event)
    
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ["totalsTable"])
    
    athelete_record = table.get_item(Key={'Id': body['owner_id']})
    logger.info(athelete_record)
    
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
                    'Id': body['owner_id']
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
        "https://www.strava.com/api/v3/activities/{ID}".format(ID=body['object_id']),
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
                'Id': body['owner_id']
            },
            UpdateExpression="set body=:c",
            ExpressionAttributeValues={
                ':c': json.dumps(content)
            }
        )

        if "twitter" in athelete_record:
            twitter_creds = json.loads(athelete_record['twitter'])
            twitter = Twython(twitter_creds["twitterConsumerKey"], 
                twitter_creds["twitterConsumerSecret"],
                twitter_creds["twitterAccessTokenKey"], 
                twitter_creds["twitterAccessTokenSecret"])
            
            ytd = content[str(datetime.now().year)][activity_json['type']]
            logging.info(ytd)
            status = "I did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s: {TOTALDISTANCEMILES:0.2f}miles ({TOTALDISTANCEKM:0.2f}km) in {TOTALDURATION}".format(
                TYPE=activity_json['type'],
                DISTANCEMILES=activity_json['distance']/1609,
                DISTANCEKM=activity_json['distance']/1000,
                DURATION=secsToStr(activity_json['elapsed_time']),
                TOTALDISTANCEMILES=ytd['distance']/1609,
                TOTALDISTANCEKM=ytd['distance']/1000,
                TOTALDURATION=secsToStr(ytd['duration']),
                TOTALCOUNT=ytd['count'],
                ACTIVITYURL="https://www.strava.com/activities/{}".format(activity_json['id']))
            if activity.json() == 'VirtualRide':
                status += " @GoZwift"

            if "photos" in activity_json and "primary" in activity_json['photos'] and "urls" in activity_json['photos']['primary'] and "600" in activity_json['photos']['primary']['urls']:
                image = requests.get(activity_json['photos']['primary']['urls']['600'])
                if image.status_code == 200:
                    twitterImage = twitter.upload_media(media=image.content)
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
