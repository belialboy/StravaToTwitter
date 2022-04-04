import unittest
import json
import os

from unittest import mock

class TestProxy(unittest.TestCase):
    
    def test_register_redirect(self):
        stream = os.popen('sam local invoke ProxyLambdaFunction -e test/payloads/register_test.json 2> /dev/null')
        output = stream.read()
        stream.close()
        expectation={"statusCode": 301, "headers": {"Location": "https://www.strava.com/oauth/authorize?client_id=pStravaClientId&redirect_uri=https://abcde123456.execute-api.eu-west-1.amazonaws.com/registersuccess/&response_type=code&scope=activity:read_all"}, "body": ""}

        self.assertEqual(json.loads(output),expectation)
        
if __name__ == '__main__':
    unittest.main()