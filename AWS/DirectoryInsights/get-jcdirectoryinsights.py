import requests, datetime, json, boto3, os, gzip, logging
from botocore.exceptions import ClientError

def get_secret(secret_name):
    client = boto3.client(service_name='secretsmanager')
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise Exception(e)
    secret = get_secret_value_response['SecretString']
    return secret

def jc_directoryinsights(event, context):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        incrementType = os.environ['incrementType']
        incrementAmount = int(os.environ['incrementAmount'])
        bucketName = os.environ['BucketName']
        service = os.environ['service']
        orgId = os.environ['OrgId']
        JsonFormat = os.environ['JsonFormat']
    except KeyError as e:
        raise Exception(e)

    jcapikey = get_secret(jcapikeyarn)
    now = datetime.datetime.utcnow()

    if incrementType == "minutes" or incrementType == "minute":
        start_dt = now - datetime.timedelta(minutes=incrementAmount)
    elif incrementType == "hours" or incrementType == "hour":
        start_dt = now - datetime.timedelta(hours=incrementAmount)
    elif incrementType == "days" or incrementType == "day":
        start_dt = now - datetime.timedelta(days=incrementAmount)
    else:
        raise Exception("Unknown increment value.")

    start_date = start_dt.isoformat("T") + "Z"
    end_date = now.isoformat("T") + "Z"

    outfileName = "jc_directoryinsights_" + start_date + "_" + end_date + ".json.gz"
    availableServices = ['directory','radius','sso','systems','ldap','mdm','all','object_storage','software','password_manager']
    serviceList = ((service.replace(" ", "")).lower()).split(",")
    for service in serviceList:
        if service not in availableServices:
            raise Exception(f"Unknown service: {service}")
    if 'all' in serviceList and len(serviceList) > 1:
            raise Exception(f"Error - Service List contains 'all' and additional services : {serviceList}")
    finalData = []

    if len(serviceList) > 1:
        for service in serviceList:
            logger.info(f'service: {service},\n start-date: {start_date},\n end-date: {end_date},\n *** Powershell Script *** \n $sourcePath =  "<directory_path>/jc_directoryinsights_{start_date}_{end_date}.json" \n Get-JCEvent -service {service} -StartTime {start_date} -EndTime {end_date} | ConvertTo-Json -Depth 99 | Out-File -FilePath $sourcePath \n $newFileName = "$($sourcePath).gz" \n $srcFileStream = New-Object System.IO.FileStream($sourcePath,([IO.FileMode]::Open),([IO.FileAccess]::Read),([IO.FileShare]::Read)) \n $dstFileStream = New-Object System.IO.FileStream($newFileName,([IO.FileMode]::Create),([IO.FileAccess]::Write),([IO.FileShare]::None)) \n $gzip = New-Object System.IO.Compression.GZipStream($dstFileStream,[System.IO.Compression.CompressionLevel]::SmallestSize) \n $srcFileStream.CopyTo($gzip) \n $gzip.Dispose() \n $srcFileStream.Dispose() \n $dstFileStream.Dispose()\n *** End Script ***' )
    else: 
            logger.info(f'service: {service},\n start-date: {start_date},\n end-date: {end_date},\n *** Powershell Script *** \n $sourcePath =  "<directory_path>/jc_directoryinsights_{start_date}_{end_date}.json" \n Get-JCEvent -service {service} -StartTime {start_date} -EndTime {end_date} | ConvertTo-Json -Depth 99 | Out-File -FilePath $sourcePath \n $newFileName = "$($sourcePath).gz" \n $srcFileStream = New-Object System.IO.FileStream($sourcePath,([IO.FileMode]::Open),([IO.FileAccess]::Read),([IO.FileShare]::Read)) \n $dstFileStream = New-Object System.IO.FileStream($newFileName,([IO.FileMode]::Create),([IO.FileAccess]::Write),([IO.FileShare]::None)) \n $gzip = New-Object System.IO.Compression.GZipStream($dstFileStream,[System.IO.Compression.CompressionLevel]::SmallestSize) \n $srcFileStream.CopyTo($gzip) \n $gzip.Dispose() \n $srcFileStream.Dispose() \n $dstFileStream.Dispose()\n *** End Script ***' )
            
    for service in serviceList:
        url = "https://api.jumpcloud.com/insights/directory/v1/events"
        body = {
            'service': [f"{service}"],
            'start_time': start_date,
            'end_time': end_date,
            "limit": 10000
        }
        headers = {
            'x-api-key': jcapikey,
            'content-type': "application/json",
            'user-agent': "JumpCloud_AWSServerless.DirectoryInsights/1.3.0"
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
                                'Value': '1.3.0'
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