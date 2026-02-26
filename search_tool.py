"""
外部搜索工具 - 使用 SerpAPI 或 DuckDuckGo 进行搜索
"""
import os
import aiohttp
from typing import List, Dict, Optional


class SearchTool:
    """外部搜索工具"""

    def __init__(self):
        self.serpapi_key = os.getenv("SERPAPI_KEY", "")
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        self.google_cx = os.getenv("GOOGLE_CX", "")

    async def search(self, query: str, num_results: int = 5) -> str:
        """
        执行搜索并返回格式化的结果

        优先级：
        1. SerpAPI (如果有 key)
        2. Google Custom Search (如果有 key 和 cx)
        3. DuckDuckGo (免费，无需 key)
        """
        if self.serpapi_key:
            return await self._search_serpapi(query, num_results)
        elif self.google_api_key and self.google_cx:
            return await self._search_google(query, num_results)
        else:
            return await self._search_duckduckgo(query, num_results)

    async def _search_serpapi(self, query: str, num_results: int) -> str:
        """使用 SerpAPI 搜索"""
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": self.serpapi_key,
            "engine": "google",
            "num": num_results,
            "hl": "zh-CN",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as resp:
                if resp.status != 200:
                    return f"搜索失败: HTTP {resp.status}"

                data = await resp.json()
                return self._format_serpapi_results(data)

    async def _search_google(self, query: str, num_results: int) -> str:
        """使用 Google Custom Search API"""
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": query,
            "key": self.google_api_key,
            "cx": self.google_cx,
            "num": min(num_results, 10),
            "hl": "zh-CN",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as resp:
                if resp.status != 200:
                    return f"搜索失败: HTTP {resp.status}"

                data = await resp.json()
                return self._format_google_results(data)

    async def _search_duckduckgo(self, query: str, num_results: int) -> str:
        """使用 DuckDuckGo 搜索 (通过 html 版本，无需 API key)"""
        # DuckDuckGo HTML 版本不需要 API key
        url = "https://html.duckduckgo.com/html/"
        data = {
            "q": query,
            "kl": "zh-cn",  # 中文结果
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers, timeout=30) as resp:
                    if resp.status != 200:
                        return f"搜索失败: HTTP {resp.status}"

                    html = await resp.text()
                    return self._parse_duckduckgo_html(html, num_results)
        except Exception as e:
            return f"搜索失败: {str(e)}"

    def _format_serpapi_results(self, data: Dict) -> str:
        """格式化 SerpAPI 搜索结果"""
        results = []

        # 获取搜索结果
        organic_results = data.get("organic_results", [])
        for i, result in enumerate(organic_results[:5], 1):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            link = result.get("link", "")
            results.append(f"[{i}] {title}\n{snippet}\n来源: {link}\n")

        # 如果有知识图谱，也加上
        kg = data.get("knowledge_graph", {})
        if kg:
            title = kg.get("title", "")
            description = kg.get("description", "")
            if title and description:
                results.insert(0, f"【知识图谱】{title}: {description}\n")

        return "\n".join(results) if results else "未找到相关搜索结果"

    def _format_google_results(self, data: Dict) -> str:
        """格式化 Google Custom Search 结果"""
        results = []
        items = data.get("items", [])

        for i, item in enumerate(items[:5], 1):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            results.append(f"[{i}] {title}\n{snippet}\n来源: {link}\n")

        return "\n".join(results) if results else "未找到相关搜索结果"

    def _parse_duckduckgo_html(self, html: str, num_results: int) -> str:
        """解析 DuckDuckGo HTML 结果"""
        from html.parser import HTMLParser

        class DuckDuckGoParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.in_result = False
                self.in_title = False
                self.in_snippet = False
                self.current_title = ""
                self.current_snippet = ""
                self.current_url = ""

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "div" and "result" in attrs_dict.get("class", ""):
                    self.in_result = True
                elif tag == "a" and self.in_result and "result__a" in attrs_dict.get("class", ""):
                    self.in_title = True
                    self.current_url = attrs_dict.get("href", "")
                elif tag == "a" and self.in_result and "result__snippet" in attrs_dict.get("class", ""):
                    self.in_snippet = True

            def handle_endtag(self, tag):
                if tag == "div" and self.in_result:
                    if self.current_title and self.current_snippet:
                        self.results.append({
                            "title": self.current_title,
                            "snippet": self.current_snippet,
                            "url": self.current_url
                        })
                    self.in_result = False
                    self.current_title = ""
                    self.current_snippet = ""
                    self.current_url = ""
                elif tag == "a" and self.in_title:
                    self.in_title = False
                elif tag == "a" and self.in_snippet:
                    self.in_snippet = False

            def handle_data(self, data):
                if self.in_title:
                    self.current_title += data
                elif self.in_snippet:
                    self.current_snippet += data

        parser = DuckDuckGoParser()
        parser.feed(html)

        results = []
        for i, r in enumerate(parser.results[:num_results], 1):
            results.append(f"[{i}] {r['title']}\n{r['snippet']}\n来源: {r['url']}\n")

        return "\n".join(results) if results else "未找到相关搜索结果"


async def test_search():
    """测试搜索功能"""
    search_tool = SearchTool()

    print("=" * 60)
    print("测试搜索功能")
    print("=" * 60)

    # 检查可用的搜索方式
    if search_tool.serpapi_key:
        print("使用 SerpAPI 进行搜索")
    elif search_tool.google_api_key and search_tool.google_cx:
        print("使用 Google Custom Search API 进行搜索")
    else:
        print("使用 DuckDuckGo 进行搜索（无需 API key）")

    # 测试搜索
    query = "OpenClaw AI 项目 2026"
    print(f"\n搜索查询: {query}")
    print("-" * 60)

    result = await search_tool.search(query, num_results=3)
    print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_search())
