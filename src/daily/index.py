#!/usr/bin/env python
import json
# pylint: disable=fixme, import-error
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
    listOfNames = worksheet.col_values(2)
    
    # List all the athletes that we currently know about
    AthleteIds = getIds()
    
    stravaClientId=Utils.getSSM("StravaClientId")
    stravaClientSecret=Utils.getSSM("StravaClientSecret")
    
    for Id in AthleteIds:
        runningYTD=0.0
        logger.info("Working on {}".format(Id))
        strava = Strava(athleteId=Id,stravaClientId=stravaClientId,stravaClientSecret=stravaClientSecret)
        athlete_record = strava._getAthleteFromDDB()
        if "body" not in athlete_record:
            logger.info("No running so far")
            continue
        body=json.loads(athlete_record['body'])
        logger.info(body)

        if Id in listOfIds:
            logger.info("Found existing athlete")
            if year in body:
                logger.info("Updating YTD for runnner {}".format(Id))
                runningYTD = calculateYTDmiles(body[year])
            else:
                logger.info("Runner {} has not run this year so far.".format(Id))
            cell = worksheet.find(Id, in_column=1)
            worksheet.update_cell(cell.row,month+2 , runningYTD)
        else:
            logger.info("New athlete")
            strava_athlete = strava.getCurrentAthlete()
            fullName="{FIRSTNAME} {LASTNAME}".format(FIRSTNAME=strava_athlete['firstname'],LASTNAME=strava_athlete['lastname'])
            if fullName in listOfNames:
                cell = worksheet.find(fullName, in_column=2)
                worksheet.update_cell(cell.row,1, Id)
                if year in body:
                    logger.info("Updating YTD for runnner {}".format(Id))
                    runningYTD = calculateYTDmiles(body[year])
                else:
                    logger.info("Runner {} has not run this year so far.".format(Id))
                worksheet.update_cell(cell.row,month+2 , runningYTD)
            else:
                newRow=[Id,fullName]
                if year in body:
                    logger.info("Adding YTD for runnner {}".format(Id))
                    runningYTD = calculateYTDmiles(body[year])
                    nonMonths=[0] * (month-1)
                    newRow.extend(nonMonths)
                    newRow.append(runningYTD)
                else:
                    logger.info("Athlete {} is new, but has not done any running this year.".format(Id))
                    strava_athlete = strava.getCurrentAthlete()
                    newRow=[Id,"{FIRSTNAME} {LASTNAME}".format(FIRSTNAME=strava_athlete['firstname'],LASTNAME=strava_athlete['lastname'])]
                    nonMonths=[0] * (month)
                    newRow.extend(nonMonths)
                worksheet.insert_row(newRow,index=len(listOfNames)+1)
            listOfNames.append(fullName)

    logging.info("Profit!")
    
def calculateYTDmiles(body):
    walk = 0
    if 'Walk' in body:
        walk = body['Walk']['distance']
    
    run = 0
    if 'Run' in body:
        run = body['Run']['distance']
    
    ytd = run/1609.34
    if walk > run:
        ytd = (run + walk)/1609.34
        
    return ytd

def getIds():
    ddb = boto3.resource('dynamodb')
    ddbTable = ddb.Table(os.environ['totalsTable'])
    Ids = ddbTable.scan(ProjectionExpression='Id')
    returnable = []
    for Id in Ids['Items']:
        returnable.append(Id['Id'])
    return returnable