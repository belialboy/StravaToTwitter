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
from io import BytesIO
from botocore.exceptions import ClientError
from strava import Strava

debug = False

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    
    if "stravaId" in os.environ:
      if 'subscription_id' not in event or int(event['subscription_id']) != int(os.environ['stravaId']):
        logger.error("This request does not have the subscription_id equal to the expected value.")
        return
    
    strava = Strava(athleteId=event['owner_id'])
    
    athlete_record = strava._getAthleteFromDDB()
    
    logger.info("Checking for race condition")
    if "last_activity_id" in athlete_record and event['object_id'] == athlete_record['last_activity_id']:
        logger.info("Bailing as this is a duplicate")
        exit()
    else:
        strava.updateLastActivity(event['object_id'])
    
    # get the activity details
    activity = strava.getActivity(event['object_id'])
    activity['type'] = activity['type'].replace("Virtual","")
    # put the activity into the detail table
    try:
        strava.putDetailActivity(activity)
    except Exception as e:
        logger.error("Failed to add activity {ID} to the details table".format(ID=event['object_id']))
    
    if "body" not in athlete_record:
        content = strava.updateContent({},activity['type'],activity['distance'],activity['elapsed_time'])
    else:
        content = strava.updateContent(json.loads(athlete_record['body']),activity['type'],activity['distance'],activity['elapsed_time'])
    
    strava._updateAthleteOnDB(json.dumps(content))
    
    logger.info(content)

    twitter = getTwitterClient()
    if twitter is  None:
        logger.info("No twitter client configured. Bailing.")
        exit()
        
    year = str(datetime.now().year)
    status = strava.makeTwitterString(athlete_year_stats=content[year],latest_event=activity)
    
    if status is not None:
        logging.info(status)
        if ("photos" in activity and 
            "primary" in activity['photos'] and 
            activity['photos']['primary'] is not None and 
            "urls" in activity['photos']['primary'] and 
            "600" in activity['photos']['primary']['urls']):
                
                image = requests.get(activity['photos']['primary']['urls']['600'])
                if image.status_code == 200:
                    try:
                        photo = BytesIO(image.content)
                        twitterImage = twitter.upload_media(media=photo)
                    except Exception as e:
                        logger.error("Failed to upload media from {} to twitter".format(activity['photos']['primary']['urls']['600']))
                        logger.error(e)
                        logger.error("Bailing on trying to use media, and now just tweeting the status without media")
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
        logging.info("Tweet published")
    else:
        logging.info("Not tweeting this time... nothing special!")

    logging.info("Profit!")
    
def getTwitterClient():
    if "ssmPrefix" in os.environ:
        ssm = boto3.client("ssm")
        credentials={}
        credentials['twitterConsumerKey'] = ssm.get_parameter(Name="{}TwitterConsumerKey".format(os.environ['ssmPrefix']))['Parameter']['Value']
        credentials['twitterConsumerSecret'] = ssm.get_parameter(Name="{}TwitterConsumerSecret".format(os.environ['ssmPrefix']))['Parameter']['Value']
        credentials['twitterAccessTokenKey'] = ssm.get_parameter(Name="{}TwitterAccessTokenKey".format(os.environ['ssmPrefix']))['Parameter']['Value']
        credentials['twitterAccessTokenSecret'] = ssm.get_parameter(Name="{}TwitterAccessTokenSecret".format(os.environ['ssmPrefix']))['Parameter']['Value']
        client = Twython(credentials["twitterConsumerKey"], 
            credentials["twitterConsumerSecret"],
            credentials["twitterAccessTokenKey"], 
            credentials["twitterAccessTokenSecret"])
        return client
    else:
        print("No twitter credentials found, so passing")
