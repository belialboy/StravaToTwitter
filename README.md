# StravaToTwitter

This project deploys a SAM application that registers with Strava and allows Strava users to register with it. Once registered, any time that user registers a Strava activity, it creates a corresponding tweet that includes details about that activity, and also their year-to-date totals.

As a "security dood" I've tried to use secure practices with the management of most sensitive information. Twitter credentials are stored in a DynamoDB table, as environmental variables in a Lambda function, and are also found in the ChengeSet for Cloudformation... so it's not perfect by any stretch. This is a hobby-project, and I wanted to make it as accessible as possible without burning unnecessary dollars on Secrets Manager and the like. Enjoy, and feel free to improve.

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
    * You'll also need the [Serverless Application Model](https://aws.amazon.com/serverless/sam/) CLI installed either on your machine, or in a [Cloud9](https://aws.amazon.com/cloud9/) environment in your AWS Account.
    * An AWS Role in that account that you can assume to run the cloudformation used by SAM
    * `git` installed on your command line

## Install

Clone this repository:

`git clone https://github.com/belialboy/StravaToTwitter && cd StravaToTwitter`

Build the SAM assets:

`sam build`

Deploy the SAM assets:

`sam deploy -g`

This will then guide you through entering your twitter keys (mentioned above) and and Strava App id/secret. 

Once complete you will need to take take the domain name (The bit after `https://` and before `/register/`, i.e. `abcde12345.execute-api.eu-west-1.amazonaws.com`) of your registration URL and set that as your `Authorization Callback Domain` for your application (the very last field on the [Update Application](https://www.strava.com/settings/api) page). You can now shre the full registration URL with Strava users that want to use your application.

### Use a Code Pipeline

If you're feeling adventurous, you could fork this GitHub repo and then create an AWS CodePipeline with CodeBuild step that uses the `buildspec.yml` to trigger the build automatically. If you do this, you'll need to provision SSM Parameters in that match the names at the top of the buildspec file. Provisioning is then automated whenever there is a change to the repository. Instructions for setting up that CodePipeline are outside this guide, but are not too tricky! You'll need to give the codebuild service role the following additional permissions to be able to run the SAM deploy properly:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
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
            "Sid": "VisualEditor1",
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:PutObject",
                "s3:GetObject"
            ],
            "Resource": "arn:aws:s3:::*/*"
        },
        {
            "Sid": "VisualEditor2",
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
                "lambda:GetLayerVersion"
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

I will make the registration include a capture for twitter credentials so that I don't have to hard code these into the deployment script.