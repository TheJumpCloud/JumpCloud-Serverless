# Changelog

## [3.2.0] - 2026-04-28

### Added
- New `JcRegion` parameter in `serverless.yaml` to support multi-region JumpCloud API deployments (`STANDARD`, `EU`, `IN`).
- `get_jc_base_url()` helper function in `get-jcdirectoryinsights.py` that resolves the correct API base URL based on the `JcRegion` environment variable.

### Changed
- Orchestrator and Worker functions now use a dynamic base URL (`api.jumpcloud.com`, `api.eu.jumpcloud.com`, or `api.in.jumpcloud.com`) instead of a hardcoded value.

## [3.1.0] - 2026-03-20

### Added

- Test functionality to input start, end time, and directory
- Multi Org and Service account support 
## [3.0.0] - 2026-03-20

### Added

- Added an Amazon SQS event-driven architecture to safely process massive event volumes (1M+ events) without hitting Lambda memory limits or execution timeouts.

- Introduced an Orchestrator-Worker pattern to enable concurrent, parallel processing of data chunks, significantly speeding up ingestion times.

- Added a Dead Letter Queue (DLQ) and automatic retry mechanism to gracefully handle temporary JumpCloud API rate limits or network timeouts without dropping data.

## [2.1.0] - 2025-12-16

### Added

- Updated Python Runtime to latest version

## [2.0.2] - 2025-03-03

### Added

- Fixed deployment bug

## [2.0.0] - 2025-03-03

### Added

- Replaced EventBridge Rate scheduling to Cron scheduling for fine-grained scheduling control
- Fixed issue with server runtime creating time gaps with API calls

## [1.3.2] - 2024-09-12

### Added

- Fixed application serverless repository installation not installing properly

## [1.3.1] - 2024-09-12

### Added

- Added a change to allow for new API Key types

## [1.3.0] - 2023-12-13

### Added

- Added new services: password_manager, object_storage, software
- Added parameter or option to format JSON to SingleLine or MultiLine
  
## [1.2.1] - 2022-06-13

### Added

- Added CloudWatch logging that includes service/s, timestamps, and Powershell Script
  - Powershell script can be used to manually run queries in case of timeouts or errors
- Changed Python runtime from version 3.7 to 3.9
## [1.2.0] - 2022-01-12

### Added

- Ability to filter available services instead of querying all directory insights data.
  - Service can be set to query any of: "directory, radius, sso, systems, ldap, mdm" instead of the default "all" services
- CloudWatch will now log for each service, notating when no results are found as NoResults_SERVICENAME

## [1.1.0] - 2020-08-11

### Added

- OrgID as an optional parameter

## [1.0.0] - 2020-07-31

### Added

- Initial release of the JumpCloud AWS Directory Insights Serverless App