#!/usr/bin/env python
import json
# pylint: disable=fixme, import-error
import os
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    if event['httpMethod'] == "GET":
        # Auth for subscription creation
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({'hub.challenge':event['queryStringParameters']['hub.challenge']})
        }
        
    elif event['httpMethod'] == "POST":
        # A posted event from a subscription
        if "body" in event:
            body = json.loads(event['body'])
            
            if "object_type" in body and "aspect_type" in body and body['object_type'] == "activity" and body['aspect_type'] == "create":
                # Async call to the other lamda so we can return fast!
                
                logger.info("Calling ASync lambda")
                lambda_client = boto3.client("lambda")
                
                lambda_client.invoke(FunctionName=os.environ["ASyncLambda"],InvocationType='Event',Payload=event['body'])
            else:
                logger.info("Webhook event is not a new activity")
                
        logging.info("Profit!")
    
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": ""
        }

