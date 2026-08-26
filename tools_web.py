"""联网工具:web_search(Tavily)与 fetch_url(网页正文抓取)。"""
import os

import requests
from bs4 import BeautifulSoup


# 工具-网络搜索
def web_search(query):
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    payload = {
        "api_key": os.getenv("taily_api_key"),
        "query": query,
        "max_results": 5,
        "include_answer": True,
        "include_raw_content": True
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return f"搜索请求失败：{e}"
    except ValueError:
        return "搜索出错：响应不是有效的 JSON"
    results = data.get("results", [])
    if not results:
        return f"搜索「{query}」未找到结果"
    res = f"【搜索】{query}\n"
    for i, item in enumerate(results):
        res += (
            f"{i + 1}. {item.get('title', '')}\n"
            f"   {item.get('url', '')}\n"
            f"   {item.get('content', '')}\n\n"
        )
    return res


# 工具-网络抓取
def fetch_url(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        response.raise_for_status()
        # 清洗
        soup = BeautifulSoup(response.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # 去重空行 + 截断
        lines = [l for l in text.splitlines() if l.strip()]
        return "\n".join(lines)[:10000]  # 截到 10000 字,防 context 爆炸

    except Exception as e:
        return f"抓取失败：{type(e).__name__}: {e}"