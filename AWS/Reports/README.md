# Report on JumpCloud Systems and User Associations with an AWS Serverless Application
_This document will walk a JumpCloud Administrator through packaging and deploying this Serverless Application manually. This workflow is intended for those who need to make modifications to the code or tie this solution into other AWS resources._

_Note: This document assumes the use of Python 3+_
## Table of Contents
- [Report on JumpCloud Systems and User Associations with an AWS Serverless Application](#report-on-jumpcloud-systems-and-user-associations-with-an-aws-serverless-application)
  - [Table of Contents](#table-of-contents)
  - [Pre-requisites](#pre-requisites)
  - [Create Python Script](#create-python-script)
  - [Create SAM Template](#create-sam-template)
  - [Package and Deploy the Application](#package-and-deploy-the-application)
    - [Packaging the Application](#packaging-the-application)
    - [Deploying the Application](#deploying-the-application)

## Pre-requisites
- [Your JumpCloud API key](https://docs.jumpcloud.com/2.0/authentication-and-authorization/authentication-and-authorization-overview)
- [AWS CLI installed](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html)
- [AWS SAM CLI installed](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
- [SlackBot App Oath Token](https://api.slack.com/start/building)
- A valid Amazon S3 bucket policy that grants the service read permissions for artifacts uploaded to Amazon S3 when you package your application.
  - Go to the [S3 Console](https://s3.console.aws.amazon.com/s3/)
  - Choose the S3 bucket that you will use to package your application
  - Permissions > Bucket Policy
  - Paste the following Policy Statement into the Bucket Policy Editor (replace `<YOUR BUCKET NAME>` with the name of your S3 bucket)
    ```
    {
          "Version":"2012-10-17",
          "Statement":[
              {
                "Effect":"Allow",
                "Principal":{
                    "Service":"serverlessrepo.amazonaws.com"
                },
                "Action":"s3:GetObject",
                "Resource":"arn:aws:s3:::<YOUR BUCKET NAME>/*",
                "Condition":{
                    "StringEquals":{
                      "aws:SourceAccount":"AWS::AccountId"
            }
          }
        }
      ]
    }
    ```
  
## Create Python Script

Create a directory to store your Serverless Application and any dependencies required. In the root of that directory create your [Python Script](https://github.com/TheJumpCloud/JumpCloud-Serverless/blob/master/AWS/reports/report.py).

This Application requires multiple dependencies to be installed Install these dependencies using pip3. Within the directory you created, run the following commands to install the dependencies within the directory.
```bash
pip3 install requests -t .
pip3 install datetime -t .
pip3 install json -t .
pip3 install boto3 -t .
pip3 install os -t .
pip3 install gzip -t .
pip3 install git+https://github.com/TheJumpCloud/jcapi-python.git#subdirectory=jcapiv1 -t .
pip3 install git+https://github.com/TheJumpCloud/jcapi-python.git#subdirectory=jcapiv2 -t .
pip3 install slack.sdk -t .
```

Create a ZIP archive of the Python script and the dependencies.
```
~/report zip -r report.zip .
```

## Create SAM Template

In the root of your directory, create a SAM template named [serverless.yaml](https://github.com/TheJumpCloud/support/blob/SA-1258-DI-Serverless/AWS/Serverless/reports/serverless.yml).

_Note: The example template provided assumes that you have named your ZIP file reports.zip. If this is not true, update the `CodeUri` property to reflect the correct name._ \
_This also assumes the name of your Python script is named report.py and the `def` in your python script is named jc_reports. If neither of these is true, update the `Handler` property to match a <script_name>.<def_name> format._

## Package and Deploy the Application

### Packaging the Application
Using the AWS SAM CLI, package your application. This will upload your ZIP archive and `serverless.yaml` file to an S3 bucket. It will also create a file named `packaged.yaml` in your directory. `packaged.yaml` is an updated version of the SAM template that you provided that now directs to your S3 bucket and the script and dependencies now stored within it.
```
sam package --template-file serverless.yml --output-template-file packaged.yaml --s3-bucket <YOUR S3 BUCKET>
```
_Note: Provide the name of the S3 bucket that you created for packaging and storing your application._


### Deploying the Application
<details>
<summary>AWS CLI</summary>

Using the AWS CLI, you can [deploy](https://docs.aws.amazon.com/cli/latest/reference/cloudformation/deploy/index.html) your template directly from your terminal.
```
sam deploy --template-file ./packaged.yaml --stack-name <Stack Name> --parameter-overrides JumpCloudApiKey=<JC API Key> BotUserAccessToken=<Slack OAth Access Token> slackChannelId=<Slack Channel ID> --capabilities CAPABILITY_IAM
```
</details>

<details>
<summary>Deploy Alternative: Privately Publish the Application</summary>
Rather than deploying your Application from the CLI, you can also publish your application so that it is viewable via the [Severless Application Repository](https://console.aws.amazon.com/serverlessrepo/). By default, published applications are "Private" so they will not be publicly available until set otherwise.

Using the AWS SAM CLI, publish your application to the Serverless Applications Repository.
```
~/jc-directorys$ sam publish --template packaged.yaml --region <REGION>
```
Once you have published your Application to the [Severless Application Repository](https://console.aws.amazon.com/serverlessrepo/), you can find and deploy your application from the Private Applications tab.
</details>
