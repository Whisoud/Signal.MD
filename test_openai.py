import feedparser

feed = feedparser.parse("https://openai.com/news/rss.xml")
if feed.entries:
    e = feed.entries[0]
    print(f"Title: {e.title}")
    print(f"Summary length: {len(e.summary) if hasattr(e, 'summary') else 0}")
    print(f"Content length: {len(e.content[0].value) if hasattr(e, 'content') else 0}")
