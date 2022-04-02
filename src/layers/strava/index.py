import json
import time
import logging
import requests
import boto3


logger = logging.getLogger()
logger.setLevel(logging.INFO)

PAUSE = 1 #second
RETRIES = 5

class Strava:
    
    def __init__(self,tokens: dict, stravaAtheleteId: int,stravaClientId: str, stravaClientSecret: str,ddbTableName: str):
        self.stravaClientId = stravaClientId
        self.stravaClientSecret = stravaClientSecret
        self.tokens = tokens
        self.ddbTableName = ddbTableName
        self.stravaAtheleteId = stravaAtheleteId
        
        self.refreshTokens()
        
    def refreshTokens(self):
        if int(time.time()) > int(self.tokens['expires_at']):
            logger.info("Need to refresh Strava Tokens")
            data = {
                'client_id': self.stravaClientId,
                'client_secret': self.stravaClientSecret,
                'grant_type': "refresh_token",
                'refresh_token': self.tokens['refresh_token']
            }
            
            response = requests.post("https://www.strava.com/oauth/token", json=data)
            
            if response.status_code == 200:
                
                logger.info("Got new Strava tokens")
                dynamodb = boto3.resource('dynamodb')
                table = dynamodb.Table(self.ddbTableName)
                
                self.tokens = {"expires_at":response.json()['expires_at'],"access_token":response.json()['access_token'],"refresh_token":response.json()['refresh_token']}
    
                table.update_item(
                    Key={
                        'Id': str(self.stravaAtheleteId)
                    },
                    UpdateExpression="set tokens=:c",
                    ExpressionAttributeValues={
                        ':c': json.dumps(self.tokens)
                    }
                )
            else:
                logger.error("Failed to get refreshed tokens")
                logger.error(response.raw)
                exit()
                
    def _get(self,endpoint):
        while True:
            counter = 0
            try:
                self.refreshTokens()
                activity = requests.get(
                    endpoint,
                    headers={'Authorization':"Bearer {ACCESS_TOKEN}".format(ACCESS_TOKEN=self.tokens['access_token'])}
                    )
                if activity.status_code == 200:
                    return activity.json()
                elif counter == RETRIES:
                    logger.error("Get failed even after retries")
                    logger.error("{} - {}".format(activity.status_code,activity.content))
                    exit()
                else:
                    counter+=1
                    time.sleep(PAUSE)
            except Exception as e:
                logger.error("An Exception occured while getting {} ".format(endpoint))
                logger.error(e)
                exit()
                
    def getActivity(self,activityId):
        endpoint = "https://www.strava.com/api/v3/activities/{ID}".format(ID=activityId)
        return(self._get(endpoint))
        
    def getCurrentAthlete(self):
        endpoint = "https://www.strava.com/api/v3/athlete"
        return(self._get(endpoint))
        