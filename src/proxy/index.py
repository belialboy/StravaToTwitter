#!/usr/bin/env python
import json
import os
import logging
import requests
import boto3
import datetime

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
           
        if "queryStringParameters" in event:
            data = {
                'client_id': os.environ['stravaClientId'],
                'client_secret': os.environ['stravaClientSecret'],
                'code': event['queryStringParameters']['code'],
                'grant_type': "authorization_code"
            }
            response = requests.post("https://www.strava.com/oauth/token", json=data)
            if response.status_code == 200:
                # write the token to the DDB
                logger.info(response.json())
                athleteId = str(response.json()['athlete']['id'])
                tokens = json.dumps({"expires_at":response.json()['expires_at'],"access_token":response.json()['access_token'],"refresh_token":response.json()['refresh_token']})
                dynamodb = boto3.resource('dynamodb')
                table = dynamodb.Table(os.environ["totalsTable"])
                logger.info("Checking to see if the athlete is already registered")
                athelete_record = table.get_item(Key={'Id': athleteId})
                if 'Item' in athelete_record:
                    logger.info("Updating the tokens in the users entry rather than overwriting existing data")
                    table.update_item(
                        Key={'Id': athleteId},
                        UpdateExpression="set tokens=:c",
                        ExpressionAttributeValues={':c': tokens}
                    )
                else:
                    # Get any existing data for runs, rides or swims they may have done, and add these as the starting status for the body element
                    logger.info("Net new athelete. Welcome!")
                    body_as_string="{}"
                    try:
                        athelete_detail = requests.get(
                            "https://www.strava.com/api/v3/athletes/{ID}/stats".format(ID=athleteId),
                            headers={'Authorization':"Bearer {ACCESS_TOKEN}".format(ACCESS_TOKEN=response.json()['access_token'])}
                            )
                        current_year = str(datetime.datetime.now().year)
                        data_to_add = {}
                        athelete_detail_json = athelete_detail.json()
                        if athelete_detail_json['ytd_ride_totals']['count']>0:
                            data_to_add['Ride']={"distance":athelete_detail_json['ytd_ride_totals']['distance'],"duration":athelete_detail_json['ytd_ride_totals']['elapsed_time'],"count":athelete_detail_json['ytd_ride_totals']['count']}
                        if athelete_detail_json['ytd_run_totals']['count']>0:
                            data_to_add['Run']={"distance":athelete_detail_json['ytd_run_totals']['distance'],"duration":athelete_detail_json['ytd_run_totals']['elapsed_time'],"count":athelete_detail_json['ytd_run_totals']['count']}
                        if athelete_detail_json['ytd_swim_totals']['count']>0:
                            data_to_add['Swim']={"distance":athelete_detail_json['ytd_swim_totals']['distance'],"duration":athelete_detail_json['ytd_swim_totals']['elapsed_time'],"count":athelete_detail_json['ytd_swim_totals']['count']}
                        if len(data_to_add)>0:
                            body_as_string=json.dumps({current_year:data_to_add})
                    except Exception as e:
                        logger.error("Failed to collect details about the athletes previous activity. Sorry")
                        logger.error(e)
                        
                    table.put_item(
                         Item={
                              'Id': athleteId,
                              'tokens': tokens,
                              'body': body_as_string,
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
                    "body": "Done! You're all registered!"
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
