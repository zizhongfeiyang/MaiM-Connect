#!/usr/bin/env python
# coding: utf-8

import asyncio
import sys
import os
import socket
import requests

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.do_tool.tool_can_use import get_tool_instance
from src.common.logger import get_module_logger
from dotenv import load_dotenv
from src.plugins.web_search import WebSearcher
from src.do_tool.tool_can_use.web_search_tool import WebSearchTool

logger = get_module_logger("test_web_search")

def check_searx_service(url):
    """检查SearXNG服务是否可用
    
    :param url: SearXNG服务URL
    :return: 服务是否可用
    """
    try:
        # 解析URL获取主机和端口
        url_parts = url.split('://')
        if len(url_parts) < 2:
            logger.warning(f"URL格式不正确: {url}")
            return False
            
        host_port = url_parts[1].split('/')
        host_parts = host_port[0].split(':')
        
        host = host_parts[0]
        port = int(host_parts[1]) if len(host_parts) > 1 else 80
        
        logger.info(f"检查SearXNG服务可用性: {host}:{port}")
        
        # 创建socket连接测试
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)  # 设置超时时间为2秒
        
        result = s.connect_ex((host, port))
        s.close()
        
        if result == 0:
            logger.info(f"SearXNG服务端口可访问: {host}:{port}")
            
            # 测试HTTP连接
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    logger.info("SearXNG服务HTTP响应正常")
                    return True
                else:
                    logger.warning(f"SearXNG服务HTTP响应异常，状态码: {response.status_code}")
                    return False
            except Exception as e:
                logger.warning(f"SearXNG服务HTTP连接失败: {str(e)}")
                return False
        else:
            logger.warning(f"SearXNG服务端口不可访问: {host}:{port}，错误代码: {result}")
            return False
            
    except Exception as e:
        logger.error(f"检查SearXNG服务时出错: {str(e)}")
        return False

async def test_query(searcher, query):
    """测试特定查询词的搜索结果
    
    :param searcher: WebSearcher实例
    :param query: 要测试的查询词
    """
    print(f"\n------- 测试查询词: '{query}' -------")
    try:
        # 执行搜索
        results = await searcher.search_web(query)
        
        # 打印结果
        if results and len(results) > 0:
            print(f"找到 {len(results)} 个搜索结果")
            print(f"第一个结果: {results[0]['title']}")
            return True
        else:
            print("没有找到结果")
            return False
    except Exception as e:
        print(f"搜索出错: {str(e)}")
        return False

async def test_query_with_tool(search_tool, query):
    """使用优化后的WebSearchTool测试查询
    
    :param search_tool: WebSearchTool实例
    :param query: 要测试的查询词
    """
    print(f"\n------- 使用优化工具测试查询词: '{query}' -------")
    try:
        # 执行搜索
        result = await search_tool.execute({"query": query})
        
        # 打印结果
        print(result["content"])
        
        # 判断是否成功找到结果
        return "抱歉，未能找到" not in result["content"]
    except Exception as e:
        print(f"工具搜索出错: {str(e)}")
        return False

async def main():
    """测试网络搜索工具"""
    try:
        # 从最新环境变量获取配置
        load_dotenv(override=True)
        
        # 从环境变量获取搜索引擎URL
        searxng_url = os.getenv("SEARXNG_URL")
        if not searxng_url:
            logger.warning("环境变量中未找到SEARXNG_URL，将使用默认值")
            searxng_url = "http://localhost:32769"
            
        logger.info(f"使用SearXNG URL: {searxng_url}")
        
        # 检查SearXNG服务是否可用
        if not check_searx_service(searxng_url):
            logger.error(f"SearXNG服务不可用: {searxng_url}")
            print(f"\n错误: SearXNG服务不可用，请检查服务是否在 {searxng_url} 上运行")
            return
        
        # 创建WebSearcher实例
        searcher = WebSearcher(searxng_url=searxng_url)
        
        # 创建优化后的WebSearchTool实例
        search_tool = WebSearchTool()
        search_tool.searcher = WebSearcher(searxng_url=searxng_url)
        
        # 测试不同查询词
        test_queries = [
            "weather",                       # 简单常见词
            "beijing weather",               # 地点+简单词
            "python programming",            # 编程相关
            "latest technology news",        # 较复杂
            "artificial intelligence technology", # 技术相关
            "latest ai technology news",     # 更复杂组合
            "python for data science",       # 英文查询
            "today headlines",               # 时效性查询
            "ai development trends 2025"     # 未来相关查询
        ]
        
        # 先执行原始搜索测试
        results_original = {}
        print(f"\n==== 开始测试不同查询词在SearXNG服务({searxng_url})上的原始性能 ====\n")
        
        for query in test_queries:
            success = await test_query(searcher, query)
            results_original[query] = success
            
        # 执行优化工具搜索测试
        results_optimized = {}
        print(f"\n==== 开始测试使用优化后的工具在SearXNG服务({searxng_url})上的性能 ====\n")
        
        for query in test_queries:
            success = await test_query_with_tool(search_tool, query)
            results_optimized[query] = success
            
        # 总结结果：原始方法
        print("\n==== 原始搜索方法测试结果汇总 ====")
        successful_original = [q for q, success in results_original.items() if success]
        failed_original = [q for q, success in results_original.items() if not success]
        
        print(f"\n成功的查询({len(successful_original)}/{len(test_queries)}):")
        for query in successful_original:
            print(f"✓ '{query}'")
            
        print(f"\n失败的查询({len(failed_original)}/{len(test_queries)}):")
        for query in failed_original:
            print(f"✗ '{query}'")
        
        # 总结结果：优化方法
        print("\n==== 优化搜索方法测试结果汇总 ====")
        successful_optimized = [q for q, success in results_optimized.items() if success]
        failed_optimized = [q for q, success in results_optimized.items() if not success]
        
        print(f"\n成功的查询({len(successful_optimized)}/{len(test_queries)}):")
        for query in successful_optimized:
            print(f"✓ '{query}'")
            
        print(f"\n失败的查询({len(failed_optimized)}/{len(test_queries)}):")
        for query in failed_optimized:
            print(f"✗ '{query}'")
            
        # 对比改进效果
        improved_count = len(successful_optimized) - len(successful_original)
        print(f"\n==== 优化效果 ====")
        print(f"原始方法成功率: {len(successful_original)}/{len(test_queries)} ({len(successful_original)*100/len(test_queries):.1f}%)")
        print(f"优化方法成功率: {len(successful_optimized)}/{len(test_queries)} ({len(successful_optimized)*100/len(test_queries):.1f}%)")
        print(f"改进数量: {improved_count} 个查询")
        
        # 列出改进的查询
        if improved_count > 0:
            improved_queries = [q for q in test_queries if q in successful_optimized and q not in successful_original]
            print(f"\n成功改进的查询:")
            for query in improved_queries:
                print(f"✓ '{query}'")
                
    except Exception as e:
        logger.error(f"测试过程中出现错误: {str(e)}")

if __name__ == "__main__":
    """运行测试脚本"""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main()) 