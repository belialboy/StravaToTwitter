#!/usr/bin/env python
import json
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    returnable = {
        "statusCode": 301,
        "headers": {
           "headers": {"Location": "https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT}&response_type=code&scope=activity:read_all".format(CLIENT_ID=os.environ['stravaClientId'],REDIRECT=os.environ['stravaRedirect']), }
        },
        "body": ""
    }
    logging.info(returnable)
    logging.info("Profit!")

    return returnable
