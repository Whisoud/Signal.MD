import json
import datetime
import os
import feedparser
import time
import requests
import io
from email.utils import parsedate_to_datetime

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

# 数据源 (复用 scraper.py 的源，也可以增加更多)
RSS_SOURCES = {
    "36氪": "https://36kr.com/feed",
    "机器之心": "https://www.jiqizhixin.com/rss",
    "量子位": "https://www.qbitai.com/feed",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "Hacker News": "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT+OR+DeepSeek+OR+Transformer",
    # "Github Trending": "https://rsshub.app/github/trending/daily/python",
    # "Hugging Face": "https://rsshub.app/huggingface/daily-papers"
}

def fetch_24h_news():
    """抓取过去 24 小时内的所有新闻"""
    print("正在收集过去 24 小时的 AI 资讯...")
    
    news_items = []
    now = datetime.datetime.now(datetime.timezone.utc)
    one_day_ago = now - datetime.timedelta(hours=24)
    
    for source_name, rss_url in RSS_SOURCES.items():
        try:
            print(f"正在扫描: {source_name}")
            
            # 使用 requests 带 Header 抓取，复用 scraper.py 的防反爬逻辑
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            try:
                resp = requests.get(rss_url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    print(f"请求失败 {source_name}: {resp.status_code}")
                    continue
                content_to_parse = io.BytesIO(resp.content)
            except Exception as req_err:
                print(f"网络请求错误 {source_name}: {req_err}，尝试直接解析...")
                content_to_parse = rss_url

            feed = feedparser.parse(content_to_parse)
            
            for entry in feed.entries:
                # 解析时间
                published_dt = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_dt = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed), datetime.timezone.utc)
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    published_dt = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed), datetime.timezone.utc)
                
                # 如果找不到时间，默认保留（防止漏掉）
                if not published_dt:
                    published_dt = now 

                # 筛选 24h 内的新闻
                if published_dt >= one_day_ago:
                    summary_clean = entry.summary if hasattr(entry, 'summary') else ""
                    summary_clean = summary_clean.replace('<p>', '').replace('</p>', '').replace('<br>', '')[:200]
                    
                    news_items.append(f"【来源：{source_name}】标题：{entry.title}\n摘要：{summary_clean}\n")
                    
        except Exception as e:
            print(f"源 {source_name} 读取失败: {e}")
            
    print(f"共收集到 {len(news_items)} 条 24h 内的新闻。")
    return news_items

def generate_daily_brief(news_items):
    """调用 LLM 生成结构化早报"""
    if not news_items:
        return {
            "date": datetime.datetime.now().strftime("%Y年%m月%d日"),
            "content": "过去 24 小时暂无重大 AI 资讯。"
        }

    # 拼接素材
    context = "\n---\n".join(news_items)
    
    system_prompt = """你是一位专业的科技媒体主编。请根据提供的过去24小时全球AI新闻素材，撰写一份《AI 每日晨报》。
    
    写作要求：
    1.  **结构化**：请按照以下分类整理（如果没有相关内容可跳过该分类）：
        -   🔴 **今日头条** (最重要的 1-2 件事)
        -   🏢 **大厂动态** (OpenAI, Google, Meta, 阿里, 字节等)
        -   🛠 **工具与开源** (新模型、新框架、Github热榜)
        -   🔬 **前沿研究** (论文、技术突破)
        -   💼 **行业应用** (医疗、金融、法律等落地)
    2.  **风格**：参考“人人都是产品经理”早报风格，简洁、干练、客观。
    3.  **格式**：使用 HTML 标签进行排版。
        -   小标题用 `<h3>` 加 emoji。
        -   每条新闻用 `<li>`，重点词汇可以加粗 `<strong>`。
        -   整体包裹在 `<div>` 中。
    4.  **去重**：如果多条新闻讲的是同一件事，请合并。
    5.  **总结**：在开头写一段 50 字以内的“昨日复盘”，概括整体风向。
    """

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
                {"role": "user", "content": f"以下是新闻素材：\n{context}"}
            ],
            "stream": False
        }
        
        print(f"正在请求 {LLM_MODEL} 生成晨报...")
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            # 清理可能包含的 markdown 代码块标记
            content = content.replace("```html", "").replace("```", "")
            
            return {
                "date": datetime.datetime.now().strftime("%m月%d日 星期%w").replace("星期0","星期日").replace("星期1","星期一").replace("星期2","星期二").replace("星期3","星期三").replace("星期4","星期四").replace("星期5","星期五").replace("星期6","星期六"),
                "content": content
            }
        else:
            print(f"API 调用失败: {response.status_code} - {response.text}")
            return None

        # DeepSeek 调用 (已注释备份)
        # url = "https://api.deepseek.com/chat/completions"
        # headers = { ... }
        # data = { "model": "deepseek-chat", ... }
        # ...
            
    except Exception as e:
        print(f"生成失败: {e}")
        return None

def save_brief(data):
    if not data:
        return
    
    os.makedirs("data", exist_ok=True)
    file_path = "data/daily_brief.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"早报已保存至 {file_path}")

if __name__ == "__main__":
    # 临时清除代理（同 scraper.py）
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)
    
    items = fetch_24h_news()
    brief_data = generate_daily_brief(items)
    save_brief(brief_data)
