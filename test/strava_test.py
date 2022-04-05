import unittest
import json

from src.layers.strava.src.python.strava import Strava
from unittest import mock

class TestStrava(unittest.TestCase):

  def test_normal_constructor(self):
    with mock.patch.object(Strava, '_getAthleteFromDDB') as mock_method:
      tokens={"expires_at":1234567890,"access_token":"abcdef1234567890","refresh_token":"0987654321fedcba"}
      mock_method.return_value = {"tokens": json.dumps(tokens)}
      strava=Strava(stravaClientId="DEADBEEF", stravaClientSecret="FEEDBEEF",ddbTableName="Dynamo", athleteId = 1234567)
      self.assertEqual(strava.tokens["expires_at"],tokens['expires_at'])
      self.assertEqual(strava.stravaClientId,"DEADBEEF")
      self.assertEqual(strava.stravaClientSecret,"FEEDBEEF")
      self.assertEqual(strava.ddbTableName,"Dynamo")
      self.assertEqual(strava.athleteId,1234567)

  def test_new_constructor(self):
    with mock.patch.object(Strava, '_newAthlete') as mock_method:
        mock_method.return_value = None
        strava=Strava(auth="codeToken",stravaClientId="DEADBEEF", stravaClientSecret="FEEDBEEF",ddbTableName="Dynamo")
        self.assertEqual(strava.stravaClientId,"DEADBEEF")
        self.assertEqual(strava.stravaClientSecret,"FEEDBEEF")
        self.assertEqual(strava.ddbTableName,"Dynamo")

  def test_secsToStr(self):
    with mock.patch.object(Strava, '_getAthleteFromDDB') as mock_method:
      tokens={"expires_at":1234567890,"access_token":"abcdef1234567890","refresh_token":"0987654321fedcba"}
      mock_method.return_value = {"tokens": json.dumps(tokens)}
      strava=Strava(stravaClientId="DEADBEEF", stravaClientSecret="FEEDBEEF",ddbTableName="Dynamo", athleteId = 1234567)
      self.assertEqual(strava.secsToStr(1),"00 minutes and 01 seconds")
      self.assertEqual(strava.secsToStr(60),"01 minutes and 00 seconds")
      self.assertEqual(strava.secsToStr(61),"01 minutes and 01 seconds")
      self.assertEqual(strava.secsToStr(600),"10 minutes and 00 seconds")
      self.assertEqual(strava.secsToStr(3601),"01hr 00mins 01seconds")
      self.assertEqual(strava.secsToStr(36000),"10hr 00mins 00seconds")
      self.assertEqual(strava.secsToStr(86401),"1 day(s) 00h 00m 01s")
      self.assertEqual(strava.secsToStr(122400),"1 day(s) 10h 00m 00s")
    
if __name__ == '__main__':
    unittest.main()