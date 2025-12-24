
import requests
import feedparser

url = "https://www.jiqizhixin.com/rss"
print(f"Testing URL: {url}")

try:
    # Try raw request first
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Content length: {len(response.text)}")
    
    # Try feedparser
    feed = feedparser.parse(response.text)
    print(f"Feed entries: {len(feed.entries)}")
    if len(feed.entries) > 0:
        print(f"First entry title: {feed.entries[0].title}")
    else:
        print("No entries found!")
        print(f"Bozo exception: {feed.bozo_exception}")

except Exception as e:
    print(f"Error: {e}")
