# Create JumpCloud User CSV files with an AWS Serverless Application
_This document will walk a JumpCloud Administrator through packaging and deploying this Serverless Application manually. This workflow is intended for those who need to make modifications to the code or tie this solution into other AWS resources. If you would simply like to deploy this Serverless Application as-is, you can do so from the [Serverless Application Repository](https://serverlessrepo.aws.amazon.com/applications/us-east-2/339347137473/JumpCloud-DirectoryInsights)_

_Note: This document assumes the use of Python 3.14+_
## Table of Contents
- [Create JumpCloud User CSV files with an AWS Serverless Application](#create-jumpcloud-user-csv-files-with-an-aws-serverless-application)
  - [Table of Contents](#table-of-contents)
  - [Pre-requisites](#pre-requisites)
  - [Create Python Script](#create-python-script)
  - [Create SAM Template](#create-sam-template)
  - [Package and Deploy the Application](#package-and-deploy-the-application)
    - [Deploying the Application](#deploying-the-application)
    - [Formatting JSON](#formatting-json)
  - [Updating an Existing Deployment](#updating-an-existing-deployment)
  - [Clean Up / Uninstall](#clean-up--uninstall)
  - [Note on Data Chunking (MAX\_EVENTS\_PER\_WORKER)](#note-on-data-chunking-max_events_per_worker)
    - [How Chunked Files Appear in S3](#how-chunked-files-appear-in-s3)
  - [Note on Lambda resource memory](#note-on-lambda-resource-memory)

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

Create a directory to store your Serverless Application and any dependencies required. In the root of that directory create your [Python Script](https://github.com/TheJumpCloud/support/blob/master/AWS/Serverless/Users/get-jcusers.py).

This Application requires `boto3`, and `requests`. Install these dependencies using pip3. Within the directory you created, run the following commands to install the dependencies within the directory.

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
aws cloudformation deploy --template-file ./packaged.yaml --stack-name <YOUR STACK NAME> --parameter-overrides JumpCloudApiKey=<API KEY> CronExpression="<CRON EXPRESSION>" Service=<SERVICES> JsonFormat=<JSON FORMAT> --capabilities CAPABILITY_IAM
```
Example:
```
aws cloudformation deploy --template-file ./packaged.yaml --stack-name JCExampleDIStack --parameter-overrides JumpCloudApiKey=YOURJCAPIKEY CronExpression="0/30 * * * ? *" Service=all JsonFormat=MultiLine --capabilities CAPABILITY_IAM
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


## Updating an Existing Deployment
To update your existing application to a newer version, simply pull the latest code, re-package the ZIP file, and run the `sam package` and `aws cloudformation deploy` commands again using the **exact same `--stack-name`**. AWS CloudFormation will automatically detect the changes and safely update your existing resources.

## Clean Up / Uninstall

If you no longer need this application and want to avoid incurring future AWS charges, you can delete the CloudFormation stack. 

*Note: Deleting the stack will NOT delete the Amazon S3 bucket containing your previously gathered logs, you must delete it manually.*

To delete the stack via the AWS CLI:
```bash
aws cloudformation delete-stack --stack-name <YOUR STACK NAME>
```

## Note on Data Chunking (MAX_EVENTS_PER_WORKER)

To prevent the Worker Lambdas from timing out or running out of memory, the Orchestrator mathematically divides large data pulls into smaller, parallel "chunks." 

By default, the application is configured to process a maximum of **25,000 events per chunk**. This limit is hardcoded via the `MAX_EVENTS_PER_WORKER` variable inside the `get-jcdirectoryinsights.py` script. 

Administrators who wish to modify the code can adjust this variable based on their needs:
* **Decrease the limit (e.g., 10,000):** Generates smaller, more frequent `.json.gz` files and further reduces the Worker Lambda memory footprint.
* **Increase the limit (e.g., 50,000):** Generates fewer, larger `.json.gz` files and reduces the total number of SQS messages sent, but will consume more memory per Worker execution.

To modify this limit, open `get-jcdirectoryinsights.py`, locate `MAX_EVENTS_PER_WORKER = 25000` inside the `jc_orchestrator` function, update the integer, and re-run the `sam package` and deploy commands. Or edit the code directly from Lambda in AWS Console.

### How Chunked Files Appear in S3

Because the Orchestrator divides a single scheduled run into multiple smaller timeframes, you will see multiple `.json.gz` files in your S3 bucket for a single execution if the event count exceeds the `MAX_EVENTS_PER_WORKER` limit.

The files are automatically named with their specific, chunked time slices (`start_time` to `end_time`). 

**Example:**
If your application runs every 15 minutes (e.g., `14:00:00Z` to `14:15:00Z`) and pulls **50,000** directory events, a chunk limit of **25,000** will result in **2** separate files in S3, split perfectly in half:
* `jc_directoryinsights_directory_2026-03-19T14-00-00Z_2026-03-19T14-07-30Z.json.gz`
* `jc_directoryinsights_directory_2026-03-19T14-07-30Z_2026-03-19T14-15-00Z.json.gz`

If your SIEM or log forwarder monitors this S3 bucket, it will naturally ingest these sequential files without any issues or duplicate data.

## Note on Lambda resource memory

Because this application uses a split architecture to handle high volumes of data, there are two distinct Lambda memory settings (`MemorySize`) in the `serverless.yaml` file:

* **OrchestratorFunction:** Currently set to `128` megabytes. Since this function only calculates time slices and queues messages, it requires minimal memory. 
* **WorkerFunction:** Currently set to `512` megabytes. This function does the heavy lifting of paginating through the JumpCloud API, processing the data, and compressing the JSON payloads.

Administrators are encouraged to experiment with different memory allocations to find the optimal configuration for their specific workload. Increasing the Worker memory can improve performance and prevent out-of-memory errors on massive data pulls, while decreasing it can reduce costs for less demanding operations.