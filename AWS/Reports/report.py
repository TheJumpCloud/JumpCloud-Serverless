import requests, datetime, json, boto3, os, gzip
from botocore.exceptions import ClientError
import jcapiv2
import jcapiv1
from jcapiv2.configuration import Configuration
from jcapiv1.configuration import Configuration
from jcapiv2.rest import ApiException
from jcapiv1.rest import ApiException as ApiExpectionV1
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import ssl

def get_secret(secret_name):
    client = boto3.client(service_name='secretsmanager')
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise Exception(e)
    secret = get_secret_value_response['SecretString']
    return secret

def jc_generatereport(event, context):
    try:
        jcapikeyarn = os.environ['JcApiKeyArn']
        bucketName = os.environ['BucketName']
        botUserAccessToken = os.environ['BotUserAccessToken']
        slackChannelId = os.environ['slackChannelId']
    except KeyError as e:
        raise Exception(e)

    jcapikey = get_secret(jcapikeyarn)
    botAccessToken = get_secret(botUserAccessToken)
    now = datetime.datetime.utcnow().isoformat("T") + "Z"

    outfileName = "jc_generatereport_" + now + ".json.gz"

    API_KEY = jcapikey
    CONTENT_TYPE = "application/json"
    ACCEPT = "application/json"

    # Set up the configuration object with your API key for authorization
    CONFIGURATION_V1 = jcapiv1.Configuration()
    CONFIGURATION_V2 = jcapiv2.Configuration()
    CONFIGURATION_V1.api_key['x-api-key'] = API_KEY
    CONFIGURATION_V2.api_key['x-api-key'] = API_KEY

    API_SYSTEM_INSTANCE = jcapiv1.SystemsApi(jcapiv1.ApiClient(CONFIGURATION_V1))
    API_SYSTEMUSERS_INSTANCE = jcapiv1.SystemusersApi(jcapiv1.ApiClient(CONFIGURATION_V1))
    API_USERS_INSTANCE = jcapiv2.UsersApi(jcapiv2.ApiClient(CONFIGURATION_V2))
    API_USERGROUP_INSTANCE = jcapiv2.UserGroupsApi(jcapiv2.ApiClient(CONFIGURATION_V2))
    API_GRAPH_INSTANCE = jcapiv2.GraphApi(jcapiv2.ApiClient(CONFIGURATION_V2))

    def slack_fileUpload(fileName):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        token = botAccessToken
        client = WebClient(token=token, ssl=ssl_context)

        try:
            response = client.files_upload(
                channels=slackChannelId,
                initial_comment="JumpCloud Reporting Tool",
                file=fileName,
                title=fileName
            )
        except SlackApiError as e:
            raise Exception("Error uploading file: {}".format(e))

    def extract(lst):
        """Extract id and username from list 'lst'"""
        return [{"id": item.id, "username": item.username} for item in lst]

    def get_jc_users():
        """Get all JC Users"""
        interval = 100
        limit = interval
        skip = 0
        get_users = True
        users = []
        try:
            while get_users:
                users_list = API_SYSTEMUSERS_INSTANCE.systemusers_list(CONTENT_TYPE, ACCEPT, limit=limit, skip=skip)
                users += users_list.results
                skip += interval
                if (len(users_list.results) != interval):
                    get_users = False
            return users
        except ApiException as e:
            raise Exception("Exception when calling SystemusersApi->systemusers_list: %s\n" % e)

    def get_jc_user_traverse_directory(user_id):
        try:
            response = API_GRAPH_INSTANCE.graph_user_traverse_directory(user_id, CONTENT_TYPE, ACCEPT)
            return response
        except ApiException as err:
            raise Exception("Exception when calling GraphApi->graph_user_traverse_directory: %s\n" % e)

    def get_jc_user_member_of(user_id):
        try:
            response = API_GRAPH_INSTANCE.graph_user_member_of(user_id, CONTENT_TYPE, ACCEPT)
            return response
        except ApiException as e:
            raise Exception("Exception when calling GraphApi->graph_user_member_of: %s\n" % e)

    def get_jc_user_group(group_id):
        try:
            response = API_USERGROUP_INSTANCE.groups_user_get(group_id, CONTENT_TYPE, ACCEPT)
            return response
        except ApiException as e:
            raise Exception("Exception when calling UserGroupsApi->groups_user_get: %s\n" % e)

    def get_jc_user_system_associations(user_id):
        try:
            response = API_USERS_INSTANCE.graph_user_traverse_system(user_id, CONTENT_TYPE, ACCEPT, limit=100)
            return response
        except ApiException as e:
            raise Exception("Exception when calling UsersApi->graph_user_traverse_system: %s\n" % e)

    def get_jc_system(system_id):
        try:
            response = API_SYSTEM_INSTANCE.systems_get(system_id, CONTENT_TYPE, ACCEPT)
            return response
        except ApiException as e:
            raise Exception("Exception when calling SystemsApi->systems_get: %s\n" % e)

    # Get List of all users
    users = get_jc_users()

    # Extract only the user's ID and username
    users = extract(users)

    # Set empty dict variable to hold final data
    finalUserInfo = {}

    # initiate an index for the above dict
    index = 0

    # total users
    totalUsers = len(users)

    # Loop through all users
    for user in users:
        # Set empty list variables to hold data
        userGroupMembership = []

        # Set the initial index to an empty dict
        finalUserInfo[index] = {}

        # Get the User's directory associations
        userDirectoryAssociation = get_jc_user_traverse_directory(user['id'])

        # Get the User's group memberships
        userGroupMembership = get_jc_user_member_of(user['id'])

        # Get the User's system associations
        userSystemAssociations = get_jc_user_system_associations(user['id'])

        # Start creating the user's dict
        finalUserInfo[index]['userId'] = user['id']
        finalUserInfo[index]['username'] = user['username']
        finalUserInfo[index]['groupMemberships'] = ""
        finalUserInfo[index]['systemIds'] = ""
        finalUserInfo[index]['systemHostnames'] = ""
        finalUserInfo[index]['systemDisplayNames'] = ""
        finalUserInfo[index]['directoryAssociation'] = ""
            
        # Loop through any system associations and return the system's ids, hostnames and displaynames
        for system in userSystemAssociations:
            systemInfo = get_jc_system(system.id)
            finalUserInfo[index]['systemIds'] += system.id + ";"
            finalUserInfo[index]['systemHostnames'] += systemInfo.hostname + ";"
            finalUserInfo[index]['systemDisplayNames'] += systemInfo.display_name + ";"

        # Loop through any memberships that the user has and return the Group's name instead of ID
        for group in userGroupMembership:
            groupInfo = get_jc_user_group(group.id)
            finalUserInfo[index]['groupMemberships'] += groupInfo.name + ";"

        # Loop through any directory association that the user has and return the directory's id and type
        for directory in userDirectoryAssociation:
            finalUserInfo[index]['directoryAssociation'] += directory.id + "_" + directory.type

        # Increment the index
        index += 1
    
    try:
        gzOutfile = gzip.GzipFile(filename="/tmp/" + outfileName, mode="w", compresslevel=9)
        gzOutfile.write(json.dumps(finalUserInfo, indent=2).encode("UTF-8"))
        gzOutfile.close()
    except Exception as e:
        raise Exception(e)
    try:
        s3 = boto3.client('s3')
        s3.upload_file("/tmp/" + outfileName, bucketName, outfileName)
    except ClientError as e:
        raise Exception(e)
    try:
        slack_fileUpload("/tmp/" + outfileName)
    except Exception as e:
        raise Exception(e)