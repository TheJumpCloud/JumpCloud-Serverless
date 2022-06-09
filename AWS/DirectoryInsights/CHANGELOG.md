# Changelog
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