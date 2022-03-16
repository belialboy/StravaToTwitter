# StravaToTwitter

## Prerequisites

To get this to function for your Strava and Twitter you will need the following:
* [Twitter Developer](https://developer.twitter.com/en/portal/dashboard) App Keys 
    * Specifically you will need (keep these to yourself and don't check them in anywhere or share them):
        * Twitter Consumer Key
        * Twitter Consumer Secret
        * Twitter Access Token Key
        * Twitter Access Token Secret
* [Strava Developer](https://www.strava.com/settings/api)
    * You'll need to obtain a `ClientId` and `ClientSecret` for the Application.
* An [AWS](https://aws.amazon.com/) account (You'll be spending less than a few cent per month, so won't break the bank)
    * You'll also need the [Serverless Application Model](https://aws.amazon.com/serverless/sam/) CLI installed either on your machine, or in a [Cloud9](https://aws.amazon.com/cloud9/) environment in your AWS Account.
    * An AWS Role in that account that you can assume to run the cloud formation used by SAM
    * `git` installed on your command line

## Install

Clone this repository:

`git clone https://github.com/belialboy/StravaToTwitter && cd StravaToTwitter`

Build the SAM assets:

`sam build`

Deploy the SAM assets:

`sam deploy -g`

This will then guide you through entering your twitter keys (mentioned above) and and Strava App id/secret. 

Once complete you will need to add a subscription to the Strava Webhook API using the following, replacing the client_id and client_secret with those you captured above and the callback_url with the webhook output of this deployment:
```
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
      -F client_id=5 \
      -F client_secret=7b2946535949ae70f015d696d8ac602830ece412 \
      -F 'callback_url=http://a-valid.com/url' \
      -F 'verify_token=STRAVA'
```
