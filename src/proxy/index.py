#!/usr/bin/env python
import json
import os
import logging
import requests
import boto3
import datetime
from strava import Strava

logger = logging.getLogger()
logger.setLevel(logging.INFO)

lambda_client = boto3.client("lambda")

def lambda_handler(event, context):
    
    logging.info("Underpants")
    logging.info(event)
    
    returnable = {
        "statusCode": 200,
        "headers": {
          "Content-Type": "text/html"
        },
        "body": "PassThru"
    }
        
    if "/register/" in event['rawPath']:
        # do the register path
        logger.info("register path")
        
        redirectUrl = 'https://{DOMAIN}/registersuccess/'.format(DOMAIN=event['requestContext']['domainName'])
        
        logger.info(redirectUrl)
        
        returnable = {
            "statusCode": 301,
            "headers": {
               "Location": "https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT}&response_type=code&scope=activity:read_all".format(CLIENT_ID=os.environ['stravaClientId'],REDIRECT=redirectUrl)
            },
            "body": ""
        }

    elif "/registersuccess/" in event['rawPath']:
        # do request Success path
        logger.info("registersuccess path")
        returnable = {
                "statusCode": 400,
                "headers": {
                  "Content-Type": "text/html"
                },
                "body": "Body had no event. Failed to register. See logs."
            }
           
        if "queryStringParameters" in event and "code" in event['queryStringParameters']:
            try:
                strava = Strava(auth=event['queryStringParameters']['code'],stravaClientId=os.environ['stravaClientId'],stravaClientSecret=os.environ['stravaClientSecret'],ddbTableName=os.environ["totalsTable"])
                dynamodb = boto3.resource('dynamodb')
                table = dynamodb.Table(os.environ["totalsTable"])
                table.update_item(
                    Key={'Id': str(strava.athleteId)},
                    UpdateExpression="set twitter=:c",
                    ExpressionAttributeValues={
                        ':c': json.dumps({
                              "twitterConsumerKey": os.environ["twitterConsumerKey"], 
                              "twitterConsumerSecret": os.environ["twitterConsumerSecret"],
                              "twitterAccessTokenKey": os.environ["twitterAccessTokenKey"], 
                              "twitterAccessTokenSecret": os.environ["twitterAccessTokenSecret"]})
                    }
                )            
            
                returnable = {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "text/html"
                    },
                    "body": "Done! You're all registered!"
                }
            
            except ConnectionError as e:
                logger.error("Failed to authenticate the athlete")
                logger.error(e)
            
                
        else:
            logger.error("Missing queryStringParameters to make sense of call expectations")
            
        
    elif "/webhook/" in event['rawPath']:
        # Do the webhook
        logger.info("webhook path")
        if event['requestContext']['http']['method'] == "GET":
            # Auth for subscription creation
            if "queryStringParameters" in event and "hub.challenge" in event['queryStringParameters']:
                sts = boto3.client("sts")
                if "hub.verify_token" not in event ['queryStringParameters'] or event['queryStringParameters']['hub.verify_token'] != str(sts.get_caller_identity()["Account"]):
                    logger.error("hub.verify_token is not equal to the account number. Bailing.")
                    returnable = {
                        "statusCode": 403,
                        "headers": {
                            "Content-Type": "application/json"
                        },
                        "body": "Verification token does not match expected value. :("
                    }
                else:
                    logger.info("Happy to verify the subscription")
                    returnable = {
                        "statusCode": 200,
                        "headers": {
                            "Content-Type": "application/json"
                        },
                        "body": json.dumps({'hub.challenge':event['queryStringParameters']['hub.challenge']})
                    }
            
            
        elif event['requestContext']['http']['method'] == "POST":
            # A posted event from a subscription
            returnable = {
                    "statusCode": 400,
                    "headers": {
                      "Content-Type": "text/html"
                    },
                    "body": "Body had no event. Failed to register. See logs."
                }
            if "body" in event:
                body = json.loads(event['body'])
                if "object_type" in body and "aspect_type" in body and body['object_type'] == "activity" and body['aspect_type'] == "create":
                    # Async call to the other lamda so we can return fast!
                    
                    logger.info("Calling ASync lambda")
                    lambda_client.invoke(FunctionName=os.environ["webhookASync"],InvocationType='Event',Payload=event['body'])
                else:
                    logger.info("Webhook event is not a new activity")
                    
                returnable = {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "text/html"
                    },
                    "body": "Done!"
                }
                
    else:
        logger.error("No path matched")
        returnable = {
                    "statusCode": 400,
                    "headers": {
                      "Content-Type": "text/html"
                    },
                    "body": "No path matched. See logs. Doh!"
                }

    logging.info(returnable)
    logging.info("Profit!")
    
    return returnable
