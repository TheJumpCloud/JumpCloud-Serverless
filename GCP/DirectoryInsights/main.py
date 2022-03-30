import croniter
import datetime
import json
import os
import requests
from google.cloud import storage


def jc_directory_insights():
    try:
        jc_api_key = os.environ['jc_api_key']
        cron_schedule = os.environ['cron_schedule']
        service =  os.environ['service']
        jc_org_id = os.environ['jc_org_id']
        bucket_name = os.environ['bucket_name']

    except KeyError as e:
        raise Exception(e)

    date_now = datetime.datetime.utcnow()
    now = date_now.replace(second=0, microsecond=0)
    cron = croniter.croniter(cron_schedule, now)
    start_dt = cron.get_prev(datetime.datetime)

    start_date = start_dt.isoformat("T") + "Z"
    end_date = now.isoformat("T") + "Z"

    available_services = ['directory', 'radius', 'sso', 'systems', 'ldap', 'mdm', 'all']
    service_list = ((service.replace(" ", "")).lower()).split(",")
    for service in service_list:
        if service not in available_services:
            raise Exception(f"Unknown service: {service}")
    if 'all' in service_list and len(service_list) > 1:
        raise Exception(f"Error - Service List contains 'all' and additional services : {service_list}")
    final_data = []

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
def run_di(tester):
    requests_args = tester.args

    if requests_args and "message" in requests_args:
        message = requests_args["message"]
    else:
        jc_directory_insights()
        message = 'Created log'
    return message
