import time
import functools
import asyncio
from src.common.logger import get_module_logger

perf_logger = get_module_logger("performance")

def log_performance(func):
    """记录函数执行时间的装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        perf_logger.info(f"[START] {func.__module__}.{func.__name__}")
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            perf_logger.info(f"[END] {func.__module__}.{func.__name__} - 耗时: {elapsed:.3f}秒")
            if elapsed > 1.0:  # 标记耗时超过1秒的操作
                perf_logger.warning(f"[SLOW] {func.__module__}.{func.__name__} - 耗时: {elapsed:.3f}秒")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            perf_logger.error(f"[ERROR] {func.__module__}.{func.__name__} - 耗时: {elapsed:.3f}秒 - 错误: {str(e)}")
            raise
    return wrapper

def log_async_performance(func):
    """记录异步函数执行时间的装饰器"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        perf_logger.info(f"[START] {func.__module__}.{func.__name__}")
        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start_time
            perf_logger.info(f"[END] {func.__module__}.{func.__name__} - 耗时: {elapsed:.3f}秒")
            if elapsed > 1.0:  # 标记耗时超过1秒的操作
                perf_logger.warning(f"[SLOW] {func.__module__}.{func.__name__} - 耗时: {elapsed:.3f}秒")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            perf_logger.error(f"[ERROR] {func.__module__}.{func.__name__} - 耗时: {elapsed:.3f}秒 - 错误: {str(e)}")
            raise
    return wrapper

class PerformanceTimer:
    """用于记录代码块执行时间的上下文管理器"""
    def __init__(self, name, warning_threshold=1.0):
        self.name = name
        self.warning_threshold = warning_threshold
        self.start_time = None
        self.sections = {}
        self.current_section = None
        self.section_start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        perf_logger.info(f"[TIMER-START] {self.name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        if exc_type:
            perf_logger.error(f"[TIMER-ERROR] {self.name} - 耗时: {elapsed:.3f}秒 - 错误: {str(exc_val)}")
        else:
            perf_logger.info(f"[TIMER-END] {self.name} - 总耗时: {elapsed:.3f}秒")
            if elapsed > self.warning_threshold:
                perf_logger.warning(f"[TIMER-SLOW] {self.name} - 总耗时: {elapsed:.3f}秒")
        
        # 打印各部分的执行时间
        if self.sections:
            section_log = "各部分耗时:\n"
            for section, time_elapsed in self.sections.items():
                section_log += f"  - {section}: {time_elapsed:.3f}秒\n"
            perf_logger.info(section_log)
    
    def start_section(self, section_name):
        """开始记录代码块的一个部分"""
        if self.current_section:
            self.end_section()
        
        self.current_section = section_name
        self.section_start_time = time.time()
        perf_logger.debug(f"[SECTION-START] {self.name} - {section_name}")
    
    def end_section(self):
        """结束记录代码块的一个部分"""
        if not self.current_section:
            return
        
        elapsed = time.time() - self.section_start_time
        self.sections[self.current_section] = elapsed
        perf_logger.debug(f"[SECTION-END] {self.name} - {self.current_section} - 耗时: {elapsed:.3f}秒")
        self.current_section = None 