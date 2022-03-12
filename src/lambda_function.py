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

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Credentials setup
# Create the Twython Twitter client using our credentials
twitter = Twython(os.environ["twitterConsumerKey"], os.environ["twitterConsumerSecret"],
                  os.environ["twitterAccessTokenKey"], os.environ["twitterAccessTokenSecret"])

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)

    if "body" in event:
        body = json.loads(event['body'])
        if "URL" in body:
            stravaActivity = requests.get(body['URL'])
            if os.environ["stravaName"] in stravaActivity.text:
                ## Validated
                ## Grab the Totals if it exists for this user
                dynamodb = boto3.resource('dynamodb')
                table = dynamodb.Table(os.environ["totalsTable"])
                content = readDDB(os.environ["stravaName"],table)
                if not content:
                    # First call of this function
                    content = {datetime.now().year:{body['type']:{"distance":body['distance'],"duration":body['duration'],"count":1}}}
                else:
                    content = updateContent(content,body['type'],body['distance'],body['duration'])
                writeDDB(os.environ["stravaName"],table,content)
                
                ytd = content[datetime.now().year][body['type']]
                status = "I did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATION} - {ACTIVITYURL}\nYTD for {COUNT} {TYPE}s: {TOTALDISTANCEMILES:0.2f}miles ({TOTALDISTANCEKM:0.2f}km) in {TOTALDURATION}".format(
                    TYPE=body['type'],
                    DISTANCEMILES=body['distance']/1609.3444,
                    DISTANCEKM=body['distance']/1000,
                    DURATION=secsToStr(body['duration']),
                    TOTALDISTANCEMILES=ytd['distance']/1609.3444,
                    TOTALDISTANCEKM=ytd['distance']/1000,
                    TOTALDURATION=secsToStr(ytd['duration']),
                    TOTALCOUNT=ytd['count'],
                    ACTIVITYURL=body['URL'])
                if body['type'] == 'VirtualRide':
                    status += " @GoZwift"

                if "ImageURL" in body and "https://" in body['ImageURL']:
                    image = requests.get(body['ImageURL'])
                    if image.status_code == 200:
                        twitterImage = twitter.upload_media(media=image.content)
                        twitter.update_status(status=status, media_ids=[twitterImage['media_id']])
                    else:
                        twitter.update_status(status=status)
                else:
                    twitter.update_status(status=status)

    logging.info("Profit!")

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": ""
    }

def readDDB(stravaName, table):
    try:
        response = table.get_item(Key={'name': stravaName})
    except ClientError as e:
        return False
    else:
        if "Item" not in response:
            return False
        return json.loads(response['Item']['body'])
        
def writeDDB(stravaName, table, content):
    if not readDDB(stravaName,table):
        response = table.put_item(
           Item={
                'name': stravaName,
                'body': content
            })
    else:
        response = table.update_item(
                Key={
                    'name': stravaName
                },
                UpdateExpression="set body=:c",
                ExpressionAttributeValues={
                    ':c': content
                }
            )

def updateContent(content, activityType, distance, duration):
    year = datetime.now().year
    logging.info(content)
    logging.info(year)
    if year in content:
        logging.info("Found year")
        if activityType in content[year]:
            logging.info("Found activity")
            content[year][activityType]['distance']+=distance
            content[year][activityType]['duration']+=duration
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
        return "{} day(s) {}".format(math.floor(seconds/86400),time.strftime("%H:%M:%S", time.gmtime(seconds)))
    elif seconds > 3600:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    else:
        return time.strftime("%M:%S", time.gmtime(seconds))
