from croniter import croniter
import datetime
import json
import os
import requests
from google.cloud import storage


def jc_directory_insights():
    print("########### JC Directory Insights Function Started ###########")
    try:
        jc_api_key = os.environ['jc_api_key']
        jc_org_id = os.environ['jc_org_id']
        cron_schedule = os.environ['cron_schedule']
        service =  os.environ['service']
        bucket_name = os.environ['bucket_name']

    except KeyError as e:
        raise Exception(e)
    
    now = datetime.datetime.utcnow()
    print(f'Cron Expression: {cron_schedule}')
    time_tolerance = 10
    try:
        cron_time = croniter(cron_schedule, now - datetime.timedelta(seconds=time_tolerance))  # get the previous time with 59 seconds of tolerance
        now = cron_time.get_next(datetime.datetime)  # get the next run time from that previous time.
        start_dt = cron_time.get_prev(datetime.datetime)  # get the previous run time        
        print(f'Current Cron Time: {now}')
        print(f'Previous Cron Time: {start_dt}')
        # time_diff = abs((now - previous_cron_time).total_seconds())
    except Exception as e:
        print(f"Error in cron expression: {e}")
        # Exit the code and raise a

    now_seconds = now.second
    start_date = start_dt.isoformat("T") + "Z"
    end_date = now.isoformat("T") + "Z"
    
    # If the cronTime is not within the tolerance, error out
    if now_seconds >= time_tolerance:
        # Timestamps of the cron schedule
        print(f'Timestamps of the cron schedule: {start_date}, {end_date}')
        # Print an instruction to run the powershell script manually and save it to the S3 bucket
        print(f"Please run the powershell script manually and save it to the S3 bucket: {bucket_name}")
        print(f'service: {service},\n start-date: {start_date},\n end-date: {end_date},\n *** Powershell Script *** \n $sourcePath =  "<directory_path>/jc_directoryinsights_{start_date}_{end_date}.json" \n Get-JCEvent -service {service} -start_date {start_date} -EndTime {end_date} | ConvertTo-Json -Depth 99 | Out-File -FilePath $sourcePath \n $newFileName = "$($sourcePath).gz" \n $srcFileStream = New-Object System.IO.FileStream($sourcePath,([IO.FileMode]::Open),([IO.FileAccess]::Read),([IO.FileShare]::Read)) \n $dstFileStream = New-Object System.IO.FileStream($newFileName,([IO.FileMode]::Create),([IO.FileAccess]::Write),([IO.FileShare]::None)) \n $gzip = New-Object System.IO.Compression.GZipStream($dstFileStream,[System.IO.Compression.CompressionLevel]::SmallestSize) \n $srcFileStream.CopyTo($gzip) \n $gzip.Dispose() \n $srcFileStream.Dispose() \n $dstFileStream.Dispose()\n *** End Script ***' )

        raise Exception("Cron time is not within the tolerance.") # This will exit the code
    
    print(f'start_date: {start_date}, end_date: {end_date}')
    available_services = ['directory', 'radius', 'sso', 'systems', 'ldap', 'mdm', 'all']
    service_list = ((service.replace(" ", "")).lower()).split(",")
    for service in service_list:
        if service not in available_services:
            raise Exception(f"Unknown service: {service}")
    if 'all' in service_list and len(service_list) > 1:
        raise Exception(f"Error - Service List contains 'all' and additional services : {service_list}")
    final_data = []
    
    if len(service_list) > 1:
        for service in service_list:
            print (f'service: {service},\n start-date: {start_date},\n end-date: {end_date},\n *** Powershell Script *** \n $sourcePath =  "<directory_path>/jc_directoryinsights_{start_date}_{end_date}.json" \n Get-JCEvent -service {service} -StartTime {start_date} -EndTime {end_date} | ConvertTo-Json -Depth 99 | Out-File -FilePath $sourcePath \n $newFileName = "$($sourcePath).gz" \n $srcFileStream = New-Object System.IO.FileStream($sourcePath,([IO.FileMode]::Open),([IO.FileAccess]::Read),([IO.FileShare]::Read)) \n $dstFileStream = New-Object System.IO.FileStream($newFileName,([IO.FileMode]::Create),([IO.FileAccess]::Write),([IO.FileShare]::None)) \n $gzip = New-Object System.IO.Compression.GZipStream($dstFileStream,[System.IO.Compression.CompressionLevel]::SmallestSize) \n $srcFileStream.CopyTo($gzip) \n $gzip.Dispose() \n $srcFileStream.Dispose() \n $dstFileStream.Dispose()\n *** End Script ***' )
    else: 
        for service in service_list:
            print (f'service: {service},\n start-date: {start_date},\n end-date: {end_date},\n *** Powershell Script *** \n $sourcePath =  "<directory_path>/jc_directoryinsights_{start_date}_{end_date}.json" \n Get-JCEvent -service {service} -StartTime {start_date} -EndTime {end_date} | ConvertTo-Json -Depth 99 | Out-File -FilePath $sourcePath \n $newFileName = "$($sourcePath).gz" \n $srcFileStream = New-Object System.IO.FileStream($sourcePath,([IO.FileMode]::Open),([IO.FileAccess]::Read),([IO.FileShare]::Read)) \n $dstFileStream = New-Object System.IO.FileStream($newFileName,([IO.FileMode]::Create),([IO.FileAccess]::Write),([IO.FileShare]::None)) \n $gzip = New-Object System.IO.Compression.GZipStream($dstFileStream,[System.IO.Compression.CompressionLevel]::SmallestSize) \n $srcFileStream.CopyTo($gzip) \n $gzip.Dispose() \n $srcFileStream.Dispose() \n $dstFileStream.Dispose()\n *** End Script ***')
        
    for service in service_list:
        url = "https://api.jumpcloud.com/insights/directory/v1/events"
        body = {
            'service': [f"{service}"],
            'start_time': start_date,
            'end_time': end_date,
            "limit": 10000
        }
        headers = {
            'x-api-key': jc_api_key,
            'content-type': "application/json",
            'user-agent': 'JumpCloud_GCPServerless.DirectoryInsights/0.0.1'
        }
        if jc_org_id != '':
            headers['x-org-id'] = jc_org_id
        response = requests.post(url, json=body, headers=headers)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(e)

        response_body = json.loads(response.text)
        data = response_body
        while response.headers["X-Result-Count"] >= response.headers["X-Limit"]:
            body["search_after"] = json.loads(response.headers["X-Search_After"])
            response = requests.post(url, json=body, headers=headers)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                raise Exception(e)

            response_body = json.loads(response.text)
            data = data + response_body
        final_data += data

    if len(final_data) == 0:
        return
    else:
        outfile_name = "jc_directoryinsights_" + start_date + "_" + end_date + ".json"
        client = storage.Client()
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(outfile_name)
        blob.upload_from_string(
            data=json.dumps(final_data),
            content_type='application/json'
        )

# Http function for GC Functions
def run_di(httpRequest):
    requests_args = httpRequest.args

    if requests_args and "message" in requests_args:
        message = requests_args["message"]
    else:
        jc_directory_insights()
        message = 'DI successfully ran'
    return message
