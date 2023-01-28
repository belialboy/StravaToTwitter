import time
import boto3
import logging
import os
import math
from twython import Twython

logger = logging.getLogger()

logging.getLogger()
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")

class Utils(object):
    
    @staticmethod
    def getSSM(parameterName):
        parameterFullName="{PREFIX}{PARAMNAME}".format(PREFIX=Utils.getEnv('ssmPrefix'),PARAMNAME=parameterName)
        logger.info("Getting {PARAM} from parameter store".format(PARAM=parameterName))
        try:
            return ssm.get_parameter(Name=parameterFullName)['Parameter']['Value']
        except:
            logger.error("No {PARAM} set in SSM parameter storre".format(PARAM=parameterFullName))
            return None
    
    @staticmethod
    def getEnv(variableName):
        if variableName in os.environ:
            return os.environ[variableName]
        logger.error("No {VAR} set in lambda environment".format(VAR=variableName))
        return None
    
    @staticmethod
    def secsToStr(seconds):
        if seconds > (86400*2)-1:
            return "{} days {}".format(math.floor(seconds/86400),time.strftime("%Hh", time.gmtime(seconds)))
        elif seconds > 86400-1:
            return "1 day {}".format(time.strftime("%Hh%Mm", time.gmtime(seconds)))
        elif seconds > 3600-1:
            return time.strftime("%Hh%Mm%Ss", time.gmtime(seconds))
        else:
            return time.strftime("%Mm%Ss", time.gmtime(seconds))
    
    @staticmethod        
    def secAndMetersToMPH( meters, seconds):
        if seconds == 0:
            return float('{:.1f}'.format(0))
            
        miles = meters/1609
        hours = seconds/3600
        
        mph = miles/hours
        
        return float('{:.1f}'.format(mph))
    
    @staticmethod    
    def secAndMetersToKmPH(meters, seconds):
        if seconds == 0:
            return float('{:.1f}'.format(0))
        
        km = meters/1000
        hours = seconds/3600
        
        kmph = km/hours
        
        return float('{:.1f}'.format(kmph))
    
    @staticmethod    
    def getMinMiles(seconds, meters):
        if seconds == 0 or meters == 0:
            return "0:00"
        
        minMile = 26.8224 / (meters/seconds)
        
        return "{MIN}:{SEC:02}".format(MIN=int(minMile//1),SEC=int((minMile%1)*60))
    
    @staticmethod    
    def getMinKm(seconds, meters):
        if seconds == 0 or meters == 0:
            return "0:00"
            
        minKm = ((seconds/60)/(meters/1000))
        
        return "{MIN}:{SEC:02}".format(MIN=int(minKm//1),SEC=int((minKm%1)*60))
    
    @staticmethod
    def getTwitterClient():
        if Utils.getEnv("ssmPrefix") is not None:
            client = Twython(
                        Utils.getSSM("TwitterConsumerKey"), 
                        Utils.getSSM("TwitterConsumerSecret"),
                        Utils.getSSM("TwitterAccessTokenKey"), 
                        Utils.getSSM("TwitterAccessTokenSecret"))
            return client
        else:
            print("No twitter credentials found, so passing")
        return None