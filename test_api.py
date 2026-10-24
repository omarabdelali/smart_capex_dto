import requests
import json

# Test API endpoint
r = requests.get('http://localhost:8000/api/sites/clusters/?cluster_id=0')
data = r.json()

print(f"Status Code: {r.status_code}")
print(f"Response Type: {data.get('type')}")
print(f"Features Count: {len(data.get('features', []))}")

if data.get('features'):
    first_feature = data['features'][0]
    print(f"\nFirst Feature:")
    print(json.dumps(first_feature, indent=2)[:800])
else:
    print("\nNo features found!")