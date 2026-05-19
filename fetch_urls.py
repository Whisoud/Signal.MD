import urllib.request
from bs4 import BeautifulSoup

urls = [
    "https://mp.weixin.qq.com/s/r6CE2U3Y0-pU05wF3_PuTQ",
    "https://aihot.virxact.com"
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

for url in urls:
    print(f"--- Fetching {url} ---")
    try:
        req = urllib.request.Request(url, headers=headers)
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        
        # For WeChat, main content is usually in js_content
        if "mp.weixin.qq.com" in url:
            content_div = soup.find(id="js_content")
            if content_div:
                print(content_div.get_text(separator=' ', strip=True)[:1500])
            else:
                print("Could not find js_content")
                print(soup.get_text(separator=' ', strip=True)[:1500])
        else:
            print(f"Title: {soup.title.string if soup.title else 'No title'}")
            print(soup.get_text(separator=' ', strip=True)[:1500])
            
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    print("\n" + "="*50 + "\n")
