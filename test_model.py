import requests

api_key = "AIzaSyDB_ua584DVkfyiRw4iCthSBqwPnmjcTxg"
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

print("Calling Google API...")
response = requests.get(url)

if response.status_code == 200:
    print("\n--- AVAILABLE MODELS ---")
models = response.json().get("models", [])
for m in models:
    if "generateContent" in m.get("supportedGenerationMethods", []):
        print(m["name"])
    else:
        print("Error!", response.status_code)
print(response.text)