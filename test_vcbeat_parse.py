import requests
import re

res = requests.get("https://vcbeat.top/", timeout=5)
match = re.search(r'window\.__NUXT__=(.*?);</script>', res.text)
nuxt_js = match.group(1)

# we can split the nuxt_js by "{", and if a block has both title and url, we extract them.
blocks = nuxt_js.split("{")
found = []
for b in blocks:
    t_m = re.search(r'title:"([^"]+)"', b)
    u_m = re.search(r'url:"(https:\\u002F\\u002Fwww\.vbdata\.cn\\u002F\d+)"', b)
    s_m = re.search(r'summary:"([^"]+)"', b)
    if t_m and u_m:
        title = t_m.group(1)
        url = u_m.group(1).replace('\\u002F', '/')
        summary = s_m.group(1) if s_m else ""
        found.append((title, url, summary))

print(f"Found {len(found)} articles")
for i in found[:3]:
    print(i)
