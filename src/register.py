#!/usr/bin/env python
import json
import os
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    
    cloudformation = boto3.client("cloudformation")
    stack = cloudformation.describe_stacks(StackName=os.environ['stackID'])
    redirectUrl = None
    for output in stack['Stacks'][0]['Outputs']:
        if output['OutputKey'] == "RegisterSuccessUrl":
            redirectUrl = output['OutputValue']
            
    returnable = {
        "statusCode": 301,
        "headers": {
           "headers": {"Location": "https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT}&response_type=code&scope=activity:read_all".format(CLIENT_ID=os.environ['stravaClientId'],REDIRECT=redirectUrl), }
        },
        "body": ""
    }
    logging.info(returnable)
    logging.info("Profit!")

    return returnable
