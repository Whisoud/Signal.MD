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
from deep_translator import GoogleTranslator
import time
import re
import random

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

# --- Search Keywords Matrix (Expanded CN) ---
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
    "AI制药",
    
    # 临床诊疗
    "辅助诊断",
    "临床决策支持系统",
    "CDSS",
    "智能分诊",
    "问诊机器人",
    "病历生成",
    "电子病历质控",
    "病历结构化",
    "临床路径",
    "多学科会诊 MDT",
    "随访管理",
    "复诊管理",
    "用药推荐",
    "处方审核",
    "合理用药",

    # 医院信息化
    "HIS系统",
    "EMR系统",
    "EHR系统",
    "PACS系统",
    "LIS系统",
    "RIS系统",
    "临床数据中心 CDR",
    "医疗数据治理",
    "医疗数据标准",
    "FHIR",
    "互联互通",
    "电子病历评级",
    "智慧医院评级",

    # 医院运营
    "DRG",
    "DIP",
    "医保控费",
    "医院绩效管理",
    "病案首页质控",
    "医疗质量控制",
    "院感管理",
    "护理管理",
    "床位管理",
    "手术排程",

    # 患者服务
    "互联网医院",
    "在线问诊",
    "患者随访",
    "患者教育",
    "健康管理",
    "慢病管理",
    "远程医疗",
    "居家监测",
    "家庭医生",

    # AI技术
    "医疗NLP",
    "医学知识图谱",
    "语音识别 医疗",
    "语音转写 Scribe",
    "医学OCR",
    "多模态医疗AI",
    "联邦学习 医疗",
    "隐私计算 医疗",
    "因果推断 医疗",

    # 医学影像细化
    "影像分割",
    "影像诊断",
    "病灶检测",
    "肺结节",
    "乳腺筛查",
    "脑卒中影像",
    "心脏影像",
    "数字病理",

    # 药物研发
    "AI药物研发",
    "分子生成",
    "靶点发现",
    "临床试验优化",
    "真实世界研究",
    "药物警戒",
    "精准医疗",
    "基因测序",

    # 意图增强（关键）
    "医疗AI案例",
    "医疗AI落地",
    "医疗AI实践",
    "医疗AI解决方案",
    "医疗AI应用场景",
    "医疗AI效果评估"
]

# --- Search Keywords Matrix (Expanded EN) ---
SEARCH_KEYWORDS_EN = [
    "Medical AI",
    "Healthcare LLM",
    "Clinical AI",
    "AI in Healthcare",
    "Generative AI Healthcare",
    "Radiology AI",
    "Digital Health",
    
    # Clinical
    "Clinical Decision Support System",
    "CDSS healthcare",
    "AI Diagnosis",
    "AI Triage",
    "Medical Scribe",
    "Clinical Documentation AI",
    "Ambient AI Healthcare",
    "Clinical Workflow AI",
    "Care Pathway Optimization",

    # Systems
    "Hospital Information System",
    "Electronic Medical Record",
    "Electronic Health Record",
    "FHIR Interoperability",
    "Healthcare Data Platform",
    "Clinical Data Repository",
    "Healthcare Data Governance",

    # Workflow AI
    "AI Copilot for Doctors",
    "Physician Workflow Automation",
    "Clinical Productivity AI",
    "Healthcare Automation",
    "AI assisted charting",

    # Imaging
    "Computer Vision Healthcare",
    "Radiology AI",
    "Pathology AI",
    "Digital Pathology",
    "AI Screening",
    "Lesion Detection",

    # Pharma
    "AI Drug Discovery",
    "Computational Biology",
    "Genomics AI",
    "Precision Medicine",
    "Real World Evidence",
    "Clinical Trial AI",

    # Business
    "HealthTech Startup",
    "Healthcare Funding",
    "Digital Health Investment",
    "MedTech IPO",
    "Healthcare M&A",

    # Intent (重要)
    "case study healthcare AI",
    "AI healthcare deployment",
    "AI healthcare implementation",
    "best practices healthcare AI",
    "ROI healthcare AI"
]

# --- Auto-Tagging Dictionary (Expanded) ---
AUTO_TAGS_DICT = {
    "大模型": ["LLM", "GPT", "大模型", "Generative AI", "生成式", "Foundation Model", "ChatGPT"],
    "医学影像": ["影像", "CV", "CT", "MRI", "Radiology", "X-ray", "Ultrasound", "超声"],
    "数字疗法": ["DTx", "数字疗法", "慢病管理", "Digital Therapeutics", "Chronic Care"],
    "电子病历": ["EMR", "EHR", "病历", "Scribe", "Documentation", "Clinical Note"],
    "商业融资": ["融资", "Funding", "Startup", "IPO", "资本", "Acquisition", "Series A", "Series B"],
    "可穿戴/IoT": ["Wearable", "手环", "传感器", "Sensor", "Apple Watch"],
    "药物研发": ["Drug Discovery", "AlphaFold", "靶点", "制药", "Pharma"],
    
    # 新增
    "医院运营": ["DRG", "DIP", "医保", "控费", "绩效", "运营分析"],
    "临床流程": ["分诊", "问诊", "诊断", "随访", "复诊"],
    "AI工作流": ["Copilot", "Workflow", "Automation", "Scribe"],
    "数据治理": ["FHIR", "数据标准", "互联互通", "数据中台"],
    "监管合规": ["FDA", "NMPA", "CE", "审批", "合规"],
    "商业模式": ["SaaS", "订阅", "按次收费", "解决方案"]
}

# --- Translation Helpers ---
def translate_html_safe(html_content, target='zh-CN'):
    if not html_content: return ""
    try:
        translator = GoogleTranslator(source='auto', target=target)
        if len(html_content) <= 4900:
            return translator.translate(html_content)
            
        chunks = []
        current_chunk = ""
        parts = html_content.split('</p>')
        for i, part in enumerate(parts):
            if i < len(parts) - 1:
                part += '</p>'
            if len(current_chunk) + len(part) < 4900:
                current_chunk += part
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = part
        if current_chunk:
            chunks.append(current_chunk)
            
        translated_chunks = []
        for c in chunks:
            if len(c) > 4900:
                translated_chunks.append(translator.translate(c[:4900]))
            else:
                res = translator.translate(c)
                translated_chunks.append(res if res else c)
        return "".join(translated_chunks)
    except Exception as e:
        print(f"Translation error: {e}")
        return html_content

def process_translations(items):
    print("🌍 正在执行本地预翻译 (Backend Pre-translation)...")
    for item in items:
        # If the item doesn't have a title_zh yet, it means it's newly scraped or un-translated
        if "title_zh" not in item:
            original_lang = item.get("lang", "zh")
            if original_lang == "en":
                # print(f"    [EN->ZH] Translating: {item['title'][:30]}...")
                item["title_en"] = item["title"]
                item["summary_en"] = item["summary"]
                item["content_en"] = item["full_content"]
                
                item["title_zh"] = translate_html_safe(item["title"], 'zh-CN')
                item["summary_zh"] = translate_html_safe(item["summary"], 'zh-CN')
                item["content_zh"] = translate_html_safe(item["full_content"], 'zh-CN')
            else:
                # Original is Chinese
                item["title_zh"] = item["title"]
                item["summary_zh"] = item["summary"]
                item["content_zh"] = item["full_content"]
                
                item["title_en"] = translate_html_safe(item["title"], 'en')
                item["summary_en"] = translate_html_safe(item["summary"], 'en')
                # Content translation for ZH to EN is often too heavy and might hit rate limits fast,
                # but let's try it since user wants "中英互译"
                item["content_en"] = translate_html_safe(item["full_content"], 'en')
    return items

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
    新四层过滤漏斗机制 (The New 4-Tier Funnel)
    输出：
        {
            "score": 总分,
            "level": S/A/B/C,
            "tags": [],
            "detail": {...}
        }
    """
    text = (title + " " + summary).lower()
    title_lower = title.lower()
    
    # --- 词库定义 ---
    WHITELIST_SOURCES = ["Eric Topol", "Doctor Penguin", "FDA", "KevinMD", "The Doctor Weighs In", "Google Health", "Mayo Clinic", "NEJM"]
    
    STRONG_MED_PHRASES = [
        "临床决策支持", "病历生成", "辅助诊断", "数字疗法", "多学科会诊", "互联网医院", "医疗数据治理",
        "临床试验", "医保控费", "靶点发现", "电子病历", "智慧医院", "分级诊疗", "DRG/DIP", "医疗质量",
        "clinical workflow", "medical scribe", "ambient ai", "clinical documentation", 
        "drug discovery", "care pathway", "electronic health record"
    ]
    
    STRONG_MED = [
        "临床", "病历", "诊断", "药物", "手术", "医院", "患者", "医生", "影像", "基因", 
        "EMR", "HIS", "FDA", "器械", "医保", "处方", "慢病", "护理", "问诊", "科室",
        "靶点", "筛查", "疗法", "医疗", "医学", "药企", "新药", "卫健委", "医保局",
        "挂号", "就诊", "门诊", "住院", "体检", "随访", "药房", "药监局", "NMPA", "院感",
        "medical", "clinical", "healthcare", "patient", "doctor", "hospital", "radiology",
        "surgery", "drug", "pharma", "therapy", "disease", "health", "care", "prescription", "triage"
    ]
    
    TECH_PHRASES = [
        "医疗大模型", "ai制药", "医疗ai", "ai医疗", "radiology ai", "healthcare copilot"
    ]
    
    TECH = [
        "大模型", "算法", "系统", "产品", "模型", "saas", "研发", "自动化",
        "gpt", "llm", "agent", "平台", "软件", "应用", "架构", "ai", "数据", "智能", "算力",
        "model", "algorithm", "system", "product", "software", "data", "platform",
        "generative", "architecture", "copilot", "automation"
    ]
    
    INTENT = ["发布", "上线", "推出", "研究", "试验", "结果", "获批", "launch", "deploy", "announce", "study", "trial", "result", "approved"]
    BUSINESS = ["融资", "商业化", "收入", "降本增效", "收购", "ipo", "funding", "startup", "revenue", "roi", "efficiency", "cost", "acquisition"]
    ENTITIES = ["openai", "google", "microsoft", "nvidia", "mayo clinic", "cleveland clinic", "辉瑞", "阿斯利康", "联影", "迈瑞", "卫宁"]
    NEGATIVE = ["减肥", "美容", "护肤", "健身", "穿搭", "娱乐", "游戏", "旅游", "网红", "主播", "带货", "食谱", "宠物"]
    PAN_TECH = ["互联网", "大厂", "出海", "字节", "腾讯", "阿里", "电商", "社交", "元宇宙", "web3"]

    score = 0
    tags = set()
    
    # --- Layer 1: 医疗纯度入场券 (The Medical Purity Gate) ---
    med_purity_score = 0
    
    # 1. 命中大招（医疗短语/实体）
    for p in STRONG_MED_PHRASES + ENTITIES:
        if p in text:
            med_purity_score += 8
            tags.add("核心医疗")
            break
            
    # 2. 平A命中（基础医疗词累加）
    med_hits = sum(1 for kw in STRONG_MED if kw in text)
    med_purity_score += med_hits * 2
    
    # 3. 蹭热点惩罚（稀释惩罚）
    pan_tech_hits = sum(1 for kw in PAN_TECH if kw in text)
    if pan_tech_hits > 2 and med_hits <= 2:
        med_purity_score -= 10 # 严重稀释，很可能是蹭热点
        
    if med_purity_score < 5:
        return {"score": 0, "level": "C", "tags": [], "detail": {"reason": "Low medical purity"}}
        
    score += med_purity_score
    
    # --- Layer 2: 黄金标题权重 (The Title Boost) ---
    for kw in STRONG_MED + STRONG_MED_PHRASES:
        if kw in title_lower:
            score += 6
            tags.add("强医疗相关")
            break

    # --- Layer 3: 增益叠加层 (The Multiplier Boosts) ---
    ai_boost_score = 0
    
    # AI 增益
    for p in TECH_PHRASES:
        if p in text:
            ai_boost_score += 8
            tags.add("AI核心场景")
            break
            
    tech_hits = sum(1 for kw in TECH if kw in text)
    ai_boost_score += tech_hits * 1.5
    
    if ai_boost_score > 0:
        score += ai_boost_score
        tags.add("AI增益")
        
    # 商业与意图增益
    for kw in BUSINESS:
        if kw in text:
            score += 4
            tags.add("商业动态")
            break
            
    for kw in INTENT:
        if kw in text:
            score += 3
            tags.add("前沿资讯")
            break
            
    # 白名单光环
    whitelist_hit = any(w.lower() in source_name.lower() for w in WHITELIST_SOURCES)
    if whitelist_hit:
        score += 5
        tags.add("高可信信源")
        
    # --- Layer 4: 降噪与分级判定 (Noise Reduction & Grading) ---
    # 负面降噪
    for kw in NEGATIVE:
        if kw in text:
            score -= 5
            
    # 密度惩罚
    length = len(text)
    if length > 300:
        density = score / (length / 100)
        if density < 2: # 要求每100字至少有2分
            score -= 4
            
    # 最终评级
    if score >= 25:
        level = "S"
    elif score >= 15:
        level = "A"
    elif score >= 8:
        level = "B"
    else:
        level = "C"
        
    return {
        "score": score,
        "level": level,
        "tags": list(tags),
        "detail": {
            "med_purity_score": med_purity_score,
            "ai_boost_score": ai_boost_score,
            "is_pure_medical": ai_boost_score == 0
        }
    }

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

def get_requests_session():
    """创建一个带有重试机制和强力 Timeout 的 Requests Session"""
    session = requests.Session()
    retry = Retry(
        total=3,  # 总共重试 3 次
        backoff_factor=1,  # 遇到错误后，重试的等待时间会指数级增加 (1s, 2s, 4s)
        status_forcelist=[429, 500, 502, 503, 504],  # 这些状态码会触发重试
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"] # 允许 POST 重试
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

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
                    eval_result = calculate_med_score(title, summary, source_name)
                    
                    if eval_result["level"] == "C": 
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
                    final_tags = list(set(smart_tags + eval_result.get("tags", [])))
                        
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
                        "level": eval_result["level"],
                        "tags": final_tags,
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
    
    session = get_requests_session()
    
    # 每次运行随机抽取 15 个关键词进行搜索，避免单次请求过多被封 IP
    sampled_keywords = random.sample(SEARCH_KEYWORDS, min(15, len(SEARCH_KEYWORDS)))
    
    for keyword in sampled_keywords:
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
                
                # 引入随机休眠，防反爬
                time.sleep(random.uniform(2, 5))
                
                # 增加更长更强健的 timeout: (connect_timeout, read_timeout)
                response = session.post(url, data=payload, headers=headers, timeout=(10, 30))
                
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
                        eval_result = calculate_med_score(title, summary, "人人都是产品经理")
                        if eval_result["level"] == "C": 
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
                        final_tags = list(set(smart_tags + eval_result.get("tags", [])))
                        full_html = extract_full_text(article_url)

                        items.append({
                            "title": title,
                            "source": f"人人都是产品经理",
                            "category": "Product",
                            "level": eval_result["level"],
                            "tags": final_tags,
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
    
    session = get_requests_session()
    
    # 每次运行随机抽取 15 个关键词进行搜索，避免触发限流
    sampled_keywords = random.sample(SEARCH_KEYWORDS, min(15, len(SEARCH_KEYWORDS)))
    
    for keyword in sampled_keywords:
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
            
            # 引入随机休眠
            time.sleep(random.uniform(1, 3))
            
            # 增加 timeout 设置
            response = session.post(url, json=payload, headers=headers, timeout=(10, 30))
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
                            eval_result = calculate_med_score(title, summary, "36氪")
                            if eval_result["level"] == "C": 
                                # print(f"    [Filtered] {title} (Score: {eval_result['score']})")
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
                            final_tags = list(set(smart_tags + eval_result.get("tags", [])))
                            full_html = extract_full_text(article_url)
                            
                            items.append({
                                "title": title,
                                "source": "36氪",
                                "category": "Market",
                                "level": eval_result["level"],
                                "tags": final_tags,
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
                
                eval_result = calculate_med_score(title, summary_clean, "Medium")
                if eval_result["level"] == "C": 
                    continue
                    
                time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    time_str = datetime.datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M")
                    
                if not is_article_fresh(time_str, "Medium"):
                    continue
                    
                smart_tags = generate_tags(title, summary_clean, "Insights")
                final_tags = list(set(smart_tags + eval_result.get("tags", [])))
                
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
                    "level": eval_result["level"],
                    "tags": final_tags,
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
    
    # 7. Apply Translations
    unique_news = process_translations(unique_news)
    
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
