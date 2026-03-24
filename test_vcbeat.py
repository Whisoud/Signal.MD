import requests
from bs4 import BeautifulSoup
import feedparser

print("Testing vcbeat.top RSSHub...")
try:
    f = feedparser.parse("https://rsshub.app/vcbeat/index")
    print(f"RSSHub vcbeat entries: {len(f.entries)}")
except Exception as e:
    print(e)

print("Testing direct vcbeat.top...")
res = requests.get("https://vcbeat.top/", timeout=5)
soup = BeautifulSoup(res.text, 'html.parser')
links = soup.find_all('a')
print(f"Links found: {len(links)}")
