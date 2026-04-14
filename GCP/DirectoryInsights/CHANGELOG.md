# Changelog

## [3.0.0] - 2026-04-08

### Added
-  Introduces a major architectural overhaul to the JumpCloud Directory Insights GCP integration, migrating it to a highly resilient, event-driven Orchestrator-Worker pattern using Google Cloud Pub/Sub. Similar functionality with the AWS Serverless App

## [1.0.3] - 2025-03-03

### Fixes
- Scheduling data gaps
- Fixed issues with deploying cloud run functions

## [1.0.2] - 2023-09-25

### Fixes
- Updated Requests package version to 2.31.0 in the requirements file

## [1.0.1] - 2022-06-13

### Added

- Added logging for service, timestamps, and Powershell script for manual query operation
  - The script can be used in case of timeouts or errors

### Fixes

- Added string quotations and note for _GCP_PROJECT_ID parameter in Cloudbuild.yaml to fix incorrect type error

## [1.0.0] - 2022-03-31

### Added

- Initial release of the JumpCloud GCP Directory Insights Serverless App