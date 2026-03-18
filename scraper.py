import json
import datetime
import os
import feedparser
import calendar
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from readability import Document
import time
import re

# --- Configuration ---
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# --- Data Sources (Product-Focused MedAI) ---
RSS_SOURCES = {
    # 🟢 Product Cases (Industry)
    "Google Health": "https://blog.google/technology/health/rss/",
    
    # 🟠 Clinical Needs
    "The Doctor Weighs In": "https://thedoctorweighsin.com/feed/",
    "KevinMD": "https://www.kevinmd.com/feed",
    
    # 🔴 Regulation / Market
    "FDA MedDevice": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/medical-devices/rss.xml",
    
    # 🌟 Global Thought Leaders (Insights)
    "Eric Topol": "https://erictopol.substack.com/feed",
    "Doctor Penguin": "https://doctorpenguin.substack.com/feed",
    
    # 💰 Biz / Capital (Market)
    "MobiHealthNews": "https://www.mobihealthnews.com/feed",
    # 36kr will be handled by direct search API now
}

# --- Search Keywords Matrix ---
SEARCH_KEYWORDS = [
    "医疗 AI", 
    "AI医疗", 
    "医疗大模型", 
    "数字疗法", 
    "医疗信息化", 
    "临床诊疗",
    "医学影像",
    "智慧医疗",
    "医疗科技",
    "AI制药"
]

SEARCH_KEYWORDS_EN = [
    "Medical AI",
    "Healthcare LLM",
    "Clinical AI",
    "AI in Healthcare",
    "Generative AI Healthcare",
    "Radiology AI",
    "Digital Health"
]

# --- Auto-Tagging Dictionary ---
AUTO_TAGS_DICT = {
    "大模型": ["LLM", "GPT", "大模型", "Generative AI", "生成式", "Foundation Model", "ChatGPT"],
    "医学影像": ["影像", "CV", "CT", "MRI", "Radiology", "X-ray", "Ultrasound", "超声"],
    "数字疗法": ["DTx", "数字疗法", "慢病管理", "Digital Therapeutics", "Chronic Care"],
    "电子病历": ["EMR", "EHR", "病历", "Scribe", "Documentation", "Clinical Note"],
    "商业融资": ["融资", "Funding", "Startup", "IPO", "资本", "Acquisition", "Series A", "Series B"],
    "可穿戴/IoT": ["Wearable", "手环", "传感器", "Sensor", "Apple Watch"],
    "药物研发": ["Drug Discovery", "AlphaFold", "靶点", "制药", "Pharma"],
}

def generate_tags(title, summary, base_category):
    """根据标题和摘要内容，自动匹配并生成结构化标签"""
    tags = set() # Don't start with category to avoid duplication
    combined_text = (title + " " + summary).lower()
    
    for tag_name, keywords in AUTO_TAGS_DICT.items():
        for kw in keywords:
            if kw.lower() in combined_text:
                tags.add(tag_name)
                break # Move to next tag category once matched
                
    return list(tags)

def calculate_med_score(title, summary, source_name=""):
    """
    四层过滤漏斗机制 (4-Tier Cascading Funnel)
    
    Layer 1: 信源白名单直通车 (Source-Level Fast Track)
    Layer 2: 前置强制交集检测 (Pre-condition Intersection)
    Layer 3: 加权积分与密度检测 (Weighted Scoring & Density)
    Layer 4: 时效性与防重墙 (在外部逻辑处理)
    """
    
    # --- Layer 1: 信源白名单直通车 ---
    # 这些源具有 100% 的垂直纯度，无需关键词检测
    WHITELIST_SOURCES = ["Eric Topol", "Doctor Penguin", "FDA", "KevinMD", "The Doctor Weighs In", "Google Health"]
    for wl_source in WHITELIST_SOURCES:
        if wl_source in source_name:
            return 10 # 满分直通
            
    combined_text = (title + " " + summary).lower()
    
    # 1. 强医疗实体词 (Medical Entities)
    STRONG_MED = [
        "临床", "病历", "诊断", "药物", "手术", "医院", "患者", "医生", "影像", "基因", 
        "EMR", "HIS", "FDA", "器械", "医保", "处方", "慢病", "护理", "问诊", "科室",
        "靶点", "筛查", "疗法", "医疗", "医学", "药企", "新药",
        "medical", "clinical", "healthcare", "patient", "doctor", "hospital", "radiology",
        "surgery", "drug", "pharma", "therapy", "disease", "health", "care"
    ]
    
    # 2. 技术/动作词 (Tech Actions)
    TECH_ACTION = [
        "大模型", "算法", "系统", "产品", "模型", "SaaS", "商业化", "融资", "研发",
        "GPT", "LLM", "Agent", "平台", "软件", "应用", "架构", "ai", "数据", "智能",
        "model", "algorithm", "system", "product", "software", "data", "platform",
        "generative", "architecture", "startup", "funding"
    ]
    
    # 3. 负面降噪词 (Negative)
    NEGATIVE = [
        "减肥", "健身", "美容", "护肤", "睡眠", "手环", "手表", "家电", "冰箱", 
        "空调", "生活方式", "穿搭", "美妆", "养生", "食谱", "宠物", "猫狗", "电商",
        "外卖", "娱乐", "游戏", "网红", "主播", "带货", "旅游"
    ]
    
    # --- Layer 2: 前置强制交集检测 (护照+机票) ---
    # 必须同时包含至少一个强医疗词和至少一个技术词
    has_med = any(kw.lower() in combined_text for kw in STRONG_MED)
    has_tech = any(kw.lower() in combined_text for kw in TECH_ACTION)
    
    # 特例：如果在标题中直接出现了“医疗AI”或“AI医疗”这种超级组合词，可豁免交集
    super_keywords = ["医疗 ai", "ai医疗", "医疗大模型", "数字疗法", "智慧医疗", "医疗信息化", "ai 医疗", "医疗ai", "medical ai", "healthcare ai", "clinical ai", "health ai"]
    has_super = any(sk in combined_text for sk in super_keywords)
    
    if not has_super and not (has_med and has_tech):
        return 0 # 交集失败，直接淘汰
        
    # --- Layer 3: 加权积分与密度检测 ---
    score = 0
    
    # 增加基础分，只要满足了交集，就代表是相关领域的
    score += 2
    
    for kw in STRONG_MED:
        count = combined_text.count(kw.lower())
        score += count * 3
        
    for kw in TECH_ACTION:
        count = combined_text.count(kw.lower())
        score += count * 1
        
    for kw in NEGATIVE:
        count = combined_text.count(kw.lower())
        score -= count * 5
        
    # Bonus: Title Match (Extra Weight for visibility)
    for kw in STRONG_MED:
        if kw.lower() in title.lower():
            score += 5
            break
            
    # 密度检测 (Length Penalty)
    # 如果文本非常长（例如长摘要），但得分很低，说明浓度不够
    text_length = len(combined_text)
    if text_length > 200:
        # 每多 100 字，要求多得 1 分
        required_extra_score = (text_length - 200) / 100
        if score < (5 + required_extra_score):
            return 0 # 密度太低被淘汰

    return score

def is_article_fresh(time_str, source_name):
    """
    分层时间窗口策略 (Hybrid Time Window)
    - 资讯/商业 (Market): 近 90 天
    - 论文/前沿 (Insights/Clinical): 近 180 天
    - 深度/产品 (Product): 近 365 天
    """
    try:
        # Extract just the date part YYYY-MM-DD
        date_part = time_str.split(" ")[0]
        dt = datetime.datetime.strptime(date_part, "%Y-%m-%d")
        now = datetime.datetime.now()
        days_diff = (now - dt).days
        
        if "36氪" in source_name or "MobiHealthNews" in source_name or "动脉网" in source_name or "FDA" in source_name or "虎嗅" in source_name:
            return days_diff <= 90
        elif "Eric Topol" in source_name or "Doctor Penguin" in source_name or "KevinMD" in source_name or "Weighs In" in source_name:
            return days_diff <= 180
        elif "Medium" in source_name:
            return days_diff <= 365
        else: # Woshipm, Google, etc.
            return days_diff <= 365
    except Exception as e:
        # If parsing fails, keep it to be safe
        return True

def extract_full_text(url):
    """提取任意网页的正文内容 (Readability)"""
    try:
        # 针对 36kr 的特殊处理（绕过 PC 端反爬，使用移动端 API 状态提取）
        if "36kr.com/p/" in url:
            mobile_url = url.replace("https://36kr.com/", "https://m.36kr.com/")
            headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            }
            time.sleep(1)
            response = requests.get(mobile_url, headers=headers, timeout=15)
            if response.status_code == 200:
                match = re.search(r'window\.initialState=(.*?)</script>', response.text, re.DOTALL)
                if match:
                    try:
                        state_str = match.group(1).strip()
                        data = json.loads(state_str)
                        inner_data = data.get('article', {}).get('detail', {}).get('data', {})
                        content = inner_data.get('widgetContent') or inner_data.get('content') or ""
                        if content:
                            # 清理一下潜在的破坏性标签
                            soup = BeautifulSoup(content, 'html.parser')
                            for tag in soup(["script", "style"]):
                                tag.decompose()
                            return str(soup)
                    except Exception as e:
                        print(f"    [36kr Extractor Parse Error] {url}: {e}")
            # 如果特殊提取失败，降级使用常规模式继续执行
        
        # Some sites like Woshipm need special headers to not return 403
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # Add a small delay to avoid rate limiting
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=15)
        
        # If Woshipm returns 404, it might be in another category
        if "woshipm.com" in url:
            # Woshipm has strong anti-bot, let's try a different approach for them if 403
            if response.status_code == 403:
                # print(f"    [403] Trying alternative woshipm url for {url}")
                url = url.replace("www.woshipm.com", "api.woshipm.com/api/article/detail")
                # We can't easily parse their API without auth, so we just return empty string and fallback to summary
                return ""
            
            if response.status_code == 404:
                for cat in ["ai", "it", "med", "active", "share", "eval", "article"]:
                    new_url = re.sub(r"woshipm\.com/[^/]+/", f"woshipm.com/{cat}/", url)
                    response = requests.get(new_url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        url = new_url # update url for returning
                        break

        if response.status_code == 200:
            doc = Document(response.text)
            html_content = doc.summary()
            
            # 基础清理：移除可能破坏 UI 的样式和脚本
            soup = BeautifulSoup(html_content, 'html.parser')
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            
            # Fix relative image URLs if any
            for img in soup.find_all('img'):
                if img.get('src') and img['src'].startswith('//'):
                    img['src'] = 'https:' + img['src']
            
            return str(soup)
        else:
            print(f"    [Full Text Extractor Failed] {url} returned {response.status_code}")
    except Exception as e:
        print(f"    [Full Text Extractor Error] {url}: {e}")
    return ""

def fetch_rss_feeds(existing_urls):
    """抓取医疗垂直 RSS 源"""
    print("正在抓取 MedAI Product RSS 源...")
    items = []
    
    for source_name, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            print(f"  -> {source_name}: {len(feed.entries)} entries")
            
            for entry in feed.entries:
                try:
                    title = entry.title
                    link = entry.link
                    
                    if link in existing_urls:
                        continue
                        
                    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    # Remove HTML tags from summary for better display/scoring
                    summary = re.sub(r'<[^>]+>', '', summary)
                    
                    # --- Filtering ---
                    # Calculate score using the new 4-tier funnel
                    med_score = calculate_med_score(title, summary, source_name)
                    
                    if med_score < 5: 
                        continue
                    
                    # Time parsing (Standard RSS usually has parsed_published)
                    time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        time_str = datetime.datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M")
                    
                    # Apply Hybrid Time Window Filtering
                    if not is_article_fresh(time_str, source_name):
                        continue
                    
                    # Category Mapping
                    category = "Market"
                    if "动脉网" in source_name or "MobiHealthNews" in source_name or "36氪" in source_name:
                        category = "Market"
                    elif "Google" in source_name or "Microsoft" in source_name or "机器之心" in source_name:
                        category = "Product"
                    elif "Doctor Weighs In" in source_name or "KevinMD" in source_name or "NEJM" in source_name:
                        category = "Clinical"
                    elif "Eric Topol" in source_name or "Doctor Penguin" in source_name:
                        category = "Insights"
                    elif "FDA" in source_name:
                        category = "Market"
                        
                    # Auto-Tagging
                    smart_tags = generate_tags(title, summary, category)
                        
                    # Check if full content is already in RSS
                    full_html = ""
                    if hasattr(entry, "content") and len(entry.content) > 0:
                        full_html = entry.content[0].value
                    else:
                        # Full text extraction for items that only have summaries
                        # print(f"    Fetching full text for: {title}")
                        full_html = extract_full_text(link)

                    items.append({
                        "title": title,
                        "source": source_name,
                        "category": category,
                        "tags": smart_tags,
                        "time": time_str,
                        "url": link,
                        "summary": summary[:200] + "...",
                        "full_content": full_html,
                        "lang": "en" if "FDA" in source_name or "Google" in source_name or "Mobi" in source_name or "Topol" in source_name else "zh"
                    })
                    
                except Exception as e:
                    # print(f"Error parsing RSS entry: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ RSS {source_name} Failed: {e}")
            
    return items

def scrape_woshipm_direct(existing_urls):
    """
    直接模拟官网搜索接口 POST 请求抓取
    Target: https://api.woshipm.com/search/result.html
    """
    print(f"正在抓取 人人都是产品经理 (Direct POST)...")
    items = []
    seen_urls = set(existing_urls) # Initialize with existing to avoid re-fetching
    
    url = "https://api.woshipm.com/search/result.html"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.woshipm.com/",
        "Origin": "https://www.woshipm.com",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    
    for keyword in SEARCH_KEYWORDS:
        print(f"  -> 关键词: {keyword}")
        # Fetch 3 pages per keyword instead of 10 for a single keyword
        for page in range(1, 4):
            try:
                payload = {
                    "key": keyword,
                    "tab": "0", # 0=文章
                    "page": str(page),
                    "sortType": "0", # 0=相关度 (Relevance)
                    "idSearch": "" 
                }
                
                response = requests.post(url, data=payload, headers=headers, timeout=10)
                
                if response.status_code != 200:
                    continue
                    
                soup = BeautifulSoup(response.text, "html.parser")
                article_nodes = soup.find_all("div", class_="course--item")
                
                for node in article_nodes:
                    try:
                        # 1. Title
                        title_tag = node.find("a", class_="title")
                        if not title_tag: continue
                        title = title_tag.get_text(strip=True)
                        
                        # 2. URL (Extract ID)
                        article_id = node.get("id")
                        if not article_id: continue
                        article_url = f"http://www.woshipm.com/pd/{article_id}.html"
                        
                        # Deduplication
                        if article_url in seen_urls:
                            continue
                        seen_urls.add(article_url)
                        
                        # 3. Summary
                        desc_tag = node.find("div", class_="desc")
                        summary = desc_tag.get_text(strip=True) if desc_tag else ""
                        
                        # --- NEW: Relevance Scoring ---
                        med_score = calculate_med_score(title, summary, "人人都是产品经理")
                        if med_score < 5: 
                            continue
                            
                        # 4. Meta (Date, Author)
                        meta_tag = node.find("div", class_="meta")
                        time_str = "" 
                        author = "人人都是产品经理"
                        
                        if meta_tag:
                            meta_text = meta_tag.get_text(strip=True)
                            date_match = re.search(r"(\d{4}[-\./]\d{2}[-\./]\d{2})", meta_text)
                            if date_match:
                                date_part = date_match.group(1).replace("/", "-").replace(".", "-")
                                time_str = f"{date_part} 09:00"
                            
                            if not time_str:
                                 if "小时前" in meta_text:
                                     try:
                                         hours = int(re.search(r"(\d+)\s*小时前", meta_text).group(1))
                                         time_str = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
                                     except: pass
                                 elif "天前" in meta_text:
                                     try:
                                         days = int(re.search(r"(\d+)\s*天前", meta_text).group(1))
                                         time_str = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
                                     except: pass
                                 elif "分钟前" in meta_text:
                                     time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                                     
                        # Fallback to image path for date
                        if not time_str:
                            img_tag = node.find("img")
                            if img_tag:
                                src = img_tag.get("src", "")
                                url_date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", src)
                                if url_date_match:
                                    y, m, d = url_date_match.groups()
                                    time_str = f"{y}-{m}-{d} 09:00"

                        if not time_str:
                             time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

                        # --- Apply Hybrid Time Window Filtering ---
                        if not is_article_fresh(time_str, "人人都是产品经理"):
                            continue

                        smart_tags = generate_tags(title, summary, "Product")
                        full_html = extract_full_text(article_url)

                        items.append({
                            "title": title,
                            "source": f"人人都是产品经理",
                            "category": "Product",
                            "tags": smart_tags,
                            "time": time_str,
                            "url": article_url,
                            "summary": summary,
                            "full_content": full_html,
                            "lang": "zh"
                        })
                        
                    except Exception as e:
                        continue
                        
            except Exception as e:
                print(f"❌ Direct POST 失败: {e}")
                
    return items

def scrape_36kr_direct(existing_urls):
    """直接调用 36kr 搜索 API 获取精准内容"""
    print("正在抓取 36氪 (Direct Search API)...")
    items = []
    seen_urls = set(existing_urls) # Initialize with existing
    
    url = "https://gateway.36kr.com/api/mis/nav/search/resultbytype"
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json"
    }
    
    for keyword in SEARCH_KEYWORDS:
        print(f"  -> 关键词: {keyword}")
        try:
            payload = {
                "partner_id": "web",
                "timestamp": int(time.time() * 1000),
                "param": {
                    "searchType": "article",
                    "searchWord": keyword,
                    "sort": "date",
                    "pageSize": 20,
                    "pageEvent": 0,
                    "siteId": 1,
                    "platformId": 2
                }
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    article_list = data.get('data', {}).get('itemList', [])
                    
                    for item in article_list:
                        try:
                            # 36kr API has changed: item itself now contains the fields
                            material = item.get('templateMaterial') or item
                            title = material.get('widgetTitle', '')
                            # Strip HTML from title just in case
                            title = re.sub(r'<[^>]+>', '', title)
                            
                            article_id = material.get('itemId')
                            if not article_id: continue
                            
                            article_url = f"https://36kr.com/p/{article_id}"
                            
                            if article_url in seen_urls:
                                continue
                            seen_urls.add(article_url)
                            
                            summary = material.get('widgetContent') or material.get('content', '')
                            summary = re.sub(r'<[^>]+>', '', summary)
                            
                            # Scoring
                            med_score = calculate_med_score(title, summary, "36氪")
                            if med_score < 5: 
                                # print(f"    [Filtered] {title} (Score: {med_score})")
                                continue
                                
                            # Time
                            publish_time = material.get('publishTime', 0)
                            if publish_time > 0:
                                # publishTime is usually in milliseconds
                                dt = datetime.datetime.fromtimestamp(publish_time / 1000.0)
                                time_str = dt.strftime("%Y-%m-%d %H:%M")
                            else:
                                time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                                
                            # Apply Hybrid Time Window Filtering (90 days for 36kr)
                            if not is_article_fresh(time_str, "36氪"):
                                continue
                                
                            smart_tags = generate_tags(title, summary, "Market")
                            full_html = extract_full_text(article_url)
                            
                            items.append({
                                "title": title,
                                "source": "36氪",
                                "category": "Market",
                                "tags": smart_tags,
                                "time": time_str,
                                "url": article_url,
                                "summary": summary,
                                "full_content": full_html,
                                "lang": "zh"
                            })
                        except Exception as e:
                            continue
        except Exception as e:
            print(f"❌ 36kr API 失败: {e}")
            
    return items

def scrape_woshipm(existing_urls):
    """
    抓取策略路由: 优先 Direct POST，失败降级到 RSSHub
    """
    # Strategy 1: Direct POST
    data = scrape_woshipm_direct(existing_urls)
    if data:
        return data
        
    # Strategy 2: RSSHub Proxy (Fallback)
    print("⚠️ Direct POST 没抓到数据，降级尝试 RSSHub Proxy...")
    
    items = []
    
    # ... (Original RSSHub Logic) ...
    rss_url = "https://rsshub.app/woshipm/search/AI"
    
    try:
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            print("  -> RSSHub 搜索无结果，尝试抓取'热门推荐'并本地过滤...")
            rss_url = "https://rsshub.app/woshipm/popular/daily"
            feed = feedparser.parse(rss_url)
            
        print(f"  -> 解析到 {len(feed.entries)} 篇文章")
        
        count = 0
        for entry in feed.entries:
            # 关键词过滤 (如果是从热门列表抓取的)
            if "search" not in rss_url:
                content_check = (entry.title + " " + (entry.summary if hasattr(entry, 'summary') else "")).lower()
                if "医疗" not in content_check and "ai" not in content_check:
                    continue
            
            if count >= 5: break
            
            published_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    dt = datetime.datetime.fromtimestamp(calendar.timegm(entry.published_parsed))
                    published_time = dt.strftime("%Y-%m-%d %H:%M")
            
            summary_raw = entry.summary if hasattr(entry, 'summary') else ""
            summary = re.sub(r'<[^>]+>', '', summary_raw)
            
            smart_tags = generate_tags(entry.title, summary, "Product")
            
            full_html = ""
            if hasattr(entry, "content") and len(entry.content) > 0:
                full_html = entry.content[0].value
            else:
                full_html = extract_full_text(entry.link)
            
            items.append({
                "title": entry.title,
                "source": "人人都是产品经理",
                "category": "Product",
                "tags": smart_tags,
                "time": published_time,
                "url": entry.link,
                "summary": summary[:200] + "...",
                "full_content": full_html,
                "lang": "zh"
            })
            count += 1
            
    except Exception as e:
        print(f"❌ RSSHub 代理抓取失败: {e}")
            
    return items


def scrape_medium_tags(existing_urls):
    """通过 Medium Tag RSS 获取文章"""
    print("正在抓取 Medium (Tag RSS)...")
    items = []
    seen_urls = set(existing_urls)
    
    # We use RSS for tags to get pure chronologically sorted feeds. 
    # Medium search API is protected, so this is the best alternative.
    tags = [kw.replace(" ", "-").lower() for kw in SEARCH_KEYWORDS_EN]
    
    for tag in tags:
        print(f"  -> Tag: {tag}")
        url = f"https://medium.com/feed/tag/{tag}"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                link = entry.link
                # Normalize link to avoid tracking parameters
                base_link = link.split("?")[0]
                
                if base_link in seen_urls:
                    continue
                seen_urls.add(base_link)
                
                title = entry.title
                summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                summary_clean = re.sub(r'<[^>]+>', '', summary)
                
                med_score = calculate_med_score(title, summary_clean, "Medium")
                if med_score < 5:
                    continue
                    
                time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    time_str = datetime.datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M")
                    
                if not is_article_fresh(time_str, "Medium"):
                    continue
                    
                smart_tags = generate_tags(title, summary_clean, "Insights")
                
                # Medium full content is usually in content:encoded, but it might be truncated for paywall
                full_html = ""
                if hasattr(entry, "content") and len(entry.content) > 0:
                    full_html = entry.content[0].value
                
                # Medium paywall blocks standard readability extraction.
                # If RSS content is too short or missing, we fallback to just showing the summary in the drawer.
                if not full_html or len(full_html) < 200:
                    full_html = f"<div class='medium-fallback'><p><em>Note: This article is behind Medium's Paywall. Here is the summary:</em></p><br><p>{summary}</p></div>"
                    
                items.append({
                    "title": title,
                    "source": "Medium",
                    "category": "Insights", # Default to Insights
                    "tags": smart_tags,
                    "time": time_str,
                    "url": base_link,
                    "summary": summary_clean[:200] + "...",
                    "full_content": full_html,
                    "lang": "en"
                })
        except Exception as e:
            print(f"❌ Medium RSS 失败: {e}")
            
    return items

def load_existing_data(filepath="data/news.json"):
    """Load existing JSON to build a stateful memory of seen URLs"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                urls = {item.get('url') for item in data if item.get('url')}
                return data, urls
        except Exception as e:
            print(f"⚠️ 无法读取已存在的数据: {e}")
    return [], set()

def fetch_all_data():
    """主调度函数: 状态记忆增量抓取"""
    print("开始执行状态记忆增量抓取任务...")
    
    # 1. Load existing state
    existing_news, existing_urls = load_existing_data()
    print(f"📦 本地已存在 {len(existing_news)} 条数据，建立去重记忆池。")
    
    new_items = []
    
    # 2. RSS Feeds (Passing existing URLs)
    rss_data = fetch_rss_feeds(existing_urls)
    new_items.extend(rss_data)
    
    # 3. Woshipm - Direct Scrape with Multiple Keywords
    print("🚀 正在执行: 人人都是产品经理 (Multiple Keywords)...")
    woshipm_data = scrape_woshipm(existing_urls)
    new_items.extend(woshipm_data)
    
    # 4. 36kr - Direct Search API
    print("🚀 正在执行: 36氪 (Multiple Keywords)...")
    kr_data = scrape_36kr_direct(existing_urls)
    new_items.extend(kr_data)
    
    # 5. Huxiu - Direct Search API

    
    # 6. Medium - Tag RSS
    print("🚀 正在执行: Medium (Tag RSS)...")
    medium_data = scrape_medium_tags(existing_urls)
    new_items.extend(medium_data)
    
    print(f"✨ 本次增量抓取共获得 {len(new_items)} 条新数据。")
    
    # Combine and Apply Eviction Policy
    all_news = existing_news + new_items
    print("🧹 正在执行淘汰机制 (剔除过期数据) 并进行全局去重...")
    
    unique_news = []
    seen_urls = set()
    for item in all_news:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
            
        # Eviction Check
        time_str = item.get("time", "")
        source_name = item.get("source", "")
        if is_article_fresh(time_str, source_name):
            seen_urls.add(url)
            unique_news.append(item)
            
    # Sort by time descending
    unique_news.sort(key=lambda x: x.get("time", ""), reverse=True)
    
    print(f"✅ 最终保留 {len(unique_news)} 条有效数据 (剔除了 {len(all_news) - len(unique_news)} 条过期/重复数据)")
    return unique_news

def save_data(data):
    os.makedirs("data", exist_ok=True)
    file_path = "data/news.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"数据已保存至 {file_path}")

if __name__ == "__main__":
    data = fetch_all_data()
    save_data(data)
