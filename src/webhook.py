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

# Credentials setup
# Create the Twython Twitter client using our credentials
twitter = Twython(os.environ["twitterConsumerKey"], os.environ["twitterConsumerSecret"],
                  os.environ["twitterAccessTokenKey"], os.environ["twitterAccessTokenSecret"])

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    if event['httpMethod'] == "GET":
        # Auth for subscription creation
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({'hub.challenge':event['queryStringParameters']['hub.challenge']})
        }
        
    elif event['httpMethod'] == "POST":
        # A posted event from a subscription
        if "body" in event:
            body = json.loads(event['body'])
            
            if body['object_type'] == "activity" and body['aspect_type'] == "create":
                # get the athelete
                dynamodb = boto3.resource('dynamodb')
                table = dynamodb.Table(os.environ["totalsTable"])
                
                athelete_record = table.get_item(Key={'Id': body['owner_id']})
                logger.info(athelete_record)
                
                # check tokens still valid
                tokens = json.loads(athelete_record['Item']['tokens'])
                if int(time.time()) > tokens['expires_at']:
                    data = {
                        'client_id': os.environ['stravaClientId'],
                        'client_secret': os.environ['stravaClientSecret'],
                        'grant_type': "refresh_token",
                        'refresh_token': tokens['refresh_token']
                    }
                    response = requests.post("https://www.strava.com/oauth/token", json=data)
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
                
                # get the activity details
                activity = requests.get(
                    "https://www.strava.com/api/v3/activities/{ID}".format(ID=body['object_id']),
                    headers={'Authorization':"Bearer {ACCESS_TOKEN}".format(ACCESS_TOKEN=tokens['access_token'])}
                    )
                
                if activity.status_code == 200:
                    # read the activity and publish to twitter
                    logger.info(activity.json())
                    if "body" not in athelete_record['Item']:
                        content = {str(datetime.now().year):{activity.json()['type']:{"distance":activity.json()['distance'],"duration":activity.json()['elapsed_time'],"count":1}}}
                    else:
                        content = updateContent(json.loads(athelete_record['Item']['body']),activity.json()['type'],activity.json()['distance'],activity.json()['elapsed_time'])
                    table.update_item(
                        Key={
                            'Id': body['owner_id']
                        },
                        UpdateExpression="set body=:c",
                        ExpressionAttributeValues={
                            ':c': json.dumps(content)
                        }
                    )
        
                    ytd = content[str(datetime.now().year)][activity.json()['type']]
                    logging.info(ytd)
                    status = "I did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for {TOTALCOUNT} {TYPE}s: {TOTALDISTANCEMILES:0.2f}miles ({TOTALDISTANCEKM:0.2f}km) in {TOTALDURATION}".format(
                        TYPE=activity.json()['type'],
                        DISTANCEMILES=activity.json()['distance']/1609,
                        DISTANCEKM=activity.json()['distance']/1000,
                        DURATION=secsToStr(activity.json()['elapsed_time']),
                        TOTALDISTANCEMILES=ytd['distance']/1609,
                        TOTALDISTANCEKM=ytd['distance']/1000,
                        TOTALDURATION=secsToStr(ytd['duration']),
                        TOTALCOUNT=ytd['count'],
                        ACTIVITYURL="https://www.strava.com/activities/{}".format(activity.json()['id']))
                    if activity.json() == 'VirtualRide':
                        status += " @GoZwift"
    
                    if "photos" in activity.json() and "primary" in activity.json()['photos'] and "urls" in activity.json()['photos']['primary'] and "600" in activity.json()['photos']['primary']['urls']:
                        image = requests.get(activity.json()['photos']['primary']['urls']['600'])
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
                    logger.error("Failed to get the activity")
        logging.info("Profit!")
    
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": ""
        }

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
            logging.info("New activity")
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
