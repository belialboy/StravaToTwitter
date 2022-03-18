#!/usr/bin/env python
import json
import os
import logging
import requests
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    returnable = {
        "statusCode": 200,
        "headers": {
          "Content-Type": "application/json"
        },
        "body": "Registered"
    }

    logging.info("Underpants")
    logging.info(event)
    
    if "body" in event:
        body = json.loads(event['body'])
        data = {
            'client_id': os.environ['stravaClientId'],
            'client_secret': os.environ['stravaClientSecret'],
            'code': body['code'],
            'grant_type': "authorization_code"
        }
        response = requests.post("https://www.strava.com/oauth/token", json=data)
        if response.status_code == 200:
            # write the token to the DDB
            logger.info(response.json())
            atheleteId = str(response.json()['athelete']['id'])
            tokens = json.dumps({"expires_at":response.json()['expires_at'],"access_token":response.json()['access_token'],"refresh_token":response.json()['refresh_token']})
            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(os.environ["totalsTable"])
            table.put_item(
                 Item={
                      'Id': atheleteId,
                      'tokens': tokens,
                      'body': "{}",
                      'twitter': json.dumps({
                          "twitterConsumerKey": os.environ["twitterConsumerKey"], 
                          "twitterConsumerSecret": os.environ["twitterConsumerSecret"],
                          "twitterAccessTokenKey": os.environ["twitterAccessTokenKey"], 
                          "twitterAccessTokenSecret": os.environ["twitterAccessTokenSecret"]})
                  })
            
        else:
            logger.error(response.status_code)
            logger.error(response.content)
            returnable = {
                "statusCode": 400,
                "headers": {
                  "Content-Type": "text/html"
                },
                "body": "Failed to register. See logs."
            }
    
    logging.info(returnable)
    logging.info("Profit!")

    return returnable
