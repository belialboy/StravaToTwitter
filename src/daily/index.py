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
from strava import Utils
import gspread

debug = False

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):

    logging.info("Underpants")
    logging.info(event)
    
    year = str(datetime.now().year)
    month = datetime.now().month

    # Get some google connectivity
    googleCredentials = json.loads(Utils.getSSM("GooglePermissions"))
    gc = gspread.service_account_from_dict(googleCredentials)
    
    # Open the spreadsheet
    googleSheetName=Utils.getSSM("GoogleSheetName")
    sheet = gc.open(googleSheetName.split(".")[0])
    
    # Open the worksheet in the spreadsheet
    worksheet = sheet.worksheet("{SHEETPREFIX} {YEAR}".format(SHEETPREFIX=googleSheetName.split(".")[1],YEAR=year))
    
    # List all the athlete Ids that are currently in the sheet
    listOfIds =  worksheet.col_values(1)
    
    # List all the athletes that we currently know about
    AthleteIds = getIds()
    
    for Id in AthleteIds:
    
        logger.info("Working on {}".format(Id))
        strava = Strava(athleteId=Id)
        athlete_record = strava._getAthleteFromDDB()
        if "body" not in athlete_record:
            logger.info("No running so far")
            continue
        body=json.loads(athlete_record['body'])
        logger.info(body)

        if Id in listOfIds:
            logger.info("Found existing athlete")
            if year in body and "Run" in body[year] and "distance" in body[year]['Run']:
                logger.info("Updating YTD for runnner {}".format(Id))
                runningYTD = body[year]['Run']['distance']/1609.34
                cell = worksheet.find(Id, in_column=1)
                worksheet.update_cell(cell.row,month+2 , runningYTD)
            else:
                logger.info("Runner {} has not run this year so far.".format(Id))
        else:
            logger.info("New athlete")
            if year in athlete_record and "Run" in athlete_record[year] and "distance" in athlete_record[year]['Run']:
                logger.info("Adding YTD for runnner {}".format(Id))
                runningYTD = athlete_record[year]['Run']['distance']/1609.34
                strava_athlete = strava.getCurrentAthlete()
                newRow=[Id,"{FIRSTNAME} {LASTNAME}".format(FIRSTNAME=strava_athlete['firstname'],LASTNAME=strava_athlete['lastname'])]
                nonMonths=[0] * month-1
                newRow.extend(nonMonths)
                newRow.append(runningYTD)
                worksheet.insert_row(newRow)
            else:
                logger.info("Athlete {} is new, but has not done any running this year.".format(Id))


    logging.info("Profit!")

def getIds():
    ddb = boto3.resource('dynamodb')
    ddbTable = ddb.Table(os.environ['totalsTable'])
    Ids = ddbTable.scan(ProjectionExpression='Id')
    returnable = []
    for Id in Ids['Items']:
        returnable.append(Id['Id'])
    return returnable