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
import random
import re
import sys
from supabase import create_client, Client

# --- Supabase Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ 警告: 未检测到 SUPABASE_URL 或 SUPABASE_KEY 环境变量，将无法写入数据库。")
    supabase = None

# --- Configuration ---
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Global timeout configuration
GLOBAL_START_TIME = time.time()
MODE = "backfill" if "--backfill" in sys.argv else "normal"
MAX_EXECUTION_TIME = 3 * 60 * 60 if MODE == "backfill" else 8 * 60
BACKFILL_GET_FULL_CONTENT = True # For backfill mode, always try to get full content as per user request

BACKFILL_TIER2_ENABLED = "--backfill-tier2" in sys.argv

def _get_cli_int(prefix, default_value):
    for arg in sys.argv:
        if arg.startswith(prefix):
            try:
                return int(arg.split("=", 1)[1])
            except Exception:
                return default_value
    return default_value

BACKFILL_TIER2_BATCH_COUNT = _get_cli_int("--backfill-batch-count=", 6)
BACKFILL_TIER2_BATCH_INDEX = _get_cli_int("--backfill-batch-index=", -1)

def check_timeout():
    if time.time() - GLOBAL_START_TIME > MAX_EXECUTION_TIME:
        print("⚠️ [Global Timeout] 抓取任务接近时间上限，正在执行优雅停机...")
        return True
    return False

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
# Tier 1: 核心高频关键词 (每次必跑，代表行业主航道与高商业价值)
TIER_1_KEYWORDS = [
    "医疗大模型", 
    "AI医疗", 
    "临床诊疗", 
    "患者服务", 
    "医疗影像",
    "数字医院",
    "医疗政策",
    "问诊",
    "病历",
    "CDSS"
]

# Tier 2: 探索与细分关键词 (每次随机抽取部分)
TIER_2_KEYWORDS = [
    "医疗信息化",
    "智慧医疗",
    "医疗科技",

    # 临床诊疗 (Removed "临床诊疗" which is in TIER_1)
    "辅助诊断",
    "临床决策支持系统",
    "智能分诊",
    "问诊机器人",
    "电子病历质控",
    "病历结构化",
    "临床路径",
    "多学科会诊 MDT",
    "随访管理",
    "复诊管理",
    "用药推荐",
    "处方审核",
    "合理用药",

    # 医院信息化 (13 terms, acceptable for now)
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

    # 医院运营 (10 terms)
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

    # 患者服务 (9 terms)
    "互联网医院",
    "在线问诊",
    "患者随访",
    "患者教育",
    "健康管理",
    "慢病管理",
    "远程医疗",
    "居家监测",
    "家庭医生",

    # AI技术 (9 terms)
    "医疗NLP",
    "医学知识图谱",
    "语音识别 医疗",
    "语音转写 Scribe",
    "医学OCR",
    "多模态医疗AI",
    "联邦学习 医疗",
    "隐私计算 医疗",
    "因果推断 医疗",

    # 医学影像细化 (Added "AI阅片" for 9 terms)
    "影像分割",
    "影像诊断",
    "病灶检测",
    "肺结节",
    "乳腺筛查",
    "脑卒中影像",
    "心脏影像",
    "数字病理",
    "AI阅片",

    # 药物研发 (Added "新药筛选", "药物重定向" for 10 terms)
    "AI药物研发",
    "分子生成",
    "靶点发现",
    "临床试验优化",
    "真实世界研究",
    "药物警戒",
    "精准医疗",
    "基因测序",
    "新药筛选",
    "药物重定向",

    # 意图增强 (Added 5 terms for 10 terms total)
    "医疗AI落地",
    "医疗AI实践",
    "医疗AI解决方案",
    "医疗AI应用场景",
    "医疗AI效果评估",
    "AI赋能医疗",
    "医疗AI商业模式",
    "医疗AI挑战",
    "医疗AI伦理",
    "医疗AI发展趋势"
]

def get_current_run_keywords():
    """动态生成本次运行的关键词：核心词 + 基于时间的切片轮询"""
    # 核心词每次必跑
    selected_keywords = list(TIER_1_KEYWORDS)
    
    # 获取 UTC 当前小时数
    current_hour = datetime.datetime.utcnow().hour
    
    # 假设每 4 小时跑一次 (GitHub Action Cron: 0 */4 * * *)
    # 把 TIER_2 分成 6 个批次 (每批大约 10-12 个词)
    batch_count = 6
    batch_index = (current_hour // 4) % batch_count
    
    # 对 TIER_2_KEYWORDS 进行固定的哈希/排序，确保每次切片稳定
    sorted_tier2 = sorted(TIER_2_KEYWORDS)
    
    # 计算切片起始和结束位置
    batch_size = len(sorted_tier2) // batch_count
    start_idx = batch_index * batch_size
    # 最后一个批次包揽剩余的所有词
    end_idx = (batch_index + 1) * batch_size if batch_index < batch_count - 1 else len(sorted_tier2)
    
    sampled_tier2 = sorted_tier2[start_idx:end_idx]
    
    selected_keywords.extend(sampled_tier2)
    
    print(f"🎯 本次调度关键词共 {len(selected_keywords)} 个 (Batch {batch_index + 1}/{batch_count})")
    print(f"   Tier 1 (必跑): {len(TIER_1_KEYWORDS)} 个")
    print(f"   Tier 2 (轮询): {sampled_tier2}")
    return selected_keywords

# Dynamically populate for legacy functions that might use it
SEARCH_KEYWORDS = get_current_run_keywords()

# --- Search Keywords Matrix (Expanded EN) ---
SEARCH_KEYWORDS_EN = [
    "Medical AI",
    "Healthcare LLM",
    "Clinical AI",
    "AI in Healthcare",
    "Generative AI Healthcare",
    
    # --- 暂时注释掉大部分关键词，用于测试防卡死 ---
    # "Radiology AI",
    # "Digital Health",
    
    # # Clinical
    # "Clinical Decision Support System",
    # "CDSS healthcare",
    # "AI Diagnosis",
    # "AI Triage",
    # "Medical Scribe",
    # "Clinical Documentation AI",
    # "Ambient AI Healthcare",
    # "Clinical Workflow AI",
    # "Care Pathway Optimization",

    # # Systems
    # "Hospital Information System",
    # "Electronic Medical Record",
    # "Electronic Health Record",
    # "FHIR Interoperability",
    # "Healthcare Data Platform",
    # "Clinical Data Repository",
    # "Healthcare Data Governance",

    # # Workflow AI
    # "AI Copilot for Doctors",
    # "Physician Workflow Automation",
    # "Clinical Productivity AI",
    # "Healthcare Automation",
    # "AI assisted charting",

    # # Imaging
    # "Computer Vision Healthcare",
    # "Radiology AI",
    # "Pathology AI",
    # "Digital Pathology",
    # "AI Screening",
    # "Lesion Detection",

    # # Pharma
    # "AI Drug Discovery",
    # "Computational Biology",
    # "Genomics AI",
    # "Precision Medicine",
    # "Real World Evidence",
    # "Clinical Trial AI",

    # # Business
    # "HealthTech Startup",
    # "Healthcare Funding",
    # "Digital Health Investment",
    # "MedTech IPO",
    # "Healthcare M&A",

    # # Intent (重要)
    # "case study healthcare AI",
    # "AI healthcare deployment",
    # "AI healthcare implementation",
    # "best practices healthcare AI",
    # "ROI healthcare AI"
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
def process_translations(items):
    # 翻译功能已移除，直接返回原数据
    # print("🌍 翻译功能已禁用，跳过翻译步骤...")
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
    
    # 【第一关：医疗一票否决白名单】 (必须包含其中之一才允许进入打分)
    CORE_MEDICAL_WORDS = [
        # 宏观与基础
        "医疗", "医药", "医学", "医生", "医院", "患者", "病患", "诊疗", "健康", "卫健委", "医保", "医改",
        "medical", "medicine", "healthcare", "doctor", "physician", "hospital", "patient", "clinical", "health",
        # 临床与诊断
        "临床", "诊断", "问诊", "随访", "处方", "病历", "电子病历", "查房", "影像", "放射", "超声", "CT", "MRI", 
        "肿瘤", "癌症", "慢性病", "慢病", "康复", "护理", "体检", "科室", "门诊", "住院",
        "diagnosis", "radiology", "oncology", "pathology", "EMR", "EHR", "surgery", "therapy", "disease", "imaging",
        # 药企与研发
        "药企", "制药", "药物研发", "新药", "靶点", "临床试验", "真实世界研究", "基因测序", "蛋白质", "分子生成", "药监局", "NMPA", "FDA",
        "pharma", "pharmaceutical", "drug discovery", "clinical trial", "genomics", "protein",
        # 医疗信息化与运营
        "智慧医院", "HIS", "PACS", "LIS", "CDSS", "临床决策支持", "分诊", "挂号", "医保控费", "DRG", "DIP", "互联互通", "互联网医院", "院感",
        "triage", "interoperability", "FHIR",
        # 医疗垂直 AI
        "数字疗法", "医疗大模型", "AI制药", "医学知识图谱", "AI问诊", "病历生成", "医疗AI",
        "DTx", "digital therapeutics", "medical scribe", "ambient ai"
    ]
    
    # 【已废除】PAN_TECH_NOISE：不再进行强惩罚，完全信任 CORE_MEDICAL_WORDS 的过滤能力。
    # 只要命中了核心医疗词，即使提到 Python/汽车，也大概率是高价值跨界信号。

    # --- 第一关：一票否决 ---
    is_core_medical = any(kw.lower() in text for kw in CORE_MEDICAL_WORDS)
    if not is_core_medical:
        # 如果连一个核心医疗词都没提到，直接枪毙
        return {"score": 0, "level": "C", "tags": [], "detail": {"reason": "Vetoed: No core medical keywords found"}}

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
            break
            
    # 2. 平A命中（基础医疗词累加）
    med_hits = sum(1 for kw in STRONG_MED if kw in text)
    med_purity_score += med_hits * 2
    
    # 3. 蹭热点惩罚（稀释惩罚）
    pan_tech_hits = sum(1 for kw in PAN_TECH if kw in text)
    if pan_tech_hits > 2 and med_hits <= 2:
        med_purity_score -= 10 # 严重稀释，很可能是蹭热点
        
    if med_purity_score < 5 and score < 10:
        return {"score": 0, "level": "C", "tags": [], "detail": {"reason": "Low medical purity"}}
        
    score += med_purity_score
    
    # --- Layer 2: 黄金标题权重 (The Title Boost) ---
    for kw in STRONG_MED + STRONG_MED_PHRASES:
        if kw in title_lower:
            score += 6
            break

    # --- Layer 3: 增益叠加层 (The Multiplier Boosts) ---
    ai_boost_score = 0
    
    # AI 增益
    for p in TECH_PHRASES:
        if p in text:
            ai_boost_score += 8
            break
            
    tech_hits = sum(1 for kw in TECH if kw in text)
    ai_boost_score += tech_hits * 1.5
    
    if ai_boost_score > 0:
        score += ai_boost_score
        
    # 商业与意图增益
    for kw in BUSINESS:
        if kw in text:
            score += 4
            break
            
    for kw in INTENT:
        if kw in text:
            score += 3
            break
            
    # 白名单光环
    whitelist_hit = any(w.lower() in source_name.lower() for w in WHITELIST_SOURCES)
    if whitelist_hit:
        score += 5
        
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
            response = requests.get(mobile_url, headers=headers, timeout=(5, 10))
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
        
        response = requests.get(url, headers=headers, timeout=(5, 10))
        
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
                    response = requests.get(new_url, headers=headers, timeout=(5, 10))
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
        if check_timeout(): break
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

def scrape_woshipm_direct(existing_urls, keywords=None, urls_need_enrich=None):
    """
    直接模拟官网搜索接口 POST 请求抓取
    Target: https://api.woshipm.com/search/result.html
    """
    print(f"正在抓取 人人都是产品经理 (Direct POST)...")
    items = []
    seen_urls = set(existing_urls) # Initialize with existing to avoid re-fetching
    urls_need_enrich = set(urls_need_enrich or set())
    
    url = "https://api.woshipm.com/search/result.html"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.woshipm.com/",
        "Origin": "https://www.woshipm.com",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    
    if keywords is None:
        if MODE == "backfill":
            keywords = list(dict.fromkeys(TIER_1_KEYWORDS + ["医疗", "AI"]))
        else:
            keywords = SEARCH_KEYWORDS

    for keyword in keywords:
        if check_timeout(): break
        print(f"  -> 关键词: {keyword}")
        
        # 智能早停标记
        continuous_old_count = 0 
        
        max_pages = 60 if MODE == "backfill" else 3
        for page in range(1, max_pages + 1):
            if check_timeout(): break
            
            # 如果上一页已经连续遇到老数据，提前结束当前关键词的翻页
            if MODE != "backfill" and continuous_old_count >= 5:
                print(f"     [Early Stop] {keyword} 遇到过多历史数据，停止翻页")
                break
                
            try:
                payload = {
                    "key": keyword,
                    "tab": "0", # 0=文章
                    "page": str(page),
                    "sortType": "1" if MODE == "backfill" else "0",
                    "idSearch": "" 
                }
                
                response = requests.post(url, data=payload, headers=headers, timeout=(5, 10))
                
                if response.status_code != 200:
                    continue
                    
                soup = BeautifulSoup(response.text, "html.parser")
                article_nodes = soup.find_all("div", class_="course--item")
                if not article_nodes:
                    break

                page_old_count = 0
                
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
                        
                        # Deduplication & Early Stop signal
                        if article_url in seen_urls and article_url not in urls_need_enrich:
                            if MODE != "backfill":
                                continuous_old_count += 1
                            continue
                            
                        # Reset if we find a new one
                        if MODE != "backfill":
                            continuous_old_count = 0
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
                            if MODE == "backfill":
                                page_old_count += 1
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
                        if article_url in urls_need_enrich:
                            urls_need_enrich.discard(article_url)
                        
                    except Exception as e:
                        continue

                if MODE == "backfill" and page_old_count >= len(article_nodes):
                    break
                        
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
        if check_timeout(): break
        print(f"  -> 关键词: {keyword}")
        
        continuous_old_count = 0
        
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
            
            response = requests.post(url, json=payload, headers=headers, timeout=(5, 10))
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
                                continuous_old_count += 1
                                # 36kr 是单页大列表，如果连续遇到 5 个已抓取的，直接结束该关键词
                                if continuous_old_count >= 5:
                                    print(f"     [Early Stop] {keyword} 遇到过多历史数据，跳过后续解析")
                                    break
                                continue
                                
                            continuous_old_count = 0
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

def load_existing_urls(filepath="data/news.json"):
    """Load existing URLs to build a stateful memory for deduplication. Prefer Supabase."""
    urls = set()
    if supabase:
        print("📦 正在从 Supabase 获取已有数据的 URL 列表建立去重池...")
        try:
            # Supabase defaults to returning up to 1000 rows.
            # For a production app with more data, we would paginate this or query specifically.
            # For now, fetching the last 2000 URLs is sufficient for deduplication.
            response = supabase.table("signals").select("url").order("time", desc=True).limit(3000).execute()
            urls = {item['url'] for item in response.data if item.get('url')}
            print(f"📦 从 Supabase 成功获取 {len(urls)} 个近期 URL。")
            return urls
        except Exception as e:
            print(f"⚠️ 从 Supabase 获取 URL 失败，降级读取本地: {e}")
            
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                urls = {item.get('url') for item in data if item.get('url')}
                print(f"📦 从本地 JSON 成功获取 {len(urls)} 个已知 URL。")
                return urls
        except Exception as e:
            print(f"⚠️ 无法读取本地数据: {e}")
    return urls



def fetch_all_data():
    """主调度函数: 状态记忆增量抓取"""
    print("开始执行状态记忆增量抓取任务...")
    
    # 1. Load existing state for deduplication
    existing_urls = load_existing_urls()
    
    new_items = []

    if MODE == "backfill":
        # Simplified backfill for Supabase era: just scrape and ignore full_content enrichment for old JSON
        # Since we use Supabase now, backfill mostly means fetching deeper pages.
        sorted_tier2 = sorted(TIER_2_KEYWORDS)
        batch_count = max(1, BACKFILL_TIER2_BATCH_COUNT)
        batch_size = max(1, len(sorted_tier2) // batch_count)

        batch_indices = [BACKFILL_TIER2_BATCH_INDEX] if BACKFILL_TIER2_BATCH_INDEX >= 0 else list(range(batch_count))

        if BACKFILL_TIER2_ENABLED:
            print("🚀 正在执行: 人人都是产品经理 (Backfill Tier2 by Time)...")
        else:
            print("🚀 正在执行: 人人都是产品经理 (Backfill by Time)...")

        for batch_index in batch_indices:
            if check_timeout():
                break
            if batch_index < 0 or batch_index >= batch_count:
                continue

            start_idx = batch_index * batch_size
            end_idx = (batch_index + 1) * batch_size if batch_index < batch_count - 1 else len(sorted_tier2)
            tier2_slice = sorted_tier2[start_idx:end_idx] if BACKFILL_TIER2_ENABLED else []

            keywords = list(dict.fromkeys(TIER_1_KEYWORDS + ["医疗", "AI"] + tier2_slice))
            print(f"🎯 Backfill 批次 {batch_index + 1}/{batch_count} | 关键词 {len(keywords)} 个")

            woshipm_data = scrape_woshipm_direct(existing_urls, keywords=keywords)
            new_items.extend(woshipm_data)
            existing_urls.update(item["url"] for item in woshipm_data if item.get("url"))
    else:
    
        # 2. RSS Feeds (Passing existing URLs)
        rss_data = fetch_rss_feeds(existing_urls)
        new_items.extend(rss_data)
        existing_urls.update(item["url"] for item in rss_data if item.get("url"))
        
        # 3. Woshipm - Direct Scrape with Multiple Keywords
        print("🚀 正在执行: 人人都是产品经理 (Multiple Keywords)...")
        woshipm_data = scrape_woshipm(existing_urls)
        new_items.extend(woshipm_data)
        existing_urls.update(item["url"] for item in woshipm_data if item.get("url"))
        
        # 4. 36kr - Direct Search API
        print("🚀 正在执行: 36氪 (Multiple Keywords)...")
        kr_data = scrape_36kr_direct(existing_urls)
        new_items.extend(kr_data)
        existing_urls.update(item["url"] for item in kr_data if item.get("url"))
        
        # 5. Medium - Tag RSS
        print("🚀 正在执行: Medium (Tag RSS)...")
        medium_data = scrape_medium_tags(existing_urls)
        new_items.extend(medium_data)
    
    print(f"✨ 本次增量抓取共获得 {len(new_items)} 条新数据。")
    
    # Sort by time descending
    new_items.sort(key=lambda x: x.get("time", ""), reverse=True)
    
    # 7. Apply Translations
    new_items = process_translations(new_items)
    
    return new_items

def save_data(new_items):
    # 增量推送至 Supabase (Cloud Native)
    if supabase and new_items:
        print(f"🚀 正在将 {len(new_items)} 条增量数据同步至 Supabase...")
        batch_size = 50
        for i in range(0, len(new_items), batch_size):
            batch = new_items[i:i+batch_size]
            try:
                # Upsert records based on unique 'url'
                response = supabase.table("signals").upsert(batch, on_conflict="url").execute()
                print(f"  -> 已成功同步批次 {i//batch_size + 1}, {len(batch)} 条数据")
            except Exception as e:
                print(f"❌ 同步到 Supabase 失败: {e}")
    elif not supabase:
        print("⚠️ 未配置 Supabase 环境变量，跳过数据库同步。")

    # 为了兼容降级逻辑，从 Supabase 拉取最新的 200 条数据保存为本地 fallback
    fallback_data = new_items
    if supabase:
        try:
            print("📦 正在从 Supabase 拉取最新 200 条数据生成 fallback JSON...")
            response = supabase.table("signals").select("*").order("time", desc=True).limit(200).execute()
            fallback_data = response.data
        except Exception as e:
            print(f"⚠️ 生成 fallback 数据失败: {e}")
            
    if fallback_data:
        os.makedirs("data", exist_ok=True)
        file_path = "data/news.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(fallback_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 最新降级数据 ({len(fallback_data)} 条) 已更新至 {file_path}")

if __name__ == "__main__":
    data = fetch_all_data()
    save_data(data)
