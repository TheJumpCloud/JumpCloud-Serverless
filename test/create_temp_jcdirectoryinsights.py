import shutil
import os


def create_temp(jcapikey_ci_env):

    pwd = os.getcwd()
    shutil.copyfile(pwd + '/AWS/DirectoryInsights/get-jcdirectoryinsights.py', pwd + '/test/temp_get_jcdirectoryinsights.py')    
    #Read in the file
    with open(pwd + "/test/temp_get_jcdirectoryinsights.py", 'r') as file :
        file_data = file.read()
        
        # Replace the target lines
        file_data = file_data.replace("os.environ['JcApiKeyArn']", jcapikey_ci_env)
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
            
    # Write the file out again
    with open(pwd + "/test/temp_get_jcdirectoryinsights.py", 'w') as file:
        file.write(file_data)
        file.write('\n\njc_directoryinsights()')
