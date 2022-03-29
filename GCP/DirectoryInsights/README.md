# Gather JumpCloud Directory Insights Data with an AWS Serverless Application
_This document will walk a JumpCloud Administrator through packaging and deploying this Serverless Application manually. This workflow is intended for those who need to make modifications to the code or tie this solution into other AWS resources. If you would simply like to deploy this Serverless Application as-is, you can do so from the [Serverless Application Repository](https://serverlessrepo.aws.amazon.com/applications/us-east-2/339347137473/JumpCloud-DirectoryInsights)_

_Note: This document assumes the use of Python 3+_
## Table of Contents
- [Gather JumpCloud Directory Insights Data with an AWS Serverless Application](#gather-jumpcloud-directory-insights-data-with-an-aws-serverless-application)
  - [Table of Contents](#table-of-contents)
  - [Pre-requisites](#pre-requisites)
  - [Create Directory](#create-directory-to-store-directory-insights-files)
  - [Edit cloudbuild.yaml](#edit-cloudbuildyaml)
  - [Deploying the Application](#deploying-the-application)

## Pre-requisites
- [Your JumpCloud API key](https://docs.jumpcloud.com/2.0/authentication-and-authorization/authentication-and-authorization-overview)
- [GCLOUD CLI installed](https://cloud.google.com/sdk/docs/install)
- [Google Cloud Build](https://cloud.google.com/build/docs/securing-builds/configure-access-for-cloud-build-service-account)
  - Permissions and access to create:
    - Cloud Functions = Enabled
    - Cloud Scheduler = Enabled
    - Secret Manager = Enabled
    - Cloud Build Service account email: admin access to services above
  
## Create Directory to Store Directory Insights Files

Create a directory to store your Serverless Application and any dependencies required. In the root of that directory add [Directory Insights Files](https://github.com/TheJumpCloud/JumpCloud-Serverless/blob/master/GCP/DirectoryInsights/).
Install the dependencies in requirements.txt file
```bash
~/DirectoryInsights$ pip install -r requirements.txt
```

## Edit CloudBuild.yaml

In the root directory, edit cloudbuid.yaml file `substitutions` variable values with the necessary credentials


## Deploying the Application

<summary>GCloud CLI</summary>

Using the GCLOUD CLI, you can [Cloud Build Deploy](https://cloud.google.com/sdk/gcloud/reference/builds/submit) directly from the project directory
```bash
~/DirectoryInsights$ gcloud build submit
```
_Note: `gcloud build submit` default config is "cloudbuild.yaml" which is why we do not need to specify `--config=config.yaml` tag



