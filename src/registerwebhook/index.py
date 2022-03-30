from __future__ import print_function
import json, boto3, os
import urllib3
import logging
import requests
import time

SUCCESS = "SUCCESS"
FAILED = "FAILED"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

http = urllib3.PoolManager()

def send(event, context, responseStatus, responseData, physicalResourceId=None, noEcho=False, reason=None):
    responseUrl = event['ResponseURL']

    print(responseUrl)

    responseBody = {
        'Status' : responseStatus,
        'Reason' : reason or "See the details in CloudWatch Log Stream: {}".format(context.log_stream_name),
        'PhysicalResourceId' : physicalResourceId or context.log_stream_name,
        'StackId' : event['StackId'],
        'RequestId' : event['RequestId'],
        'LogicalResourceId' : event['LogicalResourceId'],
        'NoEcho' : noEcho,
        'Data' : responseData
    }

    json_responseBody = json.dumps(responseBody)

    print("Response body:")
    print(json_responseBody)

    headers = {
        'content-type' : '',
        'content-length' : str(len(json_responseBody))
    }

    try:
        response = http.request('PUT', responseUrl, headers=headers, body=json_responseBody)
        print("Status code:", response.status)


    except Exception as e:

        print("send(..) failed executing http.request(..):", e)
        
def updateLambda(new_id):
  logger.info("Updating lambda function ({}) environment variables".format(os.environ['WebhookLambda']))
  lambdaclient=boto3.client("lambda")
  existing=lambdaclient.get_function_configuration(FunctionName=os.environ['WebhookLambda'])
  logger.info("Got the existing variables")
  newvariables = dict(existing['Environment']['Variables'])
  newvariables['stravaId']=new_id
  logger.info("Updating the variables to include the stravaId")
  UpdateRequest=lambdaclient.update_function_configuration(FunctionName=os.environ['WebhookLambda'],Environment={'Variables':newvariables})
  if "Error" in UpdateRequest['Environment']:
    logger.error("Failed to update {}: {} - {}".format(os.environ['WebhookLambda'],UpdateRequest['Environment']['Error']['ErrorCode'],UpdateRequest['Environment']['Error']['Message']))
    return False
  logger.info("Lambda function updated successfully")
  return True
  
  
def registerWebhookWithStrava(stravaBaseURL,WebhookURL,stravaAuthPayload):
  logger.info("Registering {} with strava".format(WebhookURL))
  sts = boto3.client("sts")
  accountNumber=str(sts.get_caller_identity()["Account"])
  stravaAuthPayload.update({"callback_url":WebhookURL,"verify_token":accountNumber})
  
  # Check that the API is acutally deployed
  dudpayload={"hub.verify_token":accountNumber,"hub.challenge":"deadbeef","hub.mode":"subscribe"}
  counter=0
  while True:
    response=requests.get(WebhookURL,params=dudpayload)
    counter+=1
    if response.status_code==200:
      logger.info("Webhook API is enabled")
      break
    if counter > 10:
      logger.error("Webhook API has failed to respond in a timely manner. Breaking.")
      return None

    logger.info("Sleeping for 5seconds to allow {} to come alive".format(WebhookURL))
    time.sleep(5)
    
  NewSubscription=requests.post(stravaBaseURL,stravaAuthPayload)
  if NewSubscription.status_code == 201: # 201 = Created
    logger.info("Successfully Registered")
    return NewSubscription.json()['id']
  else:
    logger.error("Failed to register :( {}".format(NewSubscription.status_code))
    logger.error(NewSubscription.content)
    return None
  
def lambda_handler(event, context):
  data = {}
  stravaBaseURL="https://www.strava.com/api/v3/push_subscriptions"
  status = FAILED
  # Get Current Subscription
  try:
    stravaAuthPayload={"client_id":os.environ['stravaClientId'],"client_secret":os.environ['stravaClientSecret']}
    CurrentSubscription=requests.get(stravaBaseURL,params=stravaAuthPayload)
    if CurrentSubscription.status_code == 200:
      logger.info("Got the Current Subscription from Strava")
      CurrentSubscriptionJson=CurrentSubscription.json()
      logger.info("This is a {} event from Cloudformation".format(event['RequestType']))
      if event['RequestType'] == "Create" or event['RequestType'] == "Update":
        if len(CurrentSubscriptionJson) == 1:
          logger.info("There's an existing subscription")
          if CurrentSubscriptionJson[0]['callback_url'] != os.environ['WebhookURL']:
            logger.info("The current subscription ({}) is not the same as this deployment ({})".format(CurrentSubscriptionJson[0]['callback_url'],os.environ['WebhookURL']))
            logger.info("Deleting current subscription")
            requests.delete(stravaBaseURL+"/"+str(CurrentSubscriptionJson[0]['id']),params=stravaAuthPayload)
            id=registerWebhookWithStrava(stravaBaseURL,os.environ['WebhookURL'],stravaAuthPayload)
            if id is not None:
              if updateLambda(id):
                status = SUCCESS
          else:
            logger.info("Webhook already registered. No need to update")
            status = SUCCESS
        else:
          logger.info("There's no existing subscription")
          id=registerWebhookWithStrava(stravaBaseURL,os.environ['WebhookURL'],stravaAuthPayload)
          if id is not None:
            if updateLambda(id):
              status = SUCCESS
      elif event['RequestType'] == "Delete":
        logger.info("Deleting current subscription")
        requests.delete(stravaBaseURL+"/"+str(CurrentSubscriptionJson[0]['id']),params=stravaAuthPayload)
        status = SUCCESS
  except Exception as e:
    logger.error("Failed!")
    logger.error(e)
  send(event, context, status, {})
