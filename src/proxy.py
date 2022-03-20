#!/usr/bin/env python
import json
import os
import logging
import requests
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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

    if "/register/" in event['requestContext']['resourcePath']:
        # do the register path
        
        returnable = {
            "statusCode": 301,
            "headers": {
               "headers": {"Location": "https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT}&response_type=code&scope=activity:read_all".format(CLIENT_ID=os.environ['stravaClientId'],REDIRECT=os.environ['redirectUrl']), }
            },
            "body": ""
        }

    elif "/registersuccess/" in event['requestContext']['resourcePath']:
        # do request Success path
        returnable = {
                "statusCode": 400,
                "headers": {
                  "Content-Type": "text/html"
                },
                "body": "Body had no event. Failed to register. See logs."
            }
                
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
                
                returnable = {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "text/html"
                    },
                    "body": "Done!"
                }
                
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
            
        
    elif "/webhook/" in event['requestContext']['resourcePath']:
        # Do the webhook
        if event['httpMethod'] == "GET":
            # Auth for subscription creation
            returnable = {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({'hub.challenge':event['queryStringParameters']['hub.challenge']})
            }
            
        elif event['httpMethod'] == "POST":
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
                    lambda_client = boto3.client("lambda")
                    
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

    logging.info(returnable)
    logging.info("Profit!")
    
    return returnable