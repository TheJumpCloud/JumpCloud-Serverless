import requests, datetime, json, boto3, os, gzip, base64

def get_secret(secret_name):
    client = boto3.client(service_name='secretsmanager')
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise Exception(e)

    if 'SecretString' in get_secret_value_response:
        secret = get_secret_value_response['SecretString']
        return json.loads(secret)
    else:
        decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
        return decoded_binary_secret

def jc_directoryinsights(event, context):
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        incrementType = os.environ['incrementType']
        incrementAmount = int(os.environ['incrementAmount'])
        bucketName = os.environ['BucketName']
    except KeyError as e:
        raise Exception(e)

    jcapikey = get_secret(jcapikeyarn)
    now = datetime.datetime.utcnow()

    if incrementType == "minutes":
        start_dt = now - datetime.timedelta(minutes=incrementAmount)
    elif incrementType == "minute":
        start_dt = now - datetime.timedelta(minutes=incrementAmount)
    elif incrementType == "hours":
        start_dt = now - datetime.timedelta(hours=incrementAmount)
    elif incrementType == "hour":
        start_dt = now - datetime.timedelta(minutes=incrementAmount)
    elif incrementType == "days":
        start_dt = now - datetime.timedelta(days=incrementAmount)
    elif incrementType == "day":
        start_dt = now - datetime.timedelta(days=incrementAmount)
    else:
        raise Exception("Unknown increment value.")

    start_date = start_dt.isoformat("T") + "Z"
    end_date = now.isoformat("T") + "Z"

    #fileStartDate = datetime.datetime.strftime(start_dt, "%m-%d-%YT%H-%M-%SZ")
    #fileEndDate = datetime.datetime.strftime(now, "%m-%d-%YT%H-%M-%SZ")
    outfileName = "jc_directoryinsights_" + start_date + "_" + end_date + ".json.gz"

    url = "https://api.jumpcloud.com/insights/directory/v1/events"

    body = {
        'service': ["all"],
        'start_time': start_date,
        'end_time': end_date,
        "limit": 10000
    }
    headers = {
        'x-api-key': jcapikey,
        'content-type': "application/json",
        'user-agent': "JumpCloud_AWSServerless.DirectoryInsights/0.0.1"
        }

    try:
        response = requests.post(url, json=body, headers=headers)
        responseBody = json.loads(response.text)
    except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
        raise Exception(e)

    # Change to CloudWatch Metrics
    if response.text.strip() == "[]":
        raise Exception("There have been no events in the last {0} {1}.".format(incrementAmount, incrementType))

    data = responseBody

    while (response.headers["X-Result-Count"] >= response.headers["X-Limit"]):
        body["search_after"] = json.loads(response.headers["X-Search_After"])
        try:
            response = requests.post(url, json=body, headers=headers)
            responseBody = json.loads(response.text)
            data = data + responseBody
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
            raise Exception(e)
        
    gzOutfile = gzip.GzipFile(filename="/tmp/" + outfileName, mode="w", compresslevel=9)
    gzOutfile.write(json.dumps(data, indent=2).encode("UTF-8"))
    gzOutfile.close()

    s3 = boto3.client('s3')
    s3.upload_file("/tmp/" + outfileName, bucketName, outfileName)