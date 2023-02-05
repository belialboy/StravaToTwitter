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
from strava import Utils
import traceback

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    twitter = getTwitterClient()
    for record in event['Records']:
    
        debug = False
        if "debug" in record:
            logger.setLevel(logging.DEBUG)
            debug = True
        
        if "stravaId" in os.environ:
          if 'subscription_id' not in record or int(record['subscription_id']) != int(os.environ['stravaId']):
            logger.error("This request does not have the checksum equal to the expected value.") # 'checksum' is obfustication, but it'll do for now
            return
        
        strava = Strava(athleteId=record['owner_id'])
        
        athlete_record = strava._getAthleteFromDDB()
        
        logger.info("Checking for race condition")
        if not debug and "last_activity_id" in athlete_record and record['object_id'] == athlete_record['last_activity_id']:
            logger.info("Bailing as this is a duplicate")
            exit()
        elif not debug:
            strava.updateLastActivity(record['object_id'])
        
        # get the activity details
        activity = strava.getActivity(record['object_id'])
        activity['type'] = activity['type'].replace("Virtual","")
        
        if "body" not in athlete_record:
            content = strava.updateContent({},activity['type'],activity['distance'],activity['elapsed_time'])
        else:
            content = strava.updateContent(json.loads(athlete_record['body']),activity['type'],activity['distance'],activity['elapsed_time'])
        
        strava._updateAthleteOnDB(json.dumps(content))
        
        logger.info(content)
        
        # put the activity into the detail table
        try:
            strava.putDetailActivity(activity)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to add activity {ID}; trying to continue. This event will not be added to the totals.".format(ID=activity['id']))
                            
        else:
            logger.info("Activity stored in detail database ({ID})".format(ID=record['object_id']))
            
        year = str(datetime.now().year)
        
        # build a string to tweet
        time.sleep(5) # Some of the activities take a moment or two to upload their images.
        # Get the activity from strava
        activity = strava.getActivity(record['object_id'])
        activity['type'] = activity['type'].replace("Virtual","")
        
        if twitter is not None:
                
            logger.info("Getting Ready to make a tweet. How exciting!")
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
    
        #Update the activity description
        try:
            result = strava.updateActivityDescription(athlete_year_stats=content[year],latest_event=activity)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to update activity {ID} description; trying to continue.".format(ID=activity['id']))
                            
        else:
            if result:
                logger.info("Strava activity description updated.".format(ID=record['object_id']))
            else:
                logger.info("Strava activity description not updated.".format(ID=record['object_id']))
    
    logging.info("Profit!")
    

def getTwitterClient():
    if Utils.getEnv("ssmPrefix") is not None:
        client = Twython(
                    Utils.getSSM("TwitterConsumerKey"), 
                    Utils.getSSM("TwitterConsumerSecret"),
                    Utils.getSSM("TwitterAccessTokenKey"), 
                    Utils.getSSM("TwitterAccessTokenSecret"))
        return client
    else:
        print("No twitter credentials found, so passing")
    return None