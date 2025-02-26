# Gather JumpCloud Directory Insights Data with an AWS Serverless Application

_This document will walk a JumpCloud Administrator through packaging and deploying this Serverless Application manually. This workflow is intended for those who need to make modifications to the code or tie this solution into other AWS resources. If you would simply like to deploy this Serverless Application as-is, you can do so from the [Serverless Application Repository](https://serverlessrepo.aws.amazon.com/applications/us-east-2/339347137473/JumpCloud-DirectoryInsights)_

_Note: This document assumes the use of Python 3.9+_

## Table of Contents

- [Gather JumpCloud Directory Insights Data with an AWS Serverless Application](#gather-jumpcloud-directory-insights-data-with-an-aws-serverless-application)
  - [Table of Contents](#table-of-contents)
  - [Pre-requisites](#pre-requisites)
  - [Create Python Script](#create-python-script)
  - [Create SAM Template](#create-sam-template)
  - [Package and Deploy the Application](#package-and-deploy-the-application)
    - [Packaging the Application](#packaging-the-application)
    - [Deploying the Application](#deploying-the-application)
    - [Formatting JSON](#formatting-json)
    - [Note on data](#note-on-data)

## Pre-requisites

- [Your JumpCloud API key](https://docs.jumpcloud.com/2.0/authentication-and-authorization/authentication-and-authorization-overview)
- [AWS CLI installed](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html)
- [AWS SAM CLI installed](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
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

Create a directory to store your Serverless Application and any dependencies required. In the root of that directory create your [Python Script](https://github.com/TheJumpCloud/JumpCloud-Serverless/blob/master/AWS/DirectoryInsights/get-jcdirectoryinsights.py).

This Application requires `boto3`, `requests`, and `croniter` packages. Install these dependencies using pip3. Within the directory you created, run the following commands to install the dependencies within the directory.

```bash
pip3 install boto3 -t .
pip3 install requests -t .
pip3 install croniter -t .
```

Create a ZIP archive of the Python script and the dependencies.

```
zip -r get-jcdirectoryinsights.zip .
```

## Create SAM Template

In the root of your directory, create a yaml file named `serverless.yaml` and copy the contents of this template: [serverless.yaml](https://github.com/TheJumpCloud/JumpCloud-Serverless/blob/master/AWS/DirectoryInsights/serverless.yaml).

_Note: The example template provided assumes that you have named your ZIP file get-jcdirectoryinsights.zip. If this is not true, update the `CodeUri` property to reflect the correct name._ \
_This also assumes the name of your Python script is named get-jcdirectoryinsights.py and the `def` in your python script is named jc_directoryinsights. If neither of these is true, update the `Handler` property to match a <script_name>.<def_name> format._

## Package and Deploy the Application

### Packaging the Application

Using the AWS SAM CLI, package your application. This will upload your ZIP archive and `serverless.yaml` file to an S3 bucket. It will also create a file named `packaged.yaml` in your directory. `packaged.yaml` is an updated version of the SAM template that you provided that now directs to your S3 bucket and the script and dependencies now stored within it.

```
sam package --template-file serverless.yaml --output-template-file packaged.yaml --s3-bucket <YOUR S3 BUCKET>
```

_Note: Provide the name of the S3 bucket that you created for packaging and storing your application._

### Deploying the Application

<details>
<summary>AWS CLI</summary>

Using the AWS CLI, you can [deploy](https://docs.aws.amazon.com/cli/latest/reference/cloudformation/deploy/index.html) your template directly from your terminal.

```
aws cloudformation deploy --template-file ./packaged.yaml --stack-name <YOUR STACK NAME> --parameter-overrides JumpCloudApiKey=<API KEY> CronExpression="<CRON EXPRESSION>" Service=<SERVICES> --JsonFormat=<JSON FORMAT> --capabilities CAPABILITY_IAM
```
Example:
```
aws cloudformation deploy --template-file ./packaged.yaml --stack-name JCExampleDIStack --parameter-overrides JumpCloudApiKey=YOURJCAPIKEY CronExpression="0/30 * * * ? *" Service=all --JsonFormat=MultiLine --capabilities CAPABILITY_IAM
```

_Note: Verify that the CronExpression conforms to the specified EventBridge cron syntax, as detailed in [EventBridge Cron Formatting](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html). For example: `0/30 * * * ? *` = Every 30 minutes. <br>
Service accepts a comma-delimited list of services to log. To select all services, set the Service parameter to "all". To limit data to a specific service set the Service parameter to any of the following: directory,radius,sso,systems,ldap,mdm._

</details>

<details>
<summary>Deploy Alternative: Privately Publish the Application</summary>
Rather than deploying your Application from the CLI, you can also publish your application so that it is viewable via the [Severless Application Repository](https://console.aws.amazon.com/serverlessrepo/) . By default, published applications are "Private" so they will not be publicly available until set otherwise.

Using the AWS SAM CLI, publish your application to the Serverless Applications Repository.

```
sam publish --template packaged.yaml --region <REGION>
```

Once you have published your Application to the [Severless Application Repository](https://console.aws.amazon.com/serverlessrepo/), you can find and deploy your application from the Private Applications tab.

_Note: Verify that the CronExpression conforms to the specified EventBridge cron syntax, as detailed in [EventBridge Cron Formatting](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html). For example: `0/30 * * * ? *` = Every 30 minutes. <br>
Service accepts a comma-delimited list of services to log. To select all services, set the Service parameter to "all". To limit data to a specific service set the Service parameter to any of the following: directory,radius,sso,systems,ldap,mdm._

</details>

### Formatting JSON
There are two options to format JSON, Singleline and Multiline format. To set the desired format set the parameter ```--JsonFormat=MultiLine``` or ```--JsonFormat=SingleLine``` when [Deploying the Application](#deploying-the-application)

ex.

SingleLine Format:
![Alt text](image-2.png)
MultiLine Format:
![Alt text](image-1.png)

### Note on data

This application will only gather data per the interval scheduled during deployment. I.e. If the app is configured to gather data each day. The app will gather the data from the last day and create a schedule to gather the next day data and so on. To gather data past this interval, please use our [PowerShell Module](https://github.com/TheJumpCloud/support/wiki/Using-the-JumpCloud-PowerShell-Module):

```powershell
$data = Get-JCEvent -Service:('all') -StartTime:((Get-date).AddDays(-90))
$data | ConvertTo-Json -Depth 99 | Out-file ./JsonData.json
```

The `JsonData.json` file can be saved to an S3 bucket to store a 'backup' of all available data.
