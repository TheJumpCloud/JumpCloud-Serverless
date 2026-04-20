import os
import json
import boto3
import requests
import gzip
import logging
import datetime
import math
import base64
import re
from botocore.exceptions import ClientError
from croniter import croniter

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ==============================================================================
# CORE HELPER FUNCTIONS
# ==============================================================================
def get_secret(secret_id, suppress_error=False):
    """Retrieves the secret value from AWS Secrets Manager."""
    if not secret_id:
        return ""
    client = boto3.client(service_name='secretsmanager')
    try:
        response = client.get_secret_value(SecretId=secret_id)
        return response['SecretString']
    except ClientError as e:
        if not suppress_error:
            logger.error(f"Error retrieving secret {secret_id}: {e}")
        raise Exception(e)

JC_AUTH_TYPE_API_KEY = "APIKey"
JC_AUTH_TYPE_SERVICE_TOKEN = "ServiceToken"
JC_OAUTH_TOKEN_URL = "https://admin-oauth.id.jumpcloud.com/oauth2/token"
JC_USER_AGENT = "JumpCloud_AWSServerless.DirectoryInsights/3.1.0"

def _normalize_jc_auth_type(value):
    if value is None or str(value).strip() == "":
        return JC_AUTH_TYPE_API_KEY
    return str(value).strip()

def prepare_jc_auth(secret_arn, auth_type):
    """Load credential from Secrets Manager once; for ServiceToken, exchange for OAuth access token."""
    auth_type = _normalize_jc_auth_type(auth_type)
    raw_secret = get_secret(secret_arn).strip()

    if auth_type == JC_AUTH_TYPE_API_KEY:
        return {"kind": JC_AUTH_TYPE_API_KEY, "api_key": raw_secret}

    if auth_type == JC_AUTH_TYPE_SERVICE_TOKEN:
        if ":" not in raw_secret:
            raise ValueError('ServiceToken auth requires the api-key secret to be "clientID:clientSecret".')
        basic_b64 = base64.b64encode(raw_secret.encode("utf-8")).decode("ascii")
        token_resp = requests.post(
            JC_OAUTH_TOKEN_URL,
            data={"scope": "api", "grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {basic_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=60,
        )
        token_resp.raise_for_status()
        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise ValueError("OAuth token response missing access_token")
        return {"kind": JC_AUTH_TYPE_SERVICE_TOKEN, "access_token": access_token}

    raise ValueError(f"Unknown JcAuthType: {auth_type!r}; use APIKey or ServiceToken.")

def build_jc_request_headers_from_prepared(prepared, jc_org_id):
    """Build request headers for one org from prepare_jc_auth() result."""
    kind = prepared["kind"]
    if kind == JC_AUTH_TYPE_API_KEY:
        headers = {
            "x-api-key": prepared["api_key"],
            "content-type": "application/json",
            "user-agent": JC_USER_AGENT,
        }
        if jc_org_id:
            headers["x-org-id"] = jc_org_id
        return headers

    if kind == JC_AUTH_TYPE_SERVICE_TOKEN:
        if not jc_org_id:
            raise ValueError("ServiceToken auth requires an organization ID.")
        return {
            "Authorization": f"Bearer {prepared['access_token']}",
            "content-type": "application/json",
            "user-agent": JC_USER_AGENT,
            "x-org-id": jc_org_id,
        }

    raise ValueError(f"Unknown prepared auth kind: {kind!r}")

def parse_jc_multi_org_flag(value):
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")

def build_org_id_list(org_secret_raw, multi_org):
    raw = (org_secret_raw or "").strip()
    if multi_org:
        return [p.strip() for p in raw.split(",") if p.strip()]
    if raw:
        return [raw]
    return [""]

def mask_org_id_for_logs(org_id):
    if org_id is None or str(org_id).strip() == "":
        return "(no x-org-id)"
    s = str(org_id).strip()
    if len(s) <= 4:
        return s
    return "*" * (len(s) - 4) + s[-4:]

def get_cron_time(cronExpression, timeTolerance):
    """Checks if the current time is within a tolerance of the cron schedule."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cronParts = cronExpression.split()
    cronExpression = " ".join(cronParts[:5])
    try:
        cronTime = croniter(cronExpression, now + datetime.timedelta(seconds=timeTolerance))
        currentCronTime = cronTime.get_prev(datetime.datetime)
        previousCronTime = cronTime.get_prev(datetime.datetime)
        return currentCronTime, previousCronTime
    except Exception as e:
        logger.error(f"Error in cron expression: {e}")
        raise Exception(e)

def chunk_time_range(start_time, end_time, chunks):
    """Splits a time range into an array of smaller time ranges."""
    delta = (end_time - start_time) / chunks
    return [(start_time + delta * i, start_time + delta * (i + 1)) for i in range(chunks)]


def parse_utc_datetime(value):
    """
    Parse start_time / end_time from Event JSON.

    Dynamic (evaluated at request time, UTC):
      - "now" — current instant
      - "now-30" or "now-30d" — 30 days before now (suffix: d=days, h=hours, m=minutes, s=seconds; bare number = days)

    Fixed: ISO-8601, or YYYY-MM-DD:HH:MM:SS. Naive values are UTC.
    """
    if value is None:
        raise ValueError("Timestamp is missing")
    s_raw = str(value).strip()
    if not s_raw:
        raise ValueError("Timestamp is empty")

    s_key = s_raw.lower()
    utc = datetime.timezone.utc
    now = datetime.datetime.now(utc)

    if s_key == "now":
        return now

    rel = re.match(r"^now-(\d+)([dhms])?$", s_key)
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2) or "d"
        if unit == "d":
            delta = datetime.timedelta(days=n)
        elif unit == "h":
            delta = datetime.timedelta(hours=n)
        elif unit == "m":
            delta = datetime.timedelta(minutes=n)
        else:
            delta = datetime.timedelta(seconds=n)
        return now - delta

    s = s_raw
    if len(s) > 10 and s[10] == ":":
        s = s[:10] + "T" + s[11:]
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=utc)
    else:
        dt = dt.astimezone(utc)
    return dt

# ==============================================================================
# ORCHESTRATOR FUNCTION
# ==============================================================================
def jc_orchestrator(event, context):
    logger.info("--- ORCHESTRATOR STARTED ---")
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        org_env_var = os.environ.get('OrgId', '')
        cronExpression = os.environ['CronExpression']
        queueUrl = os.environ['SqsQueueUrl']
        service_env = os.environ['service']
        jc_auth_type = os.environ.get("JcAuthType", JC_AUTH_TYPE_API_KEY)
        jc_multi_org = parse_jc_multi_org_flag(os.environ.get("JcMultiOrg"))
        MAX_EVENTS_PER_WORKER = int(os.environ.get('MaxEventsPerWorker', 25000))
    except KeyError as e:
        logger.error(f"Missing env var: {e}")
        raise Exception(e)

    # --- Optional JSON: explicit window (start_time + end_time) or service override ---
    raw_start = event.get("start_time")
    raw_end = event.get("end_time")
    test_service = event.get("service")

    if test_service:
        logger.info(f"[MANUAL] Overriding default service with: {test_service}")
        service_env = test_service

    # Attempt to fetch Org IDs. Suppress error so a plain string doesn't trigger a CloudWatch alert.
    org_secret_raw = ""
    if org_env_var:
        try:
            org_secret_raw = get_secret(org_env_var, suppress_error=True).strip()
        except Exception:
            logger.info("OrgId does not map to an AWS Secret; treating as a literal string.")
            org_secret_raw = org_env_var

    org_ids = build_org_id_list(org_secret_raw, jc_multi_org)
    
    if jc_multi_org and not org_ids:
        error_msg = "JcMultiOrg is true but no organization IDs were found."
        logger.error(error_msg)
        return {"statusCode": 400, "body": error_msg}

    # --- Time window: explicit [start_time, end_time] OR cron schedule ---
    has_start = raw_start is not None and str(raw_start).strip() != ""
    has_end = raw_end is not None and str(raw_end).strip() != ""

    if has_start ^ has_end:
        error_msg = "Provide both start_time and end_time for a manual window, or omit both for scheduled (cron) mode."
        logger.error(error_msg)
        return {"statusCode": 400, "body": error_msg}

    if has_start and has_end:
        try:
            previousTime = parse_utc_datetime(raw_start)
            now = parse_utc_datetime(raw_end)
        except ValueError as e:
            error_msg = f"Invalid start_time or end_time: {e}"
            logger.error(error_msg)
            return {"statusCode": 400, "body": error_msg}
        if previousTime >= now:
            error_msg = "start_time must be strictly before end_time."
            logger.error(error_msg)
            return {"statusCode": 400, "body": error_msg}
        logger.info(f"[MANUAL WINDOW] {previousTime.isoformat()} to {now.isoformat()}")
    else:
        timeTolerance = 10
        now, previousTime = get_cron_time(cronExpression, timeTolerance)
        logger.info(f"Search Window: {previousTime} to {now}")
    
    sqs = boto3.client('sqs')
    availableServices = ['all', 'access_management', 'alerts', 'asset_management', 'directory', 'ldap', 'mdm', 'notifications', 'object_storage', 'password_manager', 'radius', 'reports', 'saas_app_management', 'software', 'sso', 'systems', 'workflows']
    serviceList = ((service_env.replace(" ", "")).lower()).split(",")
    
    if 'all' in serviceList and len(serviceList) > 1:
        logger.warning("Configuration contains 'all' alongside specific services. Defaulting to 'all'.")
        serviceList = ['all']

    logger.info("Preparing JumpCloud authentication...")
    try:
        jc_auth_prepared = prepare_jc_auth(jcapikeyarn, jc_auth_type)
    except Exception as e:
        logger.error(f"Auth prep failed: {e}")
        raise Exception(e)

    for org_id in org_ids:
        org_label = mask_org_id_for_logs(org_id)
        logger.info(f"[ORCHESTRATOR] Organization context: {org_label}")
        
        try:
            headers = build_jc_request_headers_from_prepared(jc_auth_prepared, org_id)
        except ValueError as e:
            logger.error(str(e))
            continue

        for service in serviceList:
            if service not in availableServices:
                logger.error(f"Unknown service: {service}")
                continue

            start_iso = previousTime.isoformat("T").replace("+00:00", "Z")
            end_iso = now.isoformat("T").replace("+00:00", "Z")
            
            count_url = "https://api.jumpcloud.com/insights/directory/v1/events/count"
            count_body = {'service': [service], 'start_time': start_iso, 'end_time': end_iso}
            
            try:
                response = requests.post(count_url, json=count_body, headers=headers)
                response.raise_for_status()
                total_events = json.loads(response.text).get('count', 0)
                logger.info(f"Total events for org {org_label} | {service}: {total_events}")
            except Exception as e:
                logger.warning(f"Failed to get event count for org {org_label} | {service}: {e}")
                total_events = MAX_EVENTS_PER_WORKER 
            
            if total_events == 0:
                logger.info(f"No events for org {org_label} | {service} between {start_iso} and {end_iso}. Skipping.")
                continue 

            num_chunks = max(1, math.ceil(total_events / MAX_EVENTS_PER_WORKER))
            time_slices = chunk_time_range(previousTime, now, num_chunks)
            
            for slice_start, slice_end in time_slices:
                message_body = {
                    'service': service,
                    'start_time': slice_start.isoformat("T").replace("+00:00", "Z"),
                    'end_time': slice_end.isoformat("T").replace("+00:00", "Z"),
                    'org_id': org_id
                }
                sqs.send_message(
                    QueueUrl=queueUrl,
                    MessageBody=json.dumps(message_body)
                )
                logger.info(f"Queued job for org={org_label} | {service}: {message_body['start_time']} to {message_body['end_time']}")

    logger.info("--- ORCHESTRATOR COMPLETE ---")
    return {"statusCode": 200, "body": "Orchestration complete"}

# ==============================================================================
# WORKER FUNCTION
# ==============================================================================
def jc_worker(event, context):
    logger.info("--- WORKER STARTED ---")
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        bucketName = os.environ['BucketName']
        JsonFormat = os.environ.get('JsonFormat', 'MultiLine')
        jc_auth_type = os.environ.get("JcAuthType", JC_AUTH_TYPE_API_KEY)
    except KeyError as e:
        logger.error(f"Missing environment variable: {e}")
        raise Exception(e)

    logger.info("Worker preparing JumpCloud authentication...")
    try:
        jc_auth_prepared = prepare_jc_auth(jcapikeyarn, jc_auth_type)
    except Exception as e:
        logger.error(f"Auth prep failed: {e}")
        raise Exception(e)
    
    for record in event['Records']:
        payload = json.loads(record['body'])
        service = payload['service']
        startDate = payload['start_time']
        endDate = payload['end_time']
        org_id = payload.get('org_id', '')
        
        org_label = mask_org_id_for_logs(org_id)
        logger.info(f"Processing org={org_label} | {service} from {startDate} to {endDate}")

        try:
            headers = build_jc_request_headers_from_prepared(jc_auth_prepared, org_id)
        except ValueError as e:
            logger.error(str(e))
            raise Exception(e)

        url = "https://api.jumpcloud.com/insights/directory/v1/events"
        body = {
            'service': [service],
            'start_time': startDate,
            'end_time': endDate,
            "limit": 10000
        }
        finalData = []
        
        try:
            response = requests.post(url, json=body, headers=headers)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error fetching data: {e}")
            raise Exception(e)
            
        if response.text.strip() == "[]":
            logger.info(f"No results found for org={org_label} | {service} in this time slice.")
            continue
            
        data = json.loads(response.text)
        
        while int(response.headers.get("X-Result-Count", 0)) >= int(response.headers.get("X-Limit", 10000)):
            body["search_after"] = json.loads(response.headers["X-Search_After"])
            response = requests.post(url, json=body, headers=headers)
            response.raise_for_status()
            data += json.loads(response.text)
            
        finalData += data

        if len(finalData) == 0:
            continue
            
        finalData.sort(key=lambda x: x['timestamp'], reverse=True)
        
        org_prefix = f"{org_id}_" if org_id else ""
        outfileName = f"jc_directoryinsights_{org_prefix}{service}_{startDate}_{endDate}.json.gz"
        outfileName = outfileName.replace(":", "-")
        tmpFilePath = f"/tmp/{outfileName}"
        
        try:
            with gzip.GzipFile(filename=tmpFilePath, mode="w", compresslevel=9) as gzOutfile:
                if JsonFormat == "SingleLine":
                    gzOutfile.write(('[' + ',\n'.join(json.dumps(i) for i in finalData) + ']').encode('UTF-8'))
                else:
                    gzOutfile.write(json.dumps(finalData, indent=2).encode("UTF-8"))
        except Exception as e:
            logger.error(f"Error compressing file: {e}")
            raise Exception(e)

        try:
            s3 = boto3.client('s3')
            s3.upload_file(tmpFilePath, bucketName, outfileName)
            _log_object_name = mask_org_id_for_logs(org_id) + outfileName.split(org_id)[-1] if org_id else outfileName
            logger.info(f"Successfully uploaded {_log_object_name} to {bucketName}")
        except ClientError as e:
            logger.error(f"Error uploading to S3: {e}")
            raise Exception(e)
            
    logger.info("--- WORKER COMPLETE ---")
    return {"statusCode": 200, "body": "Worker process complete"}