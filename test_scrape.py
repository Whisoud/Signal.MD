import requests
import feedparser
from bs4 import BeautifulSoup
from readability import Document

# 1. Test VBData RSS
print("Testing VBData RSS...")
url = "https://rsshub.app/vbdata/report"
try:
    feed = feedparser.parse(url)
    print(f"VBData Report RSS entries: {len(feed.entries)}")
except Exception as e:
    print(f"VBData error: {e}")

url2 = "https://rsshub.app/vbdata/news"
try:
    feed2 = feedparser.parse(url2)
    print(f"VBData News RSS entries: {len(feed2.entries)}")
except Exception as e:
    print(f"VBData News error: {e}")

# 2. Test OpenAI Extract
print("\nTesting OpenAI Extraction...")
openai_url = "https://openai.com/news/spring-2024-update/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
}
try:
    res = requests.get(openai_url, headers=headers, timeout=10)
    print(f"OpenAI Status: {res.status_code}")
    doc = Document(res.text)
    html_content = doc.summary()
    soup = BeautifulSoup(html_content, 'html.parser')
    print(f"OpenAI Extracted Text Length: {len(soup.get_text())}")
    print(f"OpenAI snippet: {soup.get_text()[:200]}")
except Exception as e:
    print(f"OpenAI error: {e}")
