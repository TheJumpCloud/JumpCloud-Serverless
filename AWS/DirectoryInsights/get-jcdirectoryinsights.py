import requests, datetime, json, boto3, os, gzip
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
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        incrementType = os.environ['incrementType']
        incrementAmount = int(os.environ['incrementAmount'])
        bucketName = os.environ['BucketName']
        service = os.environ['service']
        orgId = os.environ['OrgId']
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
    availableServices = ['directory','radius','sso','systems','ldap','mdm','all']
    serviceList = service.split(",")
    for service in serviceList:
        if service not in availableServices:
            raise Exception(f"Unknown service: {service}")
    finalData = []

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
            'user-agent': "JumpCloud_AWSServerless.DirectoryInsights/0.0.1"
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
                                'Value': '0.0.1'
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
        gzOutfile.write(json.dumps(finalData, indent=2).encode("UTF-8"))
        gzOutfile.close()
    except Exception as e:
        raise Exception(e)

    try:
        s3 = boto3.client('s3')
        s3.upload_file("/tmp/" + outfileName, bucketName, outfileName)
    except ClientError as e:
        raise Exception(e)