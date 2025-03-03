import requests, datetime, json, boto3, os, gzip, logging, croniter
from botocore.exceptions import ClientError
from croniter import croniter


def get_secret(secret_name):
    """Retrieves the secret value from AWS Secrets Manager.
    Args:
        secret_name: The name of the secret.
    Returns:
        secret: The secret value.
    """
    client = boto3.client(service_name='secretsmanager')
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise Exception(e)
    secret = get_secret_value_response['SecretString']
    return secret

def get_cron_time(cronExpression, timeTolerance):
    """
    Checks if the current time is within a tolerance of the cron schedule.

    Args:
        cronExpression: The cron expression.
        timeTolerance: The tolerance in seconds/timeDelta.

    Returns:
        currentCronTime: The next run time of the cron schedule.
        previousCronTime: The previous run time of the cron schedule.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    now = datetime.datetime.now()
    # Get the first 5 fields of the cron expression
    cronParts = cronExpression.split()
    cronExpression = " ".join(cronParts[:5]) # Get the first 5 fields of the cron expression, this will not include the year field
    logger.info(f'Cron Expression: {cronExpression}')
    try:
        cronTime = croniter(cronExpression, now - datetime.timedelta(seconds=timeTolerance))  # get the previous time with 59 seconds of tolerance
        currentCronTime = cronTime.get_next(datetime.datetime)  # get the next run time from that previous time.
        previousCronTime = cronTime.get_prev(datetime.datetime)  # get the previous run time
        logger.info(f'Current Cron Time: {currentCronTime}')
        logger.info(f'Previous Cron Time: {previousCronTime}')
        # time_diff = abs((now - previousCronTime).total_seconds())
        return currentCronTime, previousCronTime
    except Exception as e:
        logger.error(f"Error in cron expression: {e}")
        # Exit the code and raise an exception
        raise Exception(e)

def jc_directoryinsights(event, context):
    """
    Lambda function to get directory insights from JumpCloud and upload to S3.

    Args:
        event: The event object.
        context: The context object.

    Returns:
        None
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        cronExpression = os.environ['CronExpression']
        bucketName = os.environ['BucketName']
        service = os.environ['service']
        orgId = os.environ['OrgId']
        JsonFormat = os.environ['JsonFormat']
    except KeyError as e:
        raise Exception(e)
    
    jcapikey = get_secret(jcapikeyarn)
    timeTolerance=10
    now, previousTime = get_cron_time(cronExpression, timeTolerance) # get the current time and previous time
    nowSeconds = now.second
    

    # Convert to ISO format
    startDate = previousTime.isoformat("T") + "Z"
    endDate = now.isoformat("T") + "Z"
    
    # If the cronTime is not within the tolerance, error out
    if nowSeconds >= timeTolerance:
        # Timestamps of the cron schedule
        logger.info(f'Timestamps of the cron schedule: {startDate}, {endDate}')
        # Print an instruction to run the powershell script manually and save it to the S3 bucket
        logger.info(f"Please run the powershell script manually and save it to the S3 bucket: {bucketName}")
        logger.info(f'service: {service},\n start-date: {startDate},\n end-date: {endDate},\n *** Powershell Script *** \n $sourcePath =  "<directory_path>/jc_directoryinsights_{startDate}_{endDate}.json" \n Get-JCEvent -service {service} -startDate {startDate} -EndTime {endDate} | ConvertTo-Json -Depth 99 | Out-File -FilePath $sourcePath \n $newFileName = "$($sourcePath).gz" \n $srcFileStream = New-Object System.IO.FileStream($sourcePath,([IO.FileMode]::Open),([IO.FileAccess]::Read),([IO.FileShare]::Read)) \n $dstFileStream = New-Object System.IO.FileStream($newFileName,([IO.FileMode]::Create),([IO.FileAccess]::Write),([IO.FileShare]::None)) \n $gzip = New-Object System.IO.Compression.GZipStream($dstFileStream,[System.IO.Compression.CompressionLevel]::SmallestSize) \n $srcFileStream.CopyTo($gzip) \n $gzip.Dispose() \n $srcFileStream.Dispose() \n $dstFileStream.Dispose()\n *** End Script ***' )

        raise Exception("Cron time is not within the tolerance.") # This will exit the code

    outfileName = "jc_directoryinsights_" + startDate + "_" + endDate + ".json.gz"
    availableServices = ['all', 'alerts', 'directory', 'password_manager', 'sso', 'radius', 'systems', 'software', 'mdm', 'object_storage', 'saas_app_management', 'access_management']
    serviceList = ((service.replace(" ", "")).lower()).split(",")
    for service in serviceList:
        if service not in availableServices:
            raise Exception(f"Unknown service: {service}")
    if 'all' in serviceList and len(serviceList) > 1:
            raise Exception(f"Error - Service List contains 'all' and additional services : {serviceList}")
    finalData = []

    if len(serviceList) > 1:
        for service in serviceList:
            logger.info(f'service: {service},\n start-date: {startDate},\n end-date: {endDate},\n *** Powershell Script *** \n $sourcePath =  "<directory_path>/jc_directoryinsights_{startDate}_{endDate}.json" \n Get-JCEvent -service {service} -startDate {startDate} -EndTime {endDate} | ConvertTo-Json -Depth 99 | Out-File -FilePath $sourcePath \n $newFileName = "$($sourcePath).gz" \n $srcFileStream = New-Object System.IO.FileStream($sourcePath,([IO.FileMode]::Open),([IO.FileAccess]::Read),([IO.FileShare]::Read)) \n $dstFileStream = New-Object System.IO.FileStream($newFileName,([IO.FileMode]::Create),([IO.FileAccess]::Write),([IO.FileShare]::None)) \n $gzip = New-Object System.IO.Compression.GZipStream($dstFileStream,[System.IO.Compression.CompressionLevel]::SmallestSize) \n $srcFileStream.CopyTo($gzip) \n $gzip.Dispose() \n $srcFileStream.Dispose() \n $dstFileStream.Dispose()\n *** End Script ***' )
    else: 
            logger.info(f'service: {service},\n start-date: {startDate},\n end-date: {endDate},\n *** Powershell Script *** \n $sourcePath =  "<directory_path>/jc_directoryinsights_{startDate}_{endDate}.json" \n Get-JCEvent -service {service} -startDate {startDate} -EndTime {endDate} | ConvertTo-Json -Depth 99 | Out-File -FilePath $sourcePath \n $newFileName = "$($sourcePath).gz" \n $srcFileStream = New-Object System.IO.FileStream($sourcePath,([IO.FileMode]::Open),([IO.FileAccess]::Read),([IO.FileShare]::Read)) \n $dstFileStream = New-Object System.IO.FileStream($newFileName,([IO.FileMode]::Create),([IO.FileAccess]::Write),([IO.FileShare]::None)) \n $gzip = New-Object System.IO.Compression.GZipStream($dstFileStream,[System.IO.Compression.CompressionLevel]::SmallestSize) \n $srcFileStream.CopyTo($gzip) \n $gzip.Dispose() \n $srcFileStream.Dispose() \n $dstFileStream.Dispose()\n *** End Script ***' )
            
    for service in serviceList:
        url = "https://api.jumpcloud.com/insights/directory/v1/events"
        body = {
            'service': [f"{service}"],
            'start_time': startDate,
            'end_time': endDate,
            "limit": 10000
        }
        headers = {
            'x-api-key': jcapikey,
            'content-type': "application/json",
            'user-agent': "JumpCloud_AWSServerless.DirectoryInsights/2.0.0"
        }
        if orgId != '':
            headers['x-org-id'] = orgId
        response = requests.post(url, json=body, headers=headers)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(e)
        responseBody = json.loads(response.text)
        if response.text.strip() == "[]":
            cloudwatch = boto3.client('cloudwatch')
            metric = cloudwatch.put_metric_data(
                MetricData=[
                    {
                        'MetricName': f'NoResults_{service}',
                        'Dimensions': [
                            {
                                'Name': 'JumpCloud',
                                'Value': 'DirectoryInsightsServerlessApp'
                            },
                            {
                                'Name': 'Version',
                                'Value': '2.0.0'
                            }
                        ],
                        'Unit': 'None',
                        'Value': 1
                    },
                ],
                Namespace = 'JumpCloudDirectoryInsights'
            )
            continue
        data = responseBody
            
        while (response.headers["X-Result-Count"] >= response.headers["X-Limit"]):
            body["search_after"] = json.loads(response.headers["X-Search_After"])
            response = requests.post(url, json=body, headers=headers)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                raise Exception(e)
            responseBody = json.loads(response.text)
            data = data + responseBody
        finalData += data
        
    if len(finalData) == 0:
        return
    finalData.sort(key = lambda x:x['timestamp'], reverse=True)
    try:
        gzOutfile = gzip.GzipFile(filename="/tmp/" + outfileName, mode="w", compresslevel=9)
        print ("Indent: " + JsonFormat)
        if JsonFormat == "SingleLine":
             gzOutfile.write(('[' + ',\n'.join(json.dumps(i) for i in data) + ']').encode('UTF-8'))
             gzOutfile.close()
        else:
            gzOutfile.write(json.dumps(finalData, indent=2).encode("UTF-8"))
            gzOutfile.close()
           
    except Exception as e:
        raise Exception(e)
    try:
        s3 = boto3.client('s3')
        s3.upload_file("/tmp/" + outfileName, bucketName, outfileName)
    except ClientError as e:
        raise Exception(e)