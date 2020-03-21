#!/usr/bin/env python
import json
# pylint: disable=fixme, import-error
from twython import Twython
from datetime import datetime
import os
import requests
import boto3
import logging
import hashlib

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Credentials setup
# Create the Twython Twitter client using our credentials
twitter = Twython(os.environ["twitterConsumerKey"], os.environ["twitterConsumerSecret"],
                  os.environ["twitterAccessTokenKey"], os.environ["twitterAccessTokenSecret"])

def lambda_handler(event, context):
    """Reads from twitter and posts to chime webhook"""

    logging.info("Underpants")

    # Check that this is an API call from IFTTT

    # Grab the image at the end of the ImageURL

    # Push the image into S3

    # Create a PSU for the Image

    # Post a tweet into Twitter with all the deets of the run

    logging.info("Profit!")