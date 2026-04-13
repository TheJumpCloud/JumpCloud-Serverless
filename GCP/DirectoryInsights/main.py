import os
import json
import requests
import gzip
import logging
import datetime
import math
import base64
import re
from croniter import croniter
from google.cloud import secretmanager
from google.cloud import pubsub_v1
from google.cloud import storage

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ==============================================================================
# BIGQUERY SANITIZATION UTILITIES
# ==============================================================================
def sanitize_key(key):
    """Replaces characters that are invalid in BigQuery column names."""
    clean_key = re.sub(r'[^a-zA-Z0-9_]', '_', key)
    # BigQuery columns cannot start with a number
    if clean_key and clean_key[0].isdigit():
        clean_key = '_' + clean_key
    return clean_key

def sanitize_payload(data):
    """Recursively cleans JSON for BigQuery compatibility."""
    if isinstance(data, dict):
        # Convert empty dicts to None (null) to prevent BQ "Unsupported empty struct" errors
        if not data:
            return None
        return {sanitize_key(k): sanitize_payload(v) for k, v in data.items()}
    elif isinstance(data, list):
        # Convert empty lists to None
        if not data:
            return None
        return [sanitize_payload(item) for item in data]
    else:
        return data

# ==============================================================================
# CORE HELPER FUNCTIONS
# ==============================================================================
def get_secret(project_id, secret_name):
    """Retrieves the secret value from GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"Error retrieving secret: {e}")
        raise Exception(e)

# JumpCloud Directory Insights auth: API key (x-api-key) or OAuth client credentials (Bearer + x-org-id).
JC_AUTH_TYPE_API_KEY = "APIKey"
JC_AUTH_TYPE_SERVICE_TOKEN = "ServiceToken"
JC_OAUTH_TOKEN_URL = "https://admin-oauth.id.jumpcloud.com/oauth2/token"
JC_USER_AGENT = "JumpCloud_GCPServerless.DirectoryInsights/3.0.0"


def _normalize_jc_auth_type(value):
    if value is None or str(value).strip() == "":
        return JC_AUTH_TYPE_API_KEY
    return str(value).strip()


def prepare_jc_auth(project_id, api_key_secret_name, auth_type):
    """
    Load credential from Secret Manager once; for ServiceToken, exchange for an OAuth access token once.

    Use with build_jc_request_headers_from_prepared() per org so multi-org runs do not repeat Secret Manager
    access or token round-trips (only x-org-id differs per organization).
    """
    auth_type = _normalize_jc_auth_type(auth_type)
    raw_secret = get_secret(project_id, api_key_secret_name).strip()

    if auth_type == JC_AUTH_TYPE_API_KEY:
        return {"kind": JC_AUTH_TYPE_API_KEY, "api_key": raw_secret}

    if auth_type == JC_AUTH_TYPE_SERVICE_TOKEN:
        if ":" not in raw_secret:
            raise ValueError(
                'ServiceToken auth requires the api-key secret to be "clientID:clientSecret".'
            )
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

    raise ValueError(f"Unknown jc_auth_type: {auth_type!r}; use APIKey or ServiceToken.")


def build_jc_request_headers_from_prepared(prepared, jc_org_id):
    """Build request headers for one org from prepare_jc_auth() result (same credential, org-specific x-org-id)."""
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
            raise ValueError(
                "ServiceToken auth requires an organization ID (jc_org_id / org secret)."
            )
        return {
            "Authorization": f"Bearer {prepared['access_token']}",
            "content-type": "application/json",
            "user-agent": JC_USER_AGENT,
            "x-org-id": jc_org_id,
        }

    raise ValueError(f"Unknown prepared auth kind: {kind!r}")


def get_jc_request_headers(project_id, api_key_secret_name, jc_org_id, auth_type):
    """
    Build HTTP headers for Insights API calls (single org). Fetches secret once and obtains OAuth token once
    when using ServiceToken — suitable for the Worker, which handles one org per invocation.
    """
    prepared = prepare_jc_auth(project_id, api_key_secret_name, auth_type)
    return build_jc_request_headers_from_prepared(prepared, jc_org_id)


def parse_jc_multi_org_flag(value):
    """True when env jc_multi_org enables comma-separated org list in the org secret."""
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def build_org_id_list(org_secret_raw, multi_org):
    """
    Build the list of org IDs to process.

    multi_org False: one org; empty secret yields [''] (optional x-org-id for API key).
    multi_org True: split on comma; whitespace trimmed; empty list if no ids.
    """
    raw = (org_secret_raw or "").strip()
    if multi_org:
        return [p.strip() for p in raw.split(",") if p.strip()]
    if raw:
        return [raw]
    return [""]


def mask_org_id_for_logs(org_id):
    """
    Log-safe org ID: first four characters, remainder replaced with asterisks.
    Does not alter values used for API calls, Pub/Sub payloads, or object names.
    """
    if org_id is None or str(org_id).strip() == "":
        return "(no x-org-id)"
    s = str(org_id).strip()
    n = len(s)
    show = min(4, n)
    return s[:show] + "*" * (n - show)


def mask_org_id_in_text(text, org_id):
    """Replace a literal org id in a string once (e.g. log line that echoes a filename)."""
    if not org_id or not text:
        return text
    oid = str(org_id).strip()
    if not oid:
        return text
    return text.replace(oid, mask_org_id_for_logs(oid), 1)


def get_cron_time(cron_expression, time_tolerance):
    """Calculates the current and previous cron execution times."""
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        cron_time = croniter(cron_expression, now + datetime.timedelta(seconds=time_tolerance))
        current_cron_time = cron_time.get_prev(datetime.datetime)
        previous_cron_time = cron_time.get_prev(datetime.datetime)
            
        return current_cron_time, previous_cron_time
        
    except Exception as e:
        print(f"Error in cron expression '{cron_expression}': {e}")
        raise Exception(e)

def chunk_time_range(start_time, end_time, chunks):
    """Splits a time range into an array of smaller time ranges."""
    delta = (end_time - start_time) / chunks
    return [(start_time + delta * i, start_time + delta * (i + 1)) for i in range(chunks)]

def parse_utc_datetime(value):
    """
    Parse start_time / end_time from HTTP JSON.

    Dynamic (evaluated at request time, UTC):
      - "now" — current instant
      - "now-30" or "now-30d" — 30 days before now (suffix: d=days, h=hours, m=minutes, s=seconds; bare number = days)

    Fixed: ISO-8601, or YYYY-MM-DD:HH:MM:SS (colon between date and time). Naive values are UTC.
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
    # Allow 2026-03-31:00:00:00 — normalize third colon (date/time boundary) to 'T'
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
# ORCHESTRATOR FUNCTION (Triggered by HTTP via Cloud Scheduler)
# ==============================================================================
def jc_orchestrator(request):
    print("--- ORCHESTRATOR STARTED ---")
    try:
        project_id = os.environ['gcp_project_id']
        jc_api_key_secret_name = os.environ['jc_api_key_secret']
        jc_org_id_secret_name = os.environ.get('jc_org_id', '') 
        cron_schedule = os.environ['cron_schedule']
        topic_name = os.environ['pubsub_topic']
        service_env = os.environ['service']
        jc_auth_type = os.environ.get("jc_auth_type", JC_AUTH_TYPE_API_KEY)
        jc_multi_org = parse_jc_multi_org_flag(os.environ.get("jc_multi_org"))
        print("Environment variables loaded successfully.")
    except KeyError as e:
        print(f"Missing env var: {e}")
        return f"Missing env var: {e}", 500

    # --- Optional JSON: explicit window (start_time + end_time) or service override ---
    request_json = request.get_json(silent=True) or {}
    raw_start = request_json.get("start_time")
    raw_end = request_json.get("end_time")
    test_service = request_json.get("service")

    if test_service:
        print(f"[MANUAL] Overriding default service with: {test_service}")
        service_env = test_service

    org_secret_raw = ""
    if jc_org_id_secret_name:
        print("Fetching Org ID(s) from Secret Manager...")
        org_secret_raw = get_secret(project_id, jc_org_id_secret_name).strip()
        if org_secret_raw:
            print("Org secret loaded")

    org_ids = build_org_id_list(org_secret_raw, jc_multi_org)
    if jc_multi_org and not org_ids:
        error_msg = (
            "jc_multi_org is true but no organization IDs were found in the org secret "
            "(use a comma-separated list, e.g. orgId1,orgId2)."
        )
        print(error_msg)
        return error_msg, 400

    # --- Time window: explicit [start_time, end_time] OR cron schedule ---
    has_start = raw_start is not None and str(raw_start).strip() != ""
    has_end = raw_end is not None and str(raw_end).strip() != ""

    if has_start ^ has_end:
        error_msg = "Provide both start_time and end_time for a manual window, or omit both for scheduled (cron) mode."
        print(error_msg)
        return error_msg, 400

    if has_start and has_end:
        try:
            window_start = parse_utc_datetime(raw_start)
            window_end = parse_utc_datetime(raw_end)
        except ValueError as e:
            error_msg = f"Invalid start_time or end_time: {e}"
            print(error_msg)
            return error_msg, 400
        if window_start >= window_end:
            error_msg = "start_time must be strictly before end_time."
            print(error_msg)
            return error_msg, 400
        print(f"[MANUAL WINDOW] {window_start.isoformat()} to {window_end.isoformat()}")
    else:
        time_tolerance = 10
        window_end, window_start = get_cron_time(cron_schedule, time_tolerance)

    print(f"Search Window: {window_start} to {window_end}")
    
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    
    available_services = ['all', 'access_management', 'alerts', 'asset_management', 'directory', 'ldap', 'mdm', 'notifications', 'object_storage', 'password_manager', 'radius', 'reports', 'saas_app_management', 'software', 'sso', 'systems', 'workflows']
    service_list = ((service_env.replace(" ", "")).lower()).split(",")
    
    if 'all' in service_list and len(service_list) > 1:
        print("Configuration contains 'all' alongside specific services. Defaulting to 'all'.")
        service_list = ['all']

    # Grab the max events from the environment, defaulting to 25000 if not set
    MAX_EVENTS_PER_WORKER = int(os.environ.get('max_events_per_worker', 25000)) 

    # Create a list to track all of our Pub/Sub publish operations
    publish_futures = []

    # One Secret Manager read + one OAuth token exchange (ServiceToken); per-org only varies x-org-id.
    print("Preparing JumpCloud authentication (Secret Manager; OAuth if ServiceToken)...")
    try:
        jc_auth_prepared = prepare_jc_auth(
            project_id, jc_api_key_secret_name, jc_auth_type
        )
    except ValueError as e:
        print(str(e))
        return str(e), 400
    except requests.RequestException as e:
        print(f"JumpCloud OAuth or network error: {e}")
        return f"Authentication failed: {e}", 502

    for org_id in org_ids:
        org_label = mask_org_id_for_logs(org_id)
        print(f"[ORCHESTRATOR] Organization context: {org_label}")

        try:
            headers = build_jc_request_headers_from_prepared(jc_auth_prepared, org_id)
        except ValueError as e:
            print(str(e))
            return str(e), 400

        for service in service_list:
            if service not in available_services:
                print(f"Unknown service: {service}")
                continue

            start_iso = window_start.isoformat("T").replace("+00:00", "Z")
            end_iso = window_end.isoformat("T").replace("+00:00", "Z")

            count_url = "https://api.jumpcloud.com/insights/directory/v1/events/count"

            count_body = {'service': [service], 'start_time': start_iso, 'end_time': end_iso}

            print(f"[ORCHESTRATOR] Querying Count URL: {count_url} | Org: {org_label} | Service: {service}")
            print(f"[ORCHESTRATOR] Payload: {count_body}")
            try:
                response = requests.post(count_url, json=count_body, headers=headers)
                response.raise_for_status()
                total_events = json.loads(response.text).get('count', 0)
                print(f"Total events found for org {org_label} | {service}: {total_events}")
            except Exception as e:
                print(f"Failed to get event count for org {org_label} | {service}. Defaulting to full slice. Error: {e}")
                total_events = MAX_EVENTS_PER_WORKER

            if total_events == 0:
                print(f"No events for org {org_label} | {service} between {start_iso} and {end_iso}. Skipping.")
                continue

            num_chunks = max(1, math.ceil(total_events / MAX_EVENTS_PER_WORKER))
            time_slices = chunk_time_range(window_start, window_end, num_chunks)
            print(f"Splitting org {org_label} | {service} into {num_chunks} chunk(s) for the workers.")

            for slice_start, slice_end in time_slices:
                message_body = {
                    'service': service,
                    'start_time': slice_start.isoformat("T").replace("+00:00", "Z"),
                    'end_time': slice_end.isoformat("T").replace("+00:00", "Z"),
                    'org_id': org_id,
                }

                future = publisher.publish(topic_path, json.dumps(message_body).encode("utf-8"))
                publish_futures.append(future)

                print(
                    f"Queued job into Pub/Sub: org={org_label} | {service} | "
                    f"{message_body['start_time']} to {message_body['end_time']}"
                )

    # Wait for all messages to be successfully published before exiting the function
    if publish_futures:
        print(f"Waiting for {len(publish_futures)} Pub/Sub messages to finish sending...")
        for future in publish_futures:
            try:
                # Calling .result() forces the code to pause until this specific message is confirmed delivered
                future.result() 
            except Exception as e:
                print(f"Failed to publish message to Pub/Sub: {e}")
                raise Exception(f"Pub/Sub publish failed: {e}")

    print("--- ORCHESTRATOR COMPLETE ---")
    return "Orchestration complete", 200

# ==============================================================================
# WORKER FUNCTION (Triggered by Pub/Sub)
# ==============================================================================
def jc_worker(event, context):
    print("--- WORKER STARTED ---")
    try:
        project_id = os.environ['gcp_project_id']
        jc_api_key_secret_name = os.environ['jc_api_key_secret']
        bucket_name = os.environ['bucket_name']
        jc_org_id_secret_name = os.environ.get('jc_org_id', '')
        json_format = os.environ.get('json_format', 'MultiLine') # MultiLine, SingleLine, or NDJson
        jc_auth_type = os.environ.get("jc_auth_type", JC_AUTH_TYPE_API_KEY)
        jc_multi_org = parse_jc_multi_org_flag(os.environ.get("jc_multi_org"))
    except KeyError as e:
        print(f"Missing environment variable: {e}")
        raise Exception(e)

    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    payload = json.loads(pubsub_message)
    _log_payload = dict(payload)
    if "org_id" in _log_payload:
        _log_payload["org_id"] = mask_org_id_for_logs(_log_payload.get("org_id"))
    print(f"Received Job Payload: {_log_payload}")

    if "org_id" in payload:
        _oid = payload.get("org_id")
        jc_org_id = "" if _oid is None else str(_oid).strip()
    elif jc_multi_org:
        raise ValueError(
            "Pub/Sub message is missing org_id; redeploy the orchestrator so each job includes org_id."
        )
    else:
        jc_org_id = ""
        if jc_org_id_secret_name:
            fetched_id = get_secret(project_id, jc_org_id_secret_name).strip()
            if fetched_id:
                jc_org_id = fetched_id

    print("Worker building JumpCloud request headers (credentials from Secret Manager)...")
    try:
        headers = get_jc_request_headers(
            project_id, jc_api_key_secret_name, jc_org_id, jc_auth_type
        )
    except ValueError as e:
        print(str(e))
        raise Exception(e)
    except requests.RequestException as e:
        print(f"JumpCloud OAuth or network error: {e}")
        raise Exception(e)

    service = payload['service']
    start_date = payload['start_time']
    end_date = payload['end_time']
    
    url = "https://api.jumpcloud.com/insights/directory/v1/events"
    body = {
        'service': [service],
        'start_time': start_date,
        'end_time': end_date,
        "limit": 10000
    }

    final_data = []
    
    print(f"[WORKER] Querying Events URL: {url}")
    print(f"[WORKER] Payload: {body}")
    
    try:
        response = requests.post(url, json=body, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Error fetching data from JumpCloud: {e}")
        raise Exception(e)
        
    if response.text.strip() == "[]":
        print(f"No results returned for {service} in this time slice. Exiting cleanly.")
        return
        
    data = json.loads(response.text)
    print(f"Fetched initial batch of {len(data)} records.")
    
    # Paginate
    while int(response.headers.get("X-Result-Count", 0)) >= int(response.headers.get("X-Limit", 10000)):
        print("Pagination limit reached. Fetching next batch...")
        body["search_after"] = json.loads(response.headers["X-Search_After"])
        response = requests.post(url, json=body, headers=headers)
        response.raise_for_status()
        new_data = json.loads(response.text)
        data += new_data
        print(f"Fetched additional {len(new_data)} records.")
        
    final_data += data

    if len(final_data) == 0:
        return
        
    final_data.sort(key=lambda x: x['timestamp'], reverse=True)
    org_prefix = f"{jc_org_id}_" if jc_org_id else ""
    out_file_name = f"jc_directoryinsights_{org_prefix}{service}_{start_date}_{end_date}.json.gz"
    out_file_name = out_file_name.replace(":", "-") # Safe characters for Storage
    tmp_file_path = f"/tmp/{out_file_name}"
    
    # Compress the file
    print(f"Formatting as {json_format} and compressing {len(final_data)} records to GZIP...")
    try:
        with gzip.GzipFile(filename=tmp_file_path, mode="w", compresslevel=9) as gz_out_file:
            if json_format == "NDJson":
                # Apply BigQuery sanitization and write line-by-line
                for item in final_data:
                    cleaned_item = sanitize_payload(item)
                    gz_out_file.write((json.dumps(cleaned_item) + '\n').encode('UTF-8'))
            elif json_format == "SingleLine":
                gz_out_file.write(('[' + ',\n'.join(json.dumps(i) for i in final_data) + ']').encode('UTF-8'))
            else:
                gz_out_file.write(json.dumps(final_data, indent=2).encode("UTF-8"))
    except Exception as e:
        print(f"Error compressing file: {e}")
        raise Exception(e)

    # Upload to Cloud Storage (log line masks org segment; object name remains full org id)
    _log_object_name = mask_org_id_in_text(out_file_name, jc_org_id)
    print(f"Uploading {_log_object_name} to Cloud Storage bucket: {bucket_name}...")
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(out_file_name)
        
        # Explicit content_type forces browsers to download instead of displaying raw binary text
        blob.upload_from_filename(tmp_file_path, content_type='application/gzip')
        
        print(f"SUCCESS! File uploaded to GCS.")
    except Exception as e:
        print(f"Error uploading to GCS: {e}")
        raise Exception(e)
        
    print("--- WORKER COMPLETE ---")
    
    # (Keep all your existing imports and code above this line)

# ==============================================================================
# REDRIVE FUNCTION (Triggered by HTTP)
# ==============================================================================
def redrive_dlq(request):
    """HTTP Cloud Function to redrive messages from a DLQ to a Main Topic."""
    print("--- REDRIVE INITIATED ---")
    
    try:
        project_id = os.environ.get('gcp_project_id')
        dlq_sub_id = os.environ.get('dlq_sub_id')
        main_topic_id = os.environ.get('main_topic_id')

        if not all([project_id, dlq_sub_id, main_topic_id]):
            return ("Missing required environment variables.", 500)

        subscriber = pubsub_v1.SubscriberClient()
        publisher = pubsub_v1.PublisherClient()

        subscription_path = subscriber.subscription_path(project_id, dlq_sub_id)
        topic_path = publisher.topic_path(project_id, main_topic_id)

        print(f"Pulling messages from {dlq_sub_id}...")
        
        # Pull up to 100 messages at a time
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 100}
        )

        if not response.received_messages:
            print("DLQ is empty! Nothing to move.")
            return ("DLQ is empty. No messages moved.", 200)

        # 1. Create a list to track the publish operations and their associated ack_ids
        publish_tasks = []

        for received_message in response.received_messages:
            # Fire off the publish command and capture the Future
            future = publisher.publish(topic_path, received_message.message.data)
            
            # Store the Future alongside the ack_id and message_id so we can evaluate them together later
            publish_tasks.append({
                "future": future,
                "ack_id": received_message.ack_id,
                "msg_id": received_message.message.message_id
            })

        ack_ids = []
        moved_count = 0

        # 2. Wait for each publish to finish
        for task in publish_tasks:
            try:
                # This forces the code to wait for confirmation that the main topic received it
                task["future"].result()
                
                # If we get here, it succeeded! It is now safe to queue it for deletion from the DLQ
                ack_ids.append(task["ack_id"])
                moved_count += 1
            except Exception as e:
                print(f"Failed to publish message {task['msg_id']}: {e}")
                # We intentionally do NOT add it to ack_ids, so it safely remains in the DLQ

        # 3. Tell the DLQ we successfully moved them, so it can delete them safely
        if ack_ids:
            subscriber.acknowledge(
                request={"subscription": subscription_path, "ack_ids": ack_ids}
            )
            
        result_message = f"Successfully redelivered {moved_count} messages to {main_topic_id}!"
        print(result_message)
        
        return (result_message, 200)

    except Exception as e:
        print(f"Error during redrive: {e}")
        return (f"Failed to pull messages: {e}", 500)