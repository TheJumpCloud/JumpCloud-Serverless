import os
import glob
import os.path
import gzip
import json
import subprocess
import urllib.request
import re
from re import search
from pathlib import Path


def run_subproc(cmd):
    sp = subprocess.run(['python3', cmd], stdout=subprocess.PIPE, text=True)
    return sp.stdout

def test_script_produces_output_with_all_services():
    pwd = os.path.dirname(os.path.realpath(__file__))

    print("running file...")
    print(pwd + "/temp_get-jcdirectoryinsights.py")
    # Set Variables:
    os.environ['JC_API_KEY'] = "$JC_API_KEY"
    os.environ['incrementType'] = "day"
    os.environ['incrementAmount'] = "1"
    os.environ['service'] = 'all'
    os.environ['OrgId'] = '5a4bff7ab17d0c9f63bcd277'
    # End Variables
    run_subproc(pwd + "/temp_get-jcdirectoryinsights.py")
    files = glob.glob(pwd + "/jc_directoryinsights*.json.gz")
    for file in files:
        print("found File: " + file)
        assert os.path.exists(file)


def test_json_contents_for_all_services():
    pwd = os.path.dirname(os.path.realpath(__file__))
    files = glob.glob(pwd + "/jc_directoryinsights*.json.gz")
    with gzip.open(files[0], 'r') as f:
        data = f.read()
        j = json.loads (data.decode('utf-8'))
    # non empty json
    assert len(j) != 0
    for i in j:
        # print(i['service'])
        assert i['service'] == 'directory' or i['service'] == 'radius' or i['service'] == 'systems' or i['service'] == 'sso' or i['service'] == 'ldap' or i['service'] == 'mdm'

# def test_json_again():
#     os.environ['incrementType'] = "day"
#     os.environ['incrementAmount'] = "1"
#     # os.environ['BucketName'] = 
#     os.environ['service'] = 'directory'
#     os.environ['OrgId'] = '5a4bff7ab17d0c9f63bcd277'
#     pwd = os.getcwd()
#     print("running file...")
#     print(pwd + "/get-jcdirectoryinsights.py")
#     run_subproc(pwd + "/get-jcdirectoryinsights.py")
#     files = glob.glob("jc_directoryinsights_2022-04-25*.json.gz")
#     for file in files:
#         assert os.path.exists(pwd + "/" + file)
#         print(file)
#         os.remove(file)

def test_changelog_version():
    pwd = os.path.dirname(os.path.realpath(__file__))
    path = Path(pwd)
    print(str(path.parent.parent.parent.absolute()) + '/AWS/DirectoryInsights/CHANGELOG.md')
    # get latest version from GitHub
    URL = "https://raw.githubusercontent.com/TheJumpCloud/JumpCloud-Serverless/master/AWS/DirectoryInsights/CHANGELOG.md"
    file = urllib.request.urlopen(URL)
    # get first version on changelog - this is the latest version
    for line in file:
        decoded_line = line.decode("utf-8")
        if decoded_line.startswith('##'):
            latestVersionText = decoded_line
            latestVersion = (latestVersionText[latestVersionText.find("[")+1:latestVersionText.find("]")])
            break
    # get the version from this branch
    with open(str(path.parent.parent.parent.absolute()) + '/AWS/DirectoryInsights/CHANGELOG.md') as f: 
        lines = f.readlines()
    for line in lines:
        # print(line)
        if line.startswith('##'):
            latestVersionBranchText = line
            latestVersionBranch = (latestVersionBranchText[latestVersionBranchText.find("[")+1:latestVersionBranchText.find("]")])
            break
    # get the user agent version from this branch:
    with open(str(path.parent.parent.parent.absolute()) + '/AWS/DirectoryInsights/get-jcdirectoryinsights.py') as u:
        scriptLines = u.readlines()
    for scriptLine in scriptLines:
        # print(scriptLine)
        if search('user-agent', scriptLine):
            useragent = scriptLine
            latestUserAgentFromBranch = re.search(r'DirectoryInsights/([\d.]+)', useragent).group(1)
            break
    print('latest version from GitHub: ' + latestVersion)
    print('latest version from this Branch: ' + latestVersionBranch)
    print('useragent version from this Branch: ' + latestUserAgentFromBranch)
    # Latest version should not be the same as the latest version from Branch
    assert latestVersion != latestVersionBranch
    # Latest version from branch should be updated in all places
    assert latestUserAgentFromBranch == latestVersionBranch