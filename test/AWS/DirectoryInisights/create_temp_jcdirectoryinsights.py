import shutil
import os
from pathlib import Path


def create_temp():

    pwd = os.path.dirname(os.path.realpath(__file__))
    path = Path(pwd)
    print(str(path.parent.parent.parent.absolute()) + '/AWS/DirectoryInsights/get-jcdirectoryinsights.py')
    shutil.copyfile(str(path.parent.parent.parent.absolute()) + '/AWS/DirectoryInsights/get-jcdirectoryinsights.py', pwd + '/temp_get_jcdirectoryinsights.py')
    #Read in the file
    with open(pwd + "/temp_get_jcdirectoryinsights.py", 'r') as file :
        file_data = file.read()
        # Replace the target lines
        file_data = file_data.replace("os.environ['JcApiKeyArn']", "os.environ['JC_API_KEY']")
        file_data = file_data.replace("def jc_directoryinsights(event, context):", 'def jc_directoryinsights():')
        file_data = file_data.replace("get_secret(jcapikeyarn)", 'jcapikeyarn')
        file_data = file_data.replace("def get_secret(secret_name):", '#def get_secret(secret_name):', 1)
        file_data = file_data.replace("client = boto3.client(service_name='secretsmanager')", "#client = boto3.client(service_name='secretsmanager')", 1)
        file_data = file_data.replace("try:", '#try:', 1)
        file_data = file_data.replace("get_secret_value_response = client.get_secret_value(SecretId=secret_name)", '#get_secret_value_response = client.get_secret_value(SecretId=secret_name)')
        file_data = file_data.replace("except ClientError as e:", '#except ClientError as e:', 1)
        file_data = file_data.replace("raise Exception(e)", '#raise Exception(e)', 1)
        file_data = file_data.replace("secret = get_secret_value_response['SecretString']", "#secret = get_secret_value_response['SecretString']")
        file_data = file_data.replace("return secret", '#return secret')
        file_data = file_data.replace("gzOutfile = gzip.GzipFile(filename=\"/tmp/\" + outfileName, mode=\"w\", compresslevel=9)", 'gzOutfile = gzip.GzipFile(filename=os.path.dirname(os.path.realpath(__file__)) + \"/\"  + outfileName, mode=\"w\", compresslevel=9')

    # Write the file out again
    with open(pwd + "/temp_get_jcdirectoryinsights.py", 'w') as file:
        file.write(file_data)
        file.write('\n\njc_directoryinsights()')

if __name__ == "__main__":
    create_temp()
