import os
import requests

# Define icons dictionary with direct download URLs from flaticon
ICONS = {
    "admin": "https://cdn-icons-png.flaticon.com/512/3177/3177385.png",        # admin icon
    "user": "https://cdn-icons-png.flaticon.com/512/1077/1077114.png",       # user icon
    "assistant": "https://cdn-icons-png.flaticon.com/512/4712/4712109.png",  # AI bot icon
    "fixed_response": "https://cdn-icons-png.flaticon.com/512/942/942748.png" # data icon
}


# Create folder if not exists
output_folder = "assets/icons"
os.makedirs(output_folder, exist_ok=True)

# Download icons
for name, url in ICONS.items():
    if not url:
        continue
    response = requests.get(url)
    if response.status_code == 200:
        filepath = os.path.join(output_folder, f"{name}.png")
        with open(filepath, "wb") as f:
            f.write(response.content)
        print(f"✅ Downloaded: {name}")
    else:
        print(f"❌ Failed to download: {name}")

print("All downloads complete.")
