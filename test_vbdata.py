import requests
import json
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
res = requests.get("https://vbdata.cn/news", headers=headers, timeout=5)
with open('vbdata.html', 'w') as f:
    f.write(res.text)
print("Saved to vbdata.html")
