#!/usr/bin/env python
import json
# pylint: disable=fixme, import-error
from twython import Twython
from twython import TwythonAuthError
from datetime import datetime
import time
import requests
import boto3
import logging
import hashlib
import math
from io import BytesIO
from botocore.exceptions import ClientError
from strava import Strava
from strava import Utils
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import sys
import traceback


logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    twitter = getTwitterClient()
    for record in event['Records']:
        
        recordjson = json.loads(record['body'])
        debug = False
        if "debug" in recordjson:
            logger.setLevel(logging.DEBUG)
            debug = True
        
        subscription_id = Utils.getSSM("subscription_id")
        if subscription_id is not None:
          if 'subscription_id' not in recordjson or int(recordjson['subscription_id']) != int(subscription_id):
            logger.error("This request does not have the checksum equal to the expected value.") # 'checksum' is obfustication, but it'll do for now
            return
        
        strava = Strava(athleteId=recordjson['owner_id'])
        
        athlete_record = strava._getAthleteFromDDB()
        if athlete_record is None:
            logger.error("Something has gone wrong. We've recieved an API call for an activity owned by {}, but have no corresponding registration in our DDB table.".format(recordjson['owner_id']))
            continue
        
        logger.info("Checking for race condition")
        if not debug and "last_activity_id" in athlete_record and recordjson['object_id'] == athlete_record['last_activity_id']:
            logger.info("Bailing as this is a duplicate")
            return
        elif not debug:
            strava.updateLastActivity(recordjson['object_id'])
        
        # get the activity details
        activity = strava.getActivity(recordjson['object_id'])
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
            logger.info("Activity stored in detail database ({ID})".format(ID=recordjson['object_id']))
            
        year = str(datetime.now().year)
        
        # build a string to tweet
        # Get the activity from strava
        activity = strava.getActivity(recordjson['object_id'])
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
            spotifyliststring = None
            if hasattr(strava,"spotify"):
                spotifyliststring = getSpotifyTrackList(strava.spotify,activity['start_date'])
                
            result = strava.updateActivityDescription(athlete_year_stats=content[year],latest_event=activity,spotifytracks=spotifyliststring)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to update activity {ID} description; trying to continue.".format(ID=activity['id']))
            
            result = strava.updateActivityDescription(athlete_year_stats=content[year],latest_event=activity)
        except TwythonAuthError as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to update activity {ID} description; trying to continue.".format(ID=activity['id']))
            
            result = strava.updateActivityDescription(athlete_year_stats=content[year],latest_event=activity)
            
        else:
            if result:
                logger.info("Strava activity description updated.".format(ID=recordjson['object_id']))
            else:
                logger.info("Strava activity description not updated.".format(ID=recordjson['object_id']))
                
        
    
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
    
def getSpotifyTrackList(tokens,start_date):
    try:
        spotify_string = None
        logger.debug("Making Spotify client")
        client = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(client_id = tokens['client_id'],client_secret = tokens['client_secret']))
        logger.debug("Making time as msecs")
        dt_msecs = datetime.strptime(start_date,'%Y-%m-%dT%H:%M:%SZ').timestamp() * 1000
        logger.debug("Getting track listing from Spotify")
        track_list = client.current_user_recently_played(limit=50, after=dt_msecs)
        logger.info(track_list)
        if len(track_list) >0:
            spotify_string = "I listened to the following tracks:\n"
            logger.debug("Building tracklist")
            for track in track_list:
                spotify_string+="* {ARTIST} - {TRACK}\n".format(TRACK = track['name'], ARTIST = track['artist'])
    except Exception as e:
        logger.error("Trying to get Spotify track listing")
        logger.error(e)
    logger.debug("Profit!")
    return spotify_string