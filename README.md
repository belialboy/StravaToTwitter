# StravaToTwitter

## Prerequisites

To get this to function for your Strava and Twitter you will need the following:
* [Twitter Developer](https://developer.twitter.com/en/portal/dashboard) App Keys 
    * Specifically you will need (keep these to yourself and don't check them in anywhere or share them):
        * Twitter Consumer Key
        * Twitter Consumer Secret
        * Twitter Access Token Key
        * Twitter Access Token Secret
* [IFTTT](https://ifttt.com/applets/) Webhook Applet
    * Use a `POST` type using `application/json`
    * The body shoud be set to ```{"URL":"{{LinkToActivity}}","ImageURL":"{{RouteMapImageUrl}}","distance":{{DistanceMeters}},"duration":{{ElapsedTimeInSeconds}},"type":"{{ActivityType}}"}```
    * The URL will ultimately be set to be the output of the SAM deployment, so feel free to enter anything in here for the time being.
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

This will then guide you through entering your twitter keys (mentioned above) and the exact name you use in Strava for your account. My name is "Jonathan Jenkyn" and so this is what I put into this field. This is a really noddy test to make sure that any posts that hit this function are actually for you, and not for someone else, thus it's important that this matches the textual version of your name in Strava.

Once deployed, it will exit with an `ApiUrl`. You should now update your IFTTT Webhook with as the URL for the web request. It will look something like: `https://ab1cd2ef3.execute-api.us-west-1.amazonaws.com/Prod/`

## Done?

It's really tricky to test this, as it will start to update your yearly values.

```curl -XPOST -H "Content-type: application/json" -d '{"URL":"https://www.strava.com/activities/ONEOFYOURS","ImageURL":"boink","distance":1,"duration":60,"type":"Test"}' 'https://ab1cd2ef3.execute-api.eu-west-1.amazonaws.com/Prod/'```

This will post into your Twitter feed, so get ready to delete it!

If you want to update your yearly values for different activity types, you'll need to update them in the JSON in the DynamoDB created with the SAM deploy. This should be failry self explanitory... but you will need to translate distances into meters, and time into seconds for it to be valid.

## More to come

I'm going to update this code so that there is no dependence on the IFTTT layer, and will communicate directly with Strava through [push notifications](https://developers.strava.com/docs/webhooks/). Hold the line caller.