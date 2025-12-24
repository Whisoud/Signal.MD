import json
import datetime
import os
import feedparser
import time
import requests

# DeepSeek API 配置 (已注释，备用)
# DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "REMOVED_FOR_SECURITY")
# DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Qwen-Max API 配置 (OpenAI 兼容)
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "sk-68cb34e771b942a397d04e1dcaadd279")
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen-max"

# 当前使用的 LLM 配置
LLM_API_KEY = QWEN_API_KEY
LLM_BASE_URL = QWEN_BASE_URL
LLM_MODEL = QWEN_MODEL

# 真实数据源 (RSS)
RSS_SOURCES = {
    "36氪": "https://36kr.com/feed", # 新增：科技创投风向
    
    # 国内最专业的 AI 媒体
    "机器之心": "https://www.jiqizhixin.com/rss",
    "量子位": "https://www.qbitai.com/feed",  # 新增：补充产业视角
    
    # 硅谷创投风向 (AI 垂直频道)
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    
    # 极客与开发者 (硬核信号)
    "Hacker News": "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT+OR+DeepSeek+OR+Transformer",
    
    # "Github Trending": "https://rsshub.app/github/trending/daily/python", # 暂时移除
    # "Hugging Face": "https://rsshub.app/huggingface/daily-papers" # 暂时移除
}

# 关键词过滤库 (只要标题或摘要包含其中任意一个，就保留)
AI_KEYWORDS = [
    "AI", "人工智能", "大模型", "LLM", "GPT", "DeepSeek", "OpenAI", 
    "Claude", "Gemini", "Sora", "Midjourney", "Stable Diffusion",
    "Transformer", "算力", "芯片", "英伟达", "NVIDIA", "机器人", 
    "Agent", "智能体", "自动驾驶", "Copilot", "机器学习", "RAG"
]

def check_is_ai_news(title, content):
    """调用 LLM 判断这是否是一篇有价值的 AI 新闻"""
    if not LLM_API_KEY:
        return True # 没有 Key 就默认不过滤
        
    try:
        # Qwen-Max 调用 (OpenAI 兼容接口)
        url = f"{LLM_BASE_URL}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
        data = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "你是一个新闻过滤器。请判断用户提供的新闻是否属于“人工智能(AI)领域的有价值行业资讯”。\n如果是，请只回复“YES”；\n如果不是（例如纯娱乐、纯硬件无关AI、或者太水的内容），请只回复“NO”。\n不要解释，只回复 YES 或 NO。"},
                {"role": "user", "content": f"标题：{title}\n摘要：{content}"}
            ],
            "stream": False
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            answer = result['choices'][0]['message']['content'].strip().upper()
            return "YES" in answer
        return True # 接口报错默认保留

        # DeepSeek 调用 (已注释备份)
        # url = "https://api.deepseek.com/chat/completions"
        # headers = {
        #     "Content-Type": "application/json",
        #     "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        # }
        # data = {
        #     "model": "deepseek-chat",
        #     "messages": [ ... ],
        #     "stream": False
        # }
        # ...

    except:
        return True

def generate_ai_summary(title, content):
    """直接使用 requests 调用 LLM API (Qwen-Max)"""
    if not LLM_API_KEY:
        return content[:100] + "..."
    
    # 如果摘要太短（可能是 RSS 限制），提示 AI 重点看标题
    system_prompt = """You are a senior tech analyst. Analyze the news content and output JSON result.
    
    Rules:
    1. 'summary': Generate a concise summary (Max 2 lines) in the **ORIGINAL language** of the news.
    2. 'trans_title': Translate the title into **Simplified Chinese**. (If original is Chinese, keep it same).
    3. 'trans_summary': Translate your summary into **Simplified Chinese**. (If original is Chinese, keep it same).
    4. 'lang': Detect language ('zh' or 'en').
    5. 'score': Rate 0-100 (90+=Breaking, 80+=Important, 70+=Normal, 60-=Low value).
    6. NO title repetition in summary! Use 3rd person perspective.

    JSON Format:
    {
        "summary": "Original language summary...",
        "trans_title": "中文标题...",
        "trans_summary": "中文摘要...",
        "lang": "en", 
        "score": 85
    }
    """
    
    if len(content) < 50: # 如果摘要本身就很短
        system_prompt += "\nNote: Content is short, infer from title but DO NOT just repeat it."

    try:
        # Qwen-Max 调用
        url = f"{LLM_BASE_URL}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
        data = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"新闻标题：{title}\n新闻摘要：{content}"}
            ],
            "response_format": { "type": "json_object" }, # 强制 JSON 输出
            "stream": False
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            content_str = result['choices'][0]['message']['content']
            try:
                # 解析 JSON
                data = json.loads(content_str)
                return data # 返回字典 {'summary': '...', 'score': 85}
            except:
                return {"summary": content_str, "score": 70} # 解析失败兜底
        else:
            print(f"API 调用失败: {response.status_code} - {response.text}")
            return "AI 分析暂不可用"

        # DeepSeek 调用 (已注释备份)
        # url = "https://api.deepseek.com/chat/completions"
        # headers = { ... }
        # data = { "model": "deepseek-chat", ... }
        # ...
            
    except Exception as e:
        print(f"AI 摘要生成失败: {e}")
        return "AI 分析暂不可用"

def fetch_rss_news():
    print("正在抓取真实 AI 资讯...")
    
    news_list = []
    
    # 计算7天前的截止时间 (UTC+8) - 放宽限制，确保低频源也有内容
    now = datetime.datetime.now()
    seven_days_ago = now - datetime.timedelta(days=7)
    print(f"🕒 时间窗口限制: 只抓取 {seven_days_ago.strftime('%Y-%m-%d %H:%M')} 之后的文章")
    
    for source_name, rss_url in RSS_SOURCES.items():
        try:
            print(f"正在抓取: {source_name} ({rss_url})")
            feed = feedparser.parse(rss_url)
            
            source_count = 0 # 当前源已抓取的有效 AI 新闻数量
            
            # 遍历所有条目
            for entry in feed.entries:
                if source_count >= 20: # 每个源最多取 20 条有效内容
                    break
                
                # --- 时间过滤逻辑开始 ---
                published_dt = None
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        # entry.published_parsed 是 UTC 时间 struct_time
                        dt_utc = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                        published_dt = dt_utc + datetime.timedelta(hours=8) # 转为北京时间
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        dt_utc = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                        published_dt = dt_utc + datetime.timedelta(hours=8)
                except:
                    pass
                
                # 如果解析出时间，且时间早于7天前，直接跳过
                if published_dt and published_dt < seven_days_ago:
                    # print(f"⏳ 跳过过时文章 ({published_dt}): {entry.title}")
                    continue
                # --- 时间过滤逻辑结束 ---

                # 1. 组合标题和摘要用于搜索
                summary_raw = entry.summary if hasattr(entry, 'summary') else ""
                # 去除 HTML 标签
                summary_clean = summary_raw.replace('<p>', '').replace('</p>', '').replace('<br>', '')
                
                full_text = (entry.title + summary_clean).lower() 
                
                # 2. 关键词初筛 (保留这个是为了省钱，过滤掉明显无关的)
                if not any(k.lower() in full_text for k in AI_KEYWORDS):
                    # print(f"跳过非 AI 内容: {entry.title}") # 调试用
                    continue 
                
                # 3. AI 判官终审 (新增)
                # print(f"🔍 AI 正在审核: {entry.title[:15]}...")
                
                # 对于垂直 AI 媒体（如机器之心、量子位、TechCrunch），直接信任，不进行 LLM 过滤，防止误杀
                if source_name in ["机器之心", "量子位", "TechCrunch AI"]:
                    is_ai_related = True
                else:
                    summary_for_check = summary_clean[:200]
                    is_ai_related = check_is_ai_news(entry.title, summary_for_check)
                
                if not is_ai_related:
                    print(f"❌ AI 判定无关/水文，跳过: {entry.title}")
                    continue

                source_count += 1 # 有效 AI 新闻计数 +1

                # 4. AI 生成摘要
                print(f"正在 AI 总结: {entry.title[:10]}...")
                ai_result = generate_ai_summary(entry.title, summary_clean)
                
                # 处理 AI 返回结果（可能是字典，也可能是出错时的字符串）
                if isinstance(ai_result, dict):
                    ai_summary = ai_result.get("summary", "暂无摘要")
                    hot_score = ai_result.get("score", 70)
                    trans_title = ai_result.get("trans_title", "")
                    trans_summary = ai_result.get("trans_summary", "")
                    lang = ai_result.get("lang", "zh")
                else:
                    ai_summary = str(ai_result)
                    hot_score = 70 # 默认分
                    trans_title = ""
                    trans_summary = ""
                    lang = "zh"

                print(f"✅ 生成结果: {hot_score}分 | {ai_summary[:30]}... | Lang: {lang}") 

                # 处理时间 (统一转换为北京时间 UTC+8)
                published_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") # 默认当前时间
                
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        # entry.published_parsed 是一个 UTC 的 struct_time
                        dt_utc = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                        # 加上 8 小时变北京时间
                        dt_bj = dt_utc + datetime.timedelta(hours=8)
                        published_time = dt_bj.strftime("%Y-%m-%d %H:%M")
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                         # 有些源只有 updated 字段
                        dt_utc = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                        dt_bj = dt_utc + datetime.timedelta(hours=8)
                        published_time = dt_bj.strftime("%Y-%m-%d %H:%M")
                except Exception as e:
                    print(f"时间解析失败: {e}")

                news_list.append({
                    "title": entry.title,
                    "source": source_name,
                    "time": published_time,
                    "url": entry.link,
                    "summary": ai_summary, # 原文摘要
                    "trans_title": trans_title, # 翻译标题
                    "trans_summary": trans_summary, # 翻译摘要
                    "lang": lang, # 语言标识
                    "hot_score": hot_score # 使用 AI 打出的评分
                })
                
        except Exception as e:
            print(f"抓取 {source_name} 失败: {e}")

    # 按时间降序排序 (最新的在最前)
    # 注意：这里的 time 格式是 "YYYY-MM-DD HH:MM"，可以直接字符串排序
    news_list.sort(key=lambda x: x['time'], reverse=True)
    
    # 如果没抓到数据（防止网络问题导致页面空），保留一些模拟数据作为兜底
    if not news_list:
        print("警告：未抓取到任何真实数据，使用兜底数据。")
        return get_mock_data()

    return news_list

def get_mock_data():
    return [
        {
            "title": "（兜底数据）DeepSeek 发布 V4 模型，性能超越 GPT-5",
            "source": "模拟源",
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "url": "#",
            "summary": "这是因为网络抓取失败而显示的模拟数据。",
            "hot_score": 9999
        }
    ]

def save_data(data):
    os.makedirs("data", exist_ok=True)
    file_path = "data/news.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"数据已保存至 {file_path} (共 {len(data)} 条)")

if __name__ == "__main__":
    news_data = fetch_rss_news()
    save_data(news_data)
