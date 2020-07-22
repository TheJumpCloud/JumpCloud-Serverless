# JumpCloud Directory Insights Data Collector

This application will allow you to export your JumpCloud Organization's Directory Insights data to an S3 Bucket for long-term storage or eventual use by a SIEM or analytics tool.

### What You Will Need

- Application Name
  - This can be whatever you want! Many of the resources that this application generates for you will base their name off what you provide here.
- IncrementAmount & IncrementType
  - Together these parameters will form the cadence at which this application exports your JumpCloud Directory Insights data. _Note: If your IncrementAmount is 1, please use the singular word for IncrementType_
- JumpCloudApiKey
  - Your [JumpCloud API key](https://docs.jumpcloud.com/2.0/authentication-and-authorization/authentication-and-authorization-overview) will be safely stored in AWS Secrets Manager.

### What This Application Does

Once you deploy this application, it will:
- Create a role that will be able to access and operate all of the other pieces
- Create an S3 bucket to store all of your data
- Place your JumpCloud API Key in Secrets Manager
- Create the lambda function that ties it all together

Once everything has been created, the application will wait until your specified increment has passed, gather the JumpCloud Directory Insights data from that time period into a JSON file, zip it up, and send it off to the S3 bucket for storage. It will continue doing so until the CloudFormation template is deleted or the CloudWatch Event that triggers the Lambda is disabled.

_Note: If an entire increment goes by without any Directory Insights data, we'll place a data point in a CloudWatch Metric in the JumpCloudDirectoryInsights Namespace. This namespace will not be created if you never have a time period without events._

