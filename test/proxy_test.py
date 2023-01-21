import unittest
import json
import os

from unittest import mock

class TestProxy(unittest.TestCase):
    
    @unittest.skip('Not ready yet')
    def test_register_redirect(self):
        stream = os.popen('sam local invoke ProxyLambdaFunction -e test/payloads/register_test.json 2> /dev/null')
        output = stream.read()
        stream.close
        print("START{}END".format(output))
        self.assertIsNotNone(output)
        expectation={"statusCode": 301, "headers": {"Location": "https://www.strava.com/oauth/authorize?client_id=pStravaClientId&redirect_uri=https://abcde123456.execute-api.eu-west-1.amazonaws.com/registersuccess/&response_type=code&scope=activity:read_all,activity:write"}, "body": ""}

        self.assertEqual(json.loads(output),expectation)
        
if __name__ == '__main__':
    unittest.main()