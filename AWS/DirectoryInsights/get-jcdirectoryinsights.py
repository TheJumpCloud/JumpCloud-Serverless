import os, json, boto3, requests, gzip, logging, datetime
from botocore.exceptions import ClientError
from croniter import croniter

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_secret(secret_name):
    """Retrieves the secret value from AWS Secrets Manager."""
    client = boto3.client(service_name='secretsmanager')
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except ClientError as e:
        logger.error(f"Error retrieving secret: {e}")
        raise Exception(e)

def get_cron_time(cronExpression, timeTolerance):
    """Checks if the current time is within a tolerance of the cron schedule."""
    # Use UTC explicitly to prevent timezone mismatch
    now = datetime.datetime.utcnow() 
    cronParts = cronExpression.split()
    cronExpression = " ".join(cronParts[:5])
    try:
        # Add the tolerance (instead of subtracting) in case EventBridge fires a few seconds early
        cronTime = croniter(cronExpression, now + datetime.timedelta(seconds=timeTolerance))
        
        # Get the most recent scheduled cron tick (e.g. 18:50:00)
        currentCronTime = cronTime.get_prev(datetime.datetime)
        
        # Get the scheduled cron tick right before that one (e.g. 18:45:00)
        previousCronTime = cronTime.get_prev(datetime.datetime)
        
        return currentCronTime, previousCronTime
    except Exception as e:
        logger.error(f"Error in cron expression: {e}")
        raise Exception(e)

def chunk_time_range(start_time, end_time, chunks):
    """Splits a time range into an array of smaller time ranges."""
    delta = (end_time - start_time) / chunks
    return [(start_time + delta * i, start_time + delta * (i + 1)) for i in range(chunks)]

# ==============================================================================
# 1. THE ORCHESTRATOR FUNCTION
# ==============================================================================
def jc_orchestrator(event, context):
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        cronExpression = os.environ['CronExpression']
        queueUrl = os.environ['SqsQueueUrl']
        service_env = os.environ['service']
    except KeyError as e:
        logger.error(f"Missing env var: {e}")
        raise Exception(e)

    jcapikey = get_secret(jcapikeyarn)
    timeTolerance = 10
    now, previousTime = get_cron_time(cronExpression, timeTolerance)
    
    sqs = boto3.client('sqs')
    
    availableServices = ['all','alerts','directory','password_manager','sso','radius','systems','software','mdm','object_storage','saas_app_management','access_management']
    serviceList = ((service_env.replace(" ", "")).lower()).split(",")
    
    headers = {
        'x-api-key': jcapikey,
        'content-type': "application/json",
        'user-agent': "JumpCloud_AWSServerless.DirectoryInsights/3.0.0"
    }

    MAX_EVENTS_PER_WORKER = 1 

    for service in serviceList:
        if service not in availableServices:
            logger.error(f"Unknown service: {service}")
            continue

        start_iso = previousTime.isoformat("T") + "Z"
        end_iso = now.isoformat("T") + "Z"
        
        # Hit the count endpoint to see if we even need to pull data
        count_url = "https://api.jumpcloud.com/insights/directory/v1/events/count"
        count_body = {'service': [service], 'start_time': start_iso, 'end_time': end_iso}
        
        try:
            response = requests.post(count_url, json=count_body, headers=headers)
            response.raise_for_status()
            total_events = json.loads(response.text).get('count', 0) # Get the event count
        except Exception as e:
            logger.error(f"Failed to get event count for {service}: {e}")
            continue
        
        if total_events == 0:
            logger.info(f"No events for {service} between {start_iso} and {end_iso}. Skipping.")
            continue 

        # Slice the time if there are too many events
        num_chunks = max(1, int((total_events // MAX_EVENTS_PER_WORKER) + 1))
        time_slices = chunk_time_range(previousTime, now, num_chunks)
        logger.info(f"Chuncks: {num_chunks}")
        logger.info(f"Slices: {time_slices}")
        
        
        # Queue the jobs into SQS
        for slice_start, slice_end in time_slices:
            message_body = {
                'service': service,
                'start_time': slice_start.isoformat("T") + "Z",
                'end_time': slice_end.isoformat("T") + "Z"
            }
            sqs.send_message(
                QueueUrl=queueUrl,
                MessageBody=json.dumps(message_body)
            )
            logger.info(f"Queued job for {service}: {message_body['start_time']} to {message_body['end_time']}")

    return {"statusCode": 200, "body": "Orchestration complete"}

# ==============================================================================
# 2. THE WORKER FUNCTION
# ==============================================================================
def jc_worker(event, context):
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        bucketName = os.environ['BucketName']
        orgId = os.environ.get('OrgId', '')
        JsonFormat = os.environ.get('JsonFormat', 'MultiLine')
    except KeyError as e:
        logger.error(f"Missing environment variable: {e}")
        raise Exception(e)

    jcapikey = get_secret(jcapikeyarn)
    
    for record in event['Records']:
        payload = json.loads(record['body'])
        service = payload['service']
        startDate = payload['start_time']
        endDate = payload['end_time']
        
        logger.info(f"Processing {service} from {startDate} to {endDate}")

        url = "https://api.jumpcloud.com/insights/directory/v1/events"
        body = {
            'service': [service],
            'start_time': startDate,
            'end_time': endDate,
            "limit": 10000
        }
        
        headers = {
            'x-api-key': jcapikey,
            'content-type': "application/json",
            'user-agent': "JumpCloud_AWSServerless.DirectoryInsights/3.0.0"
        }
        if orgId != '':
            headers['x-org-id'] = orgId
            
        finalData = []
        
        try:
            response = requests.post(url, json=body, headers=headers)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error fetching data: {e}")
            raise Exception(e)
            
        if response.text.strip() == "[]":
            logger.info(f"No results found for {service} in this time slice.")
            continue
            
        data = json.loads(response.text)
        
        # Paginate if needed
        while int(response.headers.get("X-Result-Count", 0)) >= int(response.headers.get("X-Limit", 10000)):
            body["search_after"] = json.loads(response.headers["X-Search_After"])
            response = requests.post(url, json=body, headers=headers)
            response.raise_for_status()
            data += json.loads(response.text)
            
        finalData += data

        if len(finalData) == 0:
            continue
            
        finalData.sort(key=lambda x: x['timestamp'], reverse=True)
        outfileName = f"jc_directoryinsights_{service}_{startDate}_{endDate}.json.gz"
        outfileName = outfileName.replace(":", "-") # Safe characters for S3
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
            logger.info(f"Successfully uploaded {outfileName} to {bucketName}")
        except ClientError as e:
            logger.error(f"Error uploading to S3: {e}")
            raise Exception(e)
            
    return {"statusCode": 200, "body": "Worker process complete"}