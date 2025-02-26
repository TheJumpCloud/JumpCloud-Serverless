# Changelog

## [2.0.0] - 2025-02-26

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