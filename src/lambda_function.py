#!/usr/bin/env python
import json
# pylint: disable=fixme, import-error
from twython import Twython
from datetime import datetime
import os
import requests
import boto3
import logging
import hashlib

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
            if "Jonathan Jenkyn" in stravaActivity.text:
                ## Validated
                status = "I did a {TYPE} of {DISTANCEMILES:0.2f}miles ({DISTANCEKM:0.2f}km) in {DURATIONMINS}:{DURATIONSECS} {ACTIVITYURL}".format(TYPE=body['type'],DISTANCEMILES=body['distance']/1609.3444,DISTANCEKM=body['distance']/1000,DURATIONMINS=int(body['duration']/60),DURATIONSECS=body['duration']%60,ACTIVITYURL=body['URL'])
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
