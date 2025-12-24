
import feedparser

url = "https://www.jiqizhixin.com/rss"
print(f"Testing URL with pure feedparser: {url}")

try:
    feed = feedparser.parse(url)
    print(f"Feed entries: {len(feed.entries)}")
    if len(feed.entries) > 0:
        print(f"First entry title: {feed.entries[0].title}")
    else:
        print("No entries found!")
        print(f"Bozo: {feed.bozo}")
        print(f"Bozo exception: {feed.bozo_exception}")
        if hasattr(feed, 'status'):
            print(f"Status: {feed.status}")

except Exception as e:
    print(f"Error: {e}")
