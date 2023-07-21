import unittest
import json

from src.layers.strava.src.python.strava import Strava
from src.layers.strava.src.python.strava import Utils


from unittest import mock
from unittest.mock import patch

class TestStrava(unittest.TestCase):
  @patch('src.layers.strava.src.python.strava.Utils.getEnv')
  @patch('src.layers.strava.src.python.strava.Utils.getSSM')
  @patch('src.layers.strava.src.python.strava.Strava._getAthleteFromDDB')
  def test_normal_constructor(self,getAthleteFromDDB,getSSM,getEnv):
    tokens={"expires_at":1234567890,"access_token":"abcdef1234567890","refresh_token":"0987654321fedcba"}
    getAthleteFromDDB.return_value = {"tokens": json.dumps(tokens)}
    getSSM.return_value = "DEADBEEF"
    getEnv.return_value = "Dynamo"
  
    strava=Strava(athleteId = 1234567)
    self.assertEqual(strava.tokens["expires_at"],tokens['expires_at'])
    self.assertEqual(strava.stravaClientId,"DEADBEEF")
    self.assertEqual(strava.stravaClientSecret,"DEADBEEF")
    self.assertEqual(strava.ddbTableName,"Dynamo")
    self.assertEqual(strava.athleteId,1234567)

  @patch('src.layers.strava.src.python.strava.Utils.getEnv')
  @patch('src.layers.strava.src.python.strava.Utils.getSSM')
  @patch('src.layers.strava.src.python.strava.Strava._newAthlete')
  def test_new_constructor(self,newAthlete,getSSM,getEnv):
    getSSM.return_value = "DEADBEEF"
    getEnv.return_value = "Dynamo"
    newAthlete.return_value = None
    
    strava=Strava(auth="codeToken")
    self.assertEqual(strava.stravaClientId,"DEADBEEF")
    self.assertEqual(strava.stravaClientSecret,"DEADBEEF")
    self.assertEqual(strava.ddbTableName,"Dynamo")

  @patch('src.layers.strava.src.python.strava.Utils.getEnv')
  @patch('src.layers.strava.src.python.strava.Utils.getSSM')
  def test_secsToStr(self,getSSM,getEnv):
    getSSM.return_value = "DEADBEEF"
    getEnv.return_value = "1234"
    with mock.patch.object(Strava, '_getAthleteFromDDB') as mock_method:
      tokens={"expires_at":1234567890,"access_token":"abcdef1234567890","refresh_token":"0987654321fedcba"}
      mock_method.return_value = {"tokens": json.dumps(tokens)}
      strava=Strava(athleteId = 1234567)
      self.assertEqual(Utils.secsToStr(1),"00m01s")
      self.assertEqual(Utils.secsToStr(60),"01m00s")
      self.assertEqual(Utils.secsToStr(61),"01m01s")
      self.assertEqual(Utils.secsToStr(600),"10m00s")
      self.assertEqual(Utils.secsToStr(3601),"01h00m01s")
      self.assertEqual(Utils.secsToStr(36000),"10h00m00s")
      self.assertEqual(Utils.secsToStr(86401),"1 day 00h00m")
      self.assertEqual(Utils.secsToStr(122400),"1 day 10h00m")
  
  @patch('src.layers.strava.src.python.strava.Utils.getEnv')
  @patch('src.layers.strava.src.python.strava.Utils.getSSM')
  @patch('src.layers.strava.src.python.strava.Strava._getAthleteFromDDB')
  @patch('src.layers.strava.src.python.strava.Strava.getCurrentAthlete')
  def test_makeTwitterStatus(self,getCurrentAthlete,getAthleteFromDDB,getSSM,getEnv):
    tokens={"expires_at":1234567890,"access_token":"abcdef1234567890","refresh_token":"0987654321fedcba"}
    getAthleteFromDDB.return_value = {"tokens": json.dumps(tokens)}
    getCurrentAthlete.return_value = {"firstname": "Jonathan", "lastname": "Jenkyn"}
    getSSM.return_value = "DEADBEEF"
    getEnv.return_value = "1234"
    with open('test/payloads/ddb_body.json') as json_file:
      body = json.load(json_file)
    strava=Strava(athleteId = 1234567)
    latest = {"type": "Ride", 'distance': 10000, 'moving_time': 3600, "id": 123, "name": "blah", "start_date_local": "2022-12-23T12:00:00Z"}
    twitterString = strava.makeTwitterString(body["2022"],latest)
    self.assertIn("Jonathan Jenkyn did a ride of 6.22miles / 10.00km in 01h00m00s at 6.2mph / 10.0kmph - https://www.strava.com/activities/123\nYTD for 60 rides 62.15miles / 100.00km in 1 day 00h00m",twitterString)
    self.assertIn("🙌",twitterString)
    self.assertIn("🔥",twitterString)
    self.assertIn("🌍",twitterString)
    self.assertIn("🔟",twitterString)
    self.assertIn("🤩",twitterString)
    self.assertIn("💨",twitterString)
    self.assertIn("⏱️",twitterString)
  
  @patch('src.layers.strava.src.python.strava.Utils.getEnv')
  @patch('src.layers.strava.src.python.strava.Utils.getSSM')
  @patch('src.layers.strava.src.python.strava.Strava._getAthleteFromDDB')
  @patch('src.layers.strava.src.python.strava.Strava.getCurrentAthlete')
  def test_makeTwitterStatusWithZwift(self,getCurrentAthlete,getAthleteFromDDB,getSSM,getEnv):
    tokens={"expires_at":1234567890,"access_token":"abcdef1234567890","refresh_token":"0987654321fedcba"}
    getAthleteFromDDB.return_value = {"tokens": json.dumps(tokens)}
    getCurrentAthlete.return_value = {"firstname": "Jonathan", "lastname": "Jenkyn"}
    getSSM.return_value = "DEADBEEF"
    getEnv.return_value = "1234"
    with open('test/payloads/ddb_body.json') as json_file:
      body = json.load(json_file)
    strava=Strava(athleteId = 1234567)
    latest = {"type": "Ride", 'distance': 10000, 'moving_time': 3600, "id": 123, "device_name": "Zwift", "name": "blah", "start_date_local": "2022-12-23T12:00:00Z"}
    twitterString = strava.makeTwitterString(body["2022"],latest)
    
    self.assertIn("Jonathan Jenkyn did a ride of 6.22miles / 10.00km in 01h00m00s at 6.2mph / 10.0kmph - https://www.strava.com/activities/123\nYTD for 60 rides 62.15miles / 100.00km in 1 day 00h00m",twitterString)
    self.assertIn("🙌",twitterString)
    self.assertIn("🔥",twitterString)
    self.assertIn("🌍",twitterString)
    self.assertIn("🔟",twitterString)
    self.assertIn("🤩",twitterString)
    self.assertIn("💨",twitterString)
    self.assertIn("⏱️",twitterString)
    self.assertIn("#RideOn @GoZwift",twitterString)
  
  @patch('src.layers.strava.src.python.strava.Utils.getEnv')
  @patch('src.layers.strava.src.python.strava.Utils.getSSM')
  def test_recoveryTime(self,getSSM,getEnv):
    getSSM.return_value = "DEADBEEF"
    getEnv.return_value = "1234"
    with mock.patch.object(Strava, '_getAthleteFromDDB') as mock_method:
      tokens={"expires_at":1234567890,"access_token":"abcdef1234567890","refresh_token":"0987654321fedcba"}
      mock_method.return_value = {"tokens": json.dumps(tokens)}
      strava=Strava(athleteId = 1234567)
      self.assertEqual(strava.getEffortQ({'average_heartrate':120,'moving_time':60*60}),(129600 / (4*24*60*60)) * 100.0)
      self.assertEqual(strava.getEffortQ({'average_heartrate':180,'moving_time':60*60*3}),(345600 / (4*24*60*60)) * 100.0)

  
if __name__ == '__main__':
    unittest.main()
