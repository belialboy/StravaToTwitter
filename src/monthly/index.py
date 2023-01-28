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

pGooglePermissions

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    
    year = str(datetime.now().year)
    if datetime.now().day == 1 and datetime.now().month == 1:
        year-=1
    
    AthleteIds = getIds()
    
    for Id in AthleteIds:
    
        strava = Strava(athleteId=Id)
        athlete_record = strava._getAthleteFromDDB()
        # TODO: snag only the year in question details
        # TODO: Write the detail out to a CSV and store in S3
        

    twitter = getTwitterClient()
    if twitter is  None:
        logger.info("No twitter client configured. Bailing.")
        exit()

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

def getIds():
    ddb = boto3.resource('dynamodb')
    ddbTable = ddb.Table(os.environ['totalsTable'])
    Ids = ddbTable.scan(ProjectionExpression='Id')
    returnable = []
    for Id in Ids['Items']:
        returnable.append(Id['Id'])
    return returnable