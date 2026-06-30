import sys
print("Interpreter:", sys.executable)

try:
    from config import REDDIT_CLIENT_ID, APIFY_TOKEN, TWITTER_BEARER_TOKEN, YOUTUBE_API_KEY, NEWS_API_KEY
    print("✓ Config loaded")
except Exception as e:
    print("❌ Failed to load config:", e)
    sys.exit(1)

keys = {
    "REDDIT": REDDIT_CLIENT_ID,
    "APIFY": APIFY_TOKEN,
    "TWITTER": TWITTER_BEARER_TOKEN,
    "YOUTUBE": YOUTUBE_API_KEY,
    "NEWS": NEWS_API_KEY
}

all_good = True
for name, val in keys.items():
    l = len(val) if val else 0
    if l > 0:
        print(f"✅ {name:10s} properly parsed (len={l})")
    else:
        print(f"❌ {name:10s} is empty!")
        all_good = False

if all_good:
    print("SUCCESS: All tokens parsed correctly!")
else:
    print("FAILURE: Some tokens are empty.")
