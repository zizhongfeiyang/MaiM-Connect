import aiohttp
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Optional, Union
from urllib.parse import urljoin
import os
from dotenv import load_dotenv
from src.common.logger import get_module_logger
import asyncio
import json
import socket
from src.common.utils import log_async_performance, PerformanceTimer

logger = get_module_logger("web_search")

class WebSearcher:
    def __init__(self, searxng_url: str = None, num_results: int = None):
        """
        初始化网络搜索器
        :param searxng_url: SearXNG实例的URL，默认从环境变量获取
        :param num_results: 返回的结果数量，默认从环境变量获取
        """
        # 每次初始化时重新加载环境变量，确保获取最新配置
        load_dotenv(override=True)
        
        # 从环境变量获取配置
        self.searxng_url = searxng_url or os.getenv("SEARXNG_URL", "http://localhost:32769")
        self.searxng_url = self.searxng_url.rstrip('/')  # 移除末尾的斜杠
        self.num_results = num_results or int(os.getenv("SEARXNG_RESULTS_COUNT", "10"))
        self.timeout = int(os.getenv("SEARXNG_TIMEOUT", "5"))  # 缩短默认超时时间从10秒到5秒
        self.max_retries = int(os.getenv("SEARXNG_MAX_RETRIES", "2"))  # 减少重试次数
        self.engines = os.getenv("SEARXNG_ENGINES", "google,bing,duckduckgo")
        self.search_endpoint = f"{self.searxng_url}/search"
        self.max_url_fetch = 3  # 最多获取前3个结果的详细内容
        
        # 设置默认请求头
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": self.searxng_url,
            "Referer": self.searxng_url + "/"
        }
        
        # 添加认证令牌（如果有）
        auth_token = os.getenv("SEARXNG_AUTH_TOKEN")
        if auth_token and auth_token.strip():
            self.headers["Authorization"] = auth_token
        
        logger.info(f"初始化网络搜索器，搜索引擎URL: {self.searxng_url}")
        
        # 尝试检查SearXNG服务是否可访问
        self._check_service_availability()

    def _check_service_availability(self):
        """检查SearXNG服务是否可访问"""
        try:
            # 从URL中提取主机和端口
            url_parts = self.searxng_url.split('://')
            if len(url_parts) < 2:
                logger.warning(f"URL格式不正确: {self.searxng_url}")
                return
                
            host_port = url_parts[1].split('/')
            host_parts = host_port[0].split(':')
            
            host = host_parts[0]
            port = int(host_parts[1]) if len(host_parts) > 1 else 80
            
            logger.debug(f"检查服务可用性: {host}:{port}")
            
            # 创建socket连接测试
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)  # 设置超时时间为2秒
            
            result = s.connect_ex((host, port))
            s.close()
            
            if result == 0:
                logger.info(f"SearXNG服务端口可访问: {host}:{port}")
            else:
                logger.warning(f"SearXNG服务端口不可访问: {host}:{port}，错误代码: {result}")
                
        except Exception as e:
            logger.warning(f"检查服务可用性时出错: {str(e)}")

    async def test_connection(self) -> bool:
        """
        测试到SearXNG服务的连接
        :return: 连接是否成功
        """
        try:
            logger.info(f"测试连接到 {self.searxng_url}")
            
            # 尝试连接到SearXNG首页
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=5)  # 5秒超时
                async with session.get(
                    self.searxng_url,
                    headers=self.headers,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        logger.info(f"成功连接到SearXNG服务，状态码: {response.status}")
                        html = await response.text()
                        logger.debug(f"首页响应长度: {len(html)}")
                        
                        # 检查是否含有搜索表单
                        soup = BeautifulSoup(html, 'html.parser')
                        search_form = soup.find('form')
                        if search_form:
                            logger.debug("找到搜索表单，服务正常")
                            return True
                        else:
                            logger.warning("未找到搜索表单，响应可能不是SearXNG页面")
                            return False
                    else:
                        logger.warning(f"连接到SearXNG服务失败，状态码: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"测试连接失败: {str(e)}")
            return False

    @log_async_performance
    async def search_web(self, query: str, time_range: str = "month") -> List[Dict]:
        """
        使用SearXNG进行网络搜索
        :param query: 搜索查询
        :param time_range: 搜索时间范围，可选值: "day", "week", "month", "year"，默认为"month"
        :return: 搜索结果列表
        """
        if not query or not query.strip():
            logger.error("搜索查询不能为空")
            return []
        
        # 添加总体超时控制
        try:
            # 设置15秒总超时，确保即使出问题也能正常返回
            return await asyncio.wait_for(
                self._search_web_impl(query, time_range), 
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"搜索总体超时: {query}")
            return []  # 返回空结果以避免无限等待
            
    async def _search_web_impl(self, query: str, time_range: str = "month") -> List[Dict]:
        """实际执行搜索的实现方法"""
        with PerformanceTimer(f"search_web-{query[:20]}") as timer:
            # 先测试连接
            timer.start_section("test_connection")
            connection_ok = await self.test_connection()
            timer.end_section()
            
            if not connection_ok:
                logger.error("SearXNG服务连接测试失败，无法执行搜索")
                return []
                
            try:
                query = query.strip()
                logger.info(f"执行网络搜索: {query}，时间范围: {time_range}")
                
                # 验证时间范围参数
                valid_time_ranges = ["day", "week", "month", "year", ""]
                if time_range not in valid_time_ranges:
                    logger.warning(f"无效的时间范围: {time_range}，使用默认值'month'")
                    time_range = "month"
                
                # 使用实例的engines属性
                logger.debug(f"使用搜索引擎: {self.engines}")
                
                # 构建搜索参数 - 尝试两种格式：HTML和JSON
                formats = ["html", "json"]
                html = None
                results_data = None
                
                # 尝试不同的格式
                timer.start_section("search_request")
                for fmt in formats:
                    try:
                        # 构建搜索参数
                        data = {
                            "q": query,
                            "category_general": "1",
                            "time_range": time_range,
                            "language": "zh-CN",
                            "engines": self.engines,
                            "format": fmt
                        }
                        
                        logger.debug(f"尝试使用 {fmt} 格式搜索")
                        
                        # 使用重试机制发送请求
                        for retry in range(self.max_retries):
                            try:
                                async with aiohttp.ClientSession() as session:
                                    logger.debug(f"发送GET请求到 {self.search_endpoint}，参数: {data}")
                                    timeout = aiohttp.ClientTimeout(total=self.timeout)
                                    async with session.get(
                                        self.search_endpoint,
                                        params=data,
                                        headers=self.headers,
                                        timeout=timeout
                                    ) as response:
                                        response.raise_for_status()
                                        logger.debug(f"收到响应状态码: {response.status}")
                                        
                                        if fmt == "json":
                                            try:
                                                results_data = await response.json()
                                                logger.debug(f"成功获取JSON响应: {str(results_data)[:200]}...")
                                                break  # 成功获取JSON数据
                                            except json.JSONDecodeError:
                                                logger.warning("JSON解析失败，继续尝试其他格式")
                                                results_data = None
                                                # 继续尝试其他格式
                                                break
                                        else:  # html
                                            html = await response.text()
                                            logger.debug(f"收到响应HTML长度: {len(html)}")
                                            # 打印HTML的开头部分，帮助诊断
                                            if len(html) > 0:
                                                logger.debug(f"HTML响应开头: {html[:200]}...")
                                            break  # 获取到HTML响应
                            except Exception as e:
                                if retry == self.max_retries - 1:  # 最后一次重试
                                    logger.warning(f"{fmt}格式请求失败: {e}")
                                    break  # 尝试下一种格式
                                logger.warning(f"搜索请求失败，正在重试 ({retry + 1}/{self.max_retries}): {e}")
                                await asyncio.sleep(2 ** retry)  # 指数退避
                    
                        # 检查是否成功获取到响应
                        if fmt == "json" and results_data:
                            # 处理JSON响应
                            timer.end_section()
                            timer.start_section("process_json_results")
                            result = self._process_json_results(results_data)
                            timer.end_section()
                            return result
                        elif fmt == "html" and html:
                            # 已获取HTML响应，退出循环
                            break
                            
                    except Exception as e:
                        logger.warning(f"{fmt}格式处理失败: {e}")
                        continue  # 尝试下一种格式
                timer.end_section()
                
                # 如果无法获取任何格式的有效响应，返回空列表
                if not html and not results_data:
                    logger.error("所有格式的搜索请求均失败")
                    return []
                
                # 处理HTML响应（如果JSON处理失败）
                if html:
                    timer.start_section("process_html_results")
                    # 解析HTML响应
                    soup = BeautifulSoup(html, 'html.parser')
                    results = []
                    
                    # 查找所有搜索结果
                    result_articles = soup.select('html > body > main > div > div:nth-child(2) > article')
                    logger.debug(f"CSS选择器1找到 {len(result_articles)} 个结果")
                    
                    if not result_articles:
                        # 尝试其他可能的CSS选择器
                        result_articles = soup.select('article.result')
                        logger.debug(f"CSS选择器2找到 {len(result_articles)} 个结果")
                        
                    if not result_articles:
                        # 再次尝试其他选择器
                        result_articles = soup.select('.result')
                        logger.debug(f"CSS选择器3找到 {len(result_articles)} 个结果")
                    
                    if not result_articles:
                        # 尝试更通用的选择器
                        result_articles = soup.select('article')
                        logger.debug(f"CSS选择器4 (article) 找到 {len(result_articles)} 个结果")
                        
                        # 如果仍然找不到结果，尝试分析页面结构
                        if not result_articles:
                            logger.debug("无法找到搜索结果，分析页面结构...")
                            main_tags = soup.find_all('main')
                            logger.debug(f"找到 {len(main_tags)} 个 main 标签")
                            
                            div_tags = soup.find_all('div')
                            logger.debug(f"找到 {len(div_tags)} 个 div 标签")
                            
                            # 尝试找出页面结构问题
                            form_tags = soup.find_all('form')
                            logger.debug(f"找到 {len(form_tags)} 个 form 标签，可能是搜索页而非结果页")
                    
                    logger.info(f"找到 {len(result_articles)} 个搜索结果")
                    
                    # 如果找到结果，记录第一个结果的结构，帮助调试
                    if result_articles and len(result_articles) > 0:
                        logger.debug(f"第一个结果HTML: {result_articles[0]}")
                    
                    timer.start_section("process_results")
                    
                    # 处理前max_url_fetch个结果的基本信息
                    limited_results = result_articles[:min(self.num_results, len(result_articles))]
                    basic_results = []
                    urls_to_fetch = []
                    
                    # 先提取基本信息
                    for article in limited_results:
                        try:
                            # 提取标题
                            title_elem = article.find('h3')
                            title = title_elem.get_text().strip() if title_elem else "无标题"
                            
                            # 提取链接
                            url_elem = article.find('a')
                            url = url_elem['href'] if url_elem else ""
                            
                            # 提取日期（如果可用）
                            date_elem = article.select_one('.published')
                            published_date = date_elem.get_text().strip() if date_elem else ""
                            
                            # 提取内容
                            content_elem = article.find('p')
                            content = content_elem.get_text().strip() if content_elem else ""
                            
                            logger.debug(f"解析结果: 标题='{title}', URL='{url}', 日期='{published_date}', 内容长度={len(content)}")
                            
                            result_item = {
                                "title": title,
                                "url": url,
                                "content": content,
                                "published_date": published_date
                            }
                            
                            basic_results.append(result_item)
                            
                            # 仅收集前max_url_fetch个有效URL进行内容获取
                            if url and len(urls_to_fetch) < self.max_url_fetch:
                                urls_to_fetch.append((len(basic_results)-1, url))
                                
                        except Exception as e:
                            logger.error(f"处理搜索结果失败: {str(e)}")
                            continue
                    
                    # 并行获取URL内容
                    timer.start_section("fetch_url_contents")
                    if urls_to_fetch:
                        tasks = []
                        for idx, url in urls_to_fetch:
                            tasks.append(self._fetch_and_update_content(idx, url, basic_results))
                        
                        # 并行执行所有获取任务
                        await asyncio.gather(*tasks)
                    timer.end_section()
                    
                    timer.end_section()  # end process_results
                    timer.end_section()  # end process_html_results
                    
                    return basic_results
                
                # 如果所有处理都失败，返回空列表
                return []
                
            except Exception as e:
                logger.error(f"网络搜索失败: {str(e)}")
                return []
    
    async def _fetch_and_update_content(self, idx: int, url: str, results: List[Dict]) -> None:
        """并行获取URL内容并更新结果列表
        
        Args:
            idx: 结果列表中的索引
            url: 要获取内容的URL
            results: 要更新的结果列表
        """
        try:
            content = await self.get_url_content(url)
            if content and idx < len(results):
                # 更新对应结果的内容
                original_content = results[idx]['content']
                if content:
                    results[idx]['content'] = f"{original_content}\n\n详细内容：\n{content}"
        except Exception as e:
            logger.error(f"获取URL内容失败: {url}, 错误: {str(e)}")

    async def get_url_content(self, url: str) -> str:
        """
        获取URL的内容
        :param url: 要访问的URL
        :return: 页面内容的文本
        """
        if not url or not url.startswith(('http://', 'https://')):
            logger.warning(f"无效URL: {url}")
            return ""
            
        try:
            # 创建自定义的超时设置 - 减少超时时间
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 添加超时处理和错误重试
                for retry in range(1):  # 减少重试次数到1次
                    try:
                        async with session.get(url, headers=self.headers) as response:
                            response.raise_for_status()
                            html = await response.text()
                            break
                    except asyncio.TimeoutError:
                        logger.warning(f"获取URL内容超时: {url}")
                        return ""
                    except Exception as e:
                        logger.debug(f"获取URL内容失败: {url}, 错误: {e}")
                        return ""
            
            # 解析HTML
            soup = BeautifulSoup(html, 'html.parser')
            
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 获取文本
            text = soup.get_text()
            
            # 清理文本
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text[:1000]  # 限制返回的文本长度，从2000缩短到1000字符
        except Exception as e:
            logger.error(f"获取URL内容失败: {str(e)}, URL: {url}")
            return ""

    def _process_json_results(self, json_data: Dict) -> List[Dict]:
        """处理JSON格式的搜索结果
        
        :param json_data: SearXNG返回的JSON数据
        :return: 处理后的结果列表
        """
        results = []
        try:
            if not isinstance(json_data, dict):
                logger.warning(f"JSON数据格式不正确: {type(json_data)}")
                return []
                
            # 获取结果列表
            result_items = json_data.get("results", [])
            if not result_items:
                logger.warning("JSON结果为空")
                return []
                
            logger.info(f"从JSON中找到 {len(result_items)} 个搜索结果")
            
            # 处理每个结果
            for item in result_items[:self.num_results]:
                try:
                    title = item.get("title", "无标题")
                    url = item.get("url", "")
                    content = item.get("content", "")
                    published_date = item.get("publishedDate", "")
                    
                    # 处理结果
                    results.append({
                        "title": title,
                        "url": url,
                        "content": content,
                        "published_date": published_date
                    })
                except Exception as e:
                    logger.error(f"处理JSON搜索结果项失败: {e}")
                    continue
                
            return results
        except Exception as e:
            logger.error(f"处理JSON搜索结果失败: {e}")
            return []

    def format_results(self, results: List[Dict]) -> str:
        """
        格式化搜索结果
        :param results: 搜索结果列表
        :return: 格式化后的字符串
        """
        if not results:
            return "抱歉，没有找到相关结果。"
        
        formatted = "🔍 搜索结果：\n\n"
        for i, result in enumerate(results, 1):
            formatted += f"📌 结果 {i}:\n"
            formatted += f"   📝 标题: {result['title']}\n"
            formatted += f"   🔗 链接: {result['url']}\n"
            if result.get('published_date'):
                formatted += f"   📅 发布日期: {result['published_date']}\n"
            
            # 处理内容，确保格式清晰
            content = result['content'].strip()
            if len(content) > 500:
                content = content[:500] + "..."
            
            # 按段落分割内容
            paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
            formatted += "   📄 内容:\n"
            for para in paragraphs:
                formatted += f"      {para}\n"
            
            formatted += "\n"  # 结果之间的分隔空行
        
        return formatted

    def update_config(self):
        """
        更新搜索器配置，重新从环境变量读取
        用于在运行时更新配置而不需要重新创建实例
        """
        # 重新加载环境变量
        load_dotenv(override=True)
        
        # 更新配置
        self.searxng_url = os.getenv("SEARXNG_URL", "http://localhost:32769")
        self.searxng_url = self.searxng_url.rstrip('/')  # 移除末尾的斜杠
        self.num_results = int(os.getenv("SEARXNG_RESULTS_COUNT", "10"))
        self.timeout = int(os.getenv("SEARXNG_TIMEOUT", "5"))  # 缩短默认超时时间从10秒到5秒
        self.max_retries = int(os.getenv("SEARXNG_MAX_RETRIES", "2"))  # 减少重试次数
        self.engines = os.getenv("SEARXNG_ENGINES", "google,bing,duckduckgo")
        self.search_endpoint = f"{self.searxng_url}/search"
        self.max_url_fetch = 3  # 最多获取前3个结果的详细内容
        
        # 更新认证令牌
        auth_token = os.getenv("SEARXNG_AUTH_TOKEN")
        if "Authorization" in self.headers and not (auth_token and auth_token.strip()):
            # 之前有令牌但现在没有，移除
            del self.headers["Authorization"]
        elif auth_token and auth_token.strip():
            # 更新或添加令牌
            self.headers["Authorization"] = auth_token
            
        # 更新头部引用链接
        self.headers["Origin"] = self.searxng_url
        self.headers["Referer"] = self.searxng_url + "/"
        
        logger.info(f"更新网络搜索器配置，搜索引擎URL: {self.searxng_url}")

# 使用示例
if __name__ == "__main__":
    # 从环境变量获取最新配置创建WebSearcher实例
    searcher = WebSearcher()
    query = "美国新闻"
    
    import asyncio
    
    async def test_search():
        # 先测试连接
        connection_ok = await searcher.test_connection()
        if not connection_ok:
            print("无法连接到SearXNG服务，请检查配置和服务状态")
            return
            
        print(f"正在搜索: {query}")
        results = await searcher.search_web(query)
        print(searcher.format_results(results))
    
    # 运行测试
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_search()) 