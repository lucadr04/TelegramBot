import os
from dotenv import load_dotenv
import requests

url = "https://api.ebay.com/developer/analytics/v1_beta/rate_limit"

load_dotenv()
ACCESS_TOKEN = os.getenv("USER_TOKEN")

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# Make the GET request
response = requests.get(url, headers=headers)

# Check the response status
if response.status_code == 200:
    data = response.json()
    for api in data.get('rateLimits', []):
        print(f"API Context: {api['apiContext']}")
        print(f"API Name: {api['apiName']}")
        print(f"API Version: {api['apiVersion']}")
        for resource in api.get('resources', []):
            print(f"  Resource: {resource['name']}")
            for rate in resource.get('rates', []):
                if(rate['count']!=0):
                    print(f"    - Calls Made: {rate['count']}")
                    print(f"      Limit: {rate['limit']}")
                    print(f"      Remaining: {rate['remaining']}")
                    print(f"      Reset: {rate['reset']}")
                    print(f"      Time Window: {rate['timeWindow']} seconds")
else:
    print(f"Failed to retrieve rate limits. Status code: {response.status_code}")
    print("Response:", response.text)