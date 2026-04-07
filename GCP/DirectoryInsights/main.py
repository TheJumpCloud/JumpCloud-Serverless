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
        print(f"Error retrieving secret {secret_name}: {e}")
        raise Exception(e)

def get_cron_time(cron_expression, time_tolerance):
    """Checks the schedule, with GCP 'Force Run' detection."""
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        cron_time = croniter(cron_expression, now + datetime.timedelta(seconds=time_tolerance))
        current_cron_time = cron_time.get_prev(datetime.datetime)
        previous_cron_time = cron_time.get_prev(datetime.datetime)
        
        # GCP "Force Run" Detection
        if (now - current_cron_time).total_seconds() > 60: 
            # Grab the requested lookback window from the environment (defaults to 30 days). This functionality is used for testing. Change the number value on how many event days you'd like to pull (max 90 days) 
            force_days = int(os.environ.get('force_run_days', 30))
            
            print(f"Manual Force Run detected! Adjusting search window to exactly {force_days} days from right now.")
            
            force_run_start_time = now - datetime.timedelta(days=force_days) 
            return now, force_run_start_time
            
        return current_cron_time, previous_cron_time
    except Exception as e:
        print(f"Error in cron expression '{cron_expression}': {e}")
        raise Exception(e)

def chunk_time_range(start_time, end_time, chunks):
    """Splits a time range into an array of smaller time ranges."""
    delta = (end_time - start_time) / chunks
    return [(start_time + delta * i, start_time + delta * (i + 1)) for i in range(chunks)]

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
        print("Environment variables loaded successfully.")
    except KeyError as e:
        print(f"Missing env var: {e}")
        return f"Missing env var: {e}", 500

    print("Fetching API Key from Secret Manager...")
    jcapikey = get_secret(project_id, jc_api_key_secret_name)
    
    jc_org_id = "" 
    if jc_org_id_secret_name:
        print("Fetching Org ID from Secret Manager...")
        fetched_id = get_secret(project_id, jc_org_id_secret_name).strip()
        if fetched_id:
            jc_org_id = fetched_id
            print(f"Org ID loaded: {jc_org_id}")

    time_tolerance = 10
    now, previous_time = get_cron_time(cron_schedule, time_tolerance)
    print(f"Search Window: {previous_time} to {now}")
    
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    
    available_services = ['all', 'access_management', 'alerts', 'asset_management', 'directory', 'ldap', 'mdm', 'notifications', 'object_storage', 'password_manager', 'radius', 'reports', 'saas_app_management', 'software', 'sso', 'systems', 'workflows']
    service_list = ((service_env.replace(" ", "")).lower()).split(",")
    
    if 'all' in service_list and len(service_list) > 1:
        print("Configuration contains 'all' alongside specific services. Defaulting to 'all'.")
        service_list = ['all']
    
    headers = {
        'x-api-key': jcapikey,
        'content-type': "application/json",
        'user-agent': "JumpCloud_GCPServerless.DirectoryInsights/3.0.0"
    }
    if jc_org_id != '':                 
        headers['x-org-id'] = jc_org_id

    MAX_EVENTS_PER_WORKER = 25000

    for service in service_list:
        if service not in available_services:
            print(f"Unknown service: {service}")
            continue

        start_iso = previous_time.isoformat("T").replace("+00:00", "Z")
        end_iso = now.isoformat("T").replace("+00:00", "Z")
        
        count_url = "https://api.jumpcloud.com/insights/directory/v1/events/count"
        
        # Omit the service parameter if querying 'all' to prevent 400 Bad Request
        count_body = {'service': [service], 'start_time': start_iso, 'end_time': end_iso}
        
        print(f"[ORCHESTRATOR] Querying Count URL: {count_url} | Service: {service}")
        print(f"[ORCHESTRATOR] Payload: {count_body}")
        try:
            response = requests.post(count_url, json=count_body, headers=headers)
            response.raise_for_status()
            total_events = json.loads(response.text).get('count', 0)
            print(f"Total events found for {service}: {total_events}")
        except Exception as e:
            print(f"Failed to get event count for {service}. Defaulting to full slice. Error: {e}")
            total_events = MAX_EVENTS_PER_WORKER 
        
        if total_events == 0:
            print(f"No events for {service} between {start_iso} and {end_iso}. Skipping.")
            continue 

        num_chunks = max(1, math.ceil(total_events / MAX_EVENTS_PER_WORKER))
        time_slices = chunk_time_range(previous_time, now, num_chunks)
        print(f"Splitting {service} into {num_chunks} chunk(s) for the workers.")
        
        for slice_start, slice_end in time_slices:
            message_body = {
                'service': service,
                'start_time': slice_start.isoformat("T").replace("+00:00", "Z"),
                'end_time': slice_end.isoformat("T").replace("+00:00", "Z")
            }
            # Publish to Pub/Sub
            publisher.publish(topic_path, json.dumps(message_body).encode("utf-8"))
            print(f"Queued job into Pub/Sub: {service} | {message_body['start_time']} to {message_body['end_time']}")

    print("--- ORCHESTRATOR COMPLETE ---")
    return "Orchestration complete", 200 # Should return 200 everytime even when we can't communicate to the JC API. It should always return event times to be pushed to the worker

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
    except KeyError as e:
        print(f"Missing environment variable: {e}")
        raise Exception(e)

    print("Worker fetching API Key from Secret Manager...")
    jcapikey = get_secret(project_id, jc_api_key_secret_name)
    
    jc_org_id = "" 
    if jc_org_id_secret_name:
        fetched_id = get_secret(project_id, jc_org_id_secret_name).strip()
        if fetched_id:
            jc_org_id = fetched_id

    # Decode Pub/Sub message
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    payload = json.loads(pubsub_message)
    print(f"Received Job Payload: {payload}")
    
    service = payload['service']
    start_date = payload['start_time']
    end_date = payload['end_time']
    
    url = "https://api.jumpcloud.com/insights/directory/v1/events"
    
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
    
    headers = {
        'x-api-key': jcapikey,
        'content-type': "application/json",
        'user-agent': "JumpCloud_GCPServerless.DirectoryInsights/3.0.0"
    }
    if jc_org_id != '':
        headers['x-org-id'] = jc_org_id
        
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
    out_file_name = f"jc_directoryinsights_{service}_{start_date}_{end_date}.json.gz"
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

    # Upload to Cloud Storage
    print(f"Uploading {out_file_name} to Cloud Storage bucket: {bucket_name}...")
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

        ack_ids = []
        moved_count = 0

        for received_message in response.received_messages:
            try:
                # 1. Forward the raw data back to the main topic
                publisher.publish(topic_path, received_message.message.data)
                
                # 2. Save the ID so we can delete it from the DLQ
                ack_ids.append(received_message.ack_id)
                moved_count += 1
            except Exception as e:
                print(f"Failed to publish message {received_message.message.message_id}: {e}")
                # We do NOT add to ack_ids so it stays in the DLQ to try again later

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