# StravaToTwitter

This project deploys a SAM application that registers itself with Strava and allows Strava users to register with it themselves. Once registered, any time that user registers a Strava activity, it creates a corresponding tweet through a single account that includes details about that activity, and also their year-to-date totals.

As a "security dood" I've tried to use secure practices with the management of most sensitive information. Twitter credentials are stored as environmental variables in a Lambda function, and are also found in the Change Set for Cloudformation... so it's not perfect by any stretch. This is a hobby-project, and I wanted to make it as accessible as possible without burning unnecessary dollars on Secrets Manager and the like. Enjoy, and feel free to improve.

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
    * Set your application `Authorization Callback Domain` to anything you like for the moment; You'll change this once the deployment has completed.
* An [AWS](https://aws.amazon.com/) account (You'll be spending less than a few cent per month, so won't break the bank)
    * You'll also need the [Serverless Application Model](https://aws.amazon.com/serverless/sam/) CLI installed either on your machine, or in a [Cloud9](https://aws.amazon.com/cloud9/) (preferred) environment in your AWS Account.
    * An AWS Role in that account that you can assume to run the cloudformation used by SAM
    * `git` installed on your command line

## Install

Clone this repository:

`git clone https://github.com/belialboy/StravaToTwitter && cd StravaToTwitter`

Build the SAM assets:

`sam build`

Deploy the SAM assets:

`sam deploy -g`

This will then guide you through entering your Twitter keys (mentioned above) and and Strava App id/secret. 

Once complete you will need to take the domain name (The bit after `https://` and before `/register/`, i.e. `abcde12345.execute-api.eu-west-1.amazonaws.com`) of your registration URL and set that as your `Authorization Callback Domain` for your application (the very last field on the [Update Application](https://www.strava.com/settings/api) page). You can now share the full registration URL with Strava users that want to use your application.

### Use a Code Pipeline

If you're feeling adventurous, you could fork this GitHub repo and then create an AWS CodePipeline with CodeBuild step that uses the `buildspec.yml` to trigger the build automatically. If you do this, you'll need to provision SSM Parameters in that match the names at the top of the buildspec file. You;ll also need to change the name of the s3 bucket where your code it built to; in the verion I use it's set to `Strava2TwitterDev`, so you'll need to change that in your forked version of this repo. Provisioning is then automated whenever there is a change to the repository. Instructions for setting up that CodePipeline are outside this guide, but are not too tricky! You'll need to give the codebuild service role the following additional permissions to be able to run the SAM deploy properly:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BasicCloudformation",
            "Effect": "Allow",
            "Action": [
                "cloudformation:DescribeStackEvents",
                "cloudformation:DescribeStackResources",
                "cloudformation:CreateStack",
                "cloudformation:DeleteStack",
                "cloudformation:UpdateStack",
                "cloudformation:CreateChangeSet",
                "cloudformation:DescribeChangeSet",
                "cloudformation:ExecuteChangeSet",
                "cloudformation:GetTemplateSummary",
                "cloudformation:DescribeStacks",
                "cloudformation:ListStackResources"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Sid": "S3RequirementsForCodeUpload",
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:PutObject",
                "s3:GetObject"
            ],
            "Resource": "arn:aws:s3:::*/*"
        },
        {
            "Sid": "SSMAndDynamoDBRequirements",
            "Effect": "Allow",
            "Action": [
                "s3:ListAllMyBuckets",
                "ssm:GetParameters",
                "ssm:GetParameter",
                "dynamodb:*"
            ],
            "Resource": "*"
        },
        {
            "Sid": "Lambda",
            "Effect": "Allow",
            "Action": [
                "lambda:AddPermission",
                "lambda:CreateFunction",
                "lambda:DeleteFunction",
                "lambda:GetFunction",
                "lambda:GetFunctionConfiguration",
                "lambda:ListTags",
                "lambda:RemovePermission",
                "lambda:TagResource",
                "lambda:UntagResource",
                "lambda:UpdateFunctionCode",
                "lambda:UpdateFunctionConfiguration",
                "lambda:InvokeFunction"
            ],
            "Resource": [
                "arn:aws:lambda:*:*:function:*"
            ]
        },
        {
            "Sid": "LambdaLayers",
            "Effect": "Allow",
            "Action": [
                "lambda:GetLayerVersion",
                "lambda:PublishLayerVersion",
                "lambda:DeleteLayerVersion"
            ],
            "Resource": [
                "arn:aws:lambda:*:*:layer:*"
            ]
        },
        {
            "Sid": "IAM",
            "Effect": "Allow",
            "Action": [
                "iam:AttachRolePolicy",
                "iam:DeleteRole",
                "iam:DetachRolePolicy",
                "iam:GetRole",
                "iam:TagRole",
                "iam:CreateRole",
                "iam:PutRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:GetRolePolicy"
            ],
            "Resource": [
                "arn:aws:iam::*:role/*"
            ]
        },
        {
            "Sid": "IAMBasic",
            "Effect": "Allow",
            "Action": [
                "iam:ListPolicies"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Sid": "IAMPassRole",
            "Effect": "Allow",
            "Action": "iam:PassRole",
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "iam:PassedToService": "lambda.amazonaws.com"
                }
            }
        },
        {
            "Sid": "APIGateway",
            "Effect": "Allow",
            "Action": [
                "apigateway:*"
            ],
            "Resource": [
                "*"
            ]
        }
    ]
}
```
## Future Stuff

* It needs lots more unit-testing... that's the next thing for me to drive.
* Add feature to require registrants to be a part of a particular strava club. This then supports the idea that this application can be used by sporting clubs to stream efforts by its members
* Standardise the formatting and variable naming convention. (It was initially just a noddy script, but grew up too quickly)