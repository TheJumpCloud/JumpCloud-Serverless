# Gather JumpCloud Directory Insights Data with GCP Services
_This document will walk a JumpCloud Administrator through deploying this Serverless Application to GCP._

_Note: This document assumes the use of Python 3.9_
## Table of Contents
- [Gather JumpCloud Directory Insights Data with an GCP](#gather-jumpcloud-directory-insights-data-with-gcp-services)
  - [Table of Contents](#table-of-contents)
  - [Pre-requisites](#pre-requisites)
  - [Create Directory](#create-directory-to-store-directory-insights-files)
  - [Edit cloudbuild.yaml](#edit-cloudbuildyaml)
  - [Deploying the Application](#deploying-the-application)

## Pre-requisites
- [Your JumpCloud API key](https://docs.jumpcloud.com/2.0/authentication-and-authorization/authentication-and-authorization-overview)
- [GCLOUD CLI installed](https://cloud.google.com/sdk/docs/install)
- [Google Cloud Build](https://cloud.google.com/build/docs/securing-builds/configure-access-for-cloud-build-service-account)
  - Permissions:
    - Cloud Functions = Enabled
    - Cloud Scheduler = Enabled
    - Secret Manager = Enabled
  - Cloud Build Service account email: admin access to services above
- JumpCloud administrator will need `Cloud Build Editor` role with their GCP account
- Cloud Functions Invoker service account
  
## Create Directory to Store Directory Insights Files

Create a directory to store your Serverless Application and any dependencies required. In the root of that directory add [Directory Insights Files](https://github.com/TheJumpCloud/JumpCloud-Serverless/blob/master/GCP/DirectoryInsights/).
Install the dependencies in requirements.txt file
```bash
~/DirectoryInsights$ pip install -r requirements.txt
```

## Edit CloudBuild.yaml

In the root directory, edit cloudbuid.yaml file `substitutions` variable values with the necessary credentials


## Deploying the Application

GCloud CLI

Using the GCLOUD CLI, you can [Cloud Build Deploy](https://cloud.google.com/sdk/gcloud/reference/builds/submit) directly from the project directory
```bash
~/DirectoryInsights$ gcloud builds submit
```
_Note: `gcloud build submit` default config is "cloudbuild.yaml" which is why we do not need to specify `--config=config.yaml` tag_
_Note: `.gcloudignore` file excludes unwanted files/folders from getting push in the deploy process_



