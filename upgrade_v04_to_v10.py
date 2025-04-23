#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MaiM v62_lianwang 一键安装工具
此脚本用于快速安装MaiM v62_lianwang联网工具版
"""

import os
import sys
import shutil
import subprocess
import datetime
import json
import re
import time
import zipfile
import platform
import tempfile
from pathlib import Path
import urllib.request
import configparser
import gc  # 添加垃圾回收
import stat  # 添加文件权限处理
import fnmatch

# 定义颜色代码，用于美化输出
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# 清理控制台
def clear_screen():
    if platform.system() == "Windows":
        os.system('cls')
    else:
        os.system('clear')

# 美化输出函数
def print_step(step, message):
    print(f"{Colors.BLUE}[步骤 {step}]{Colors.ENDC} {Colors.BOLD}{message}{Colors.ENDC}")

def print_info(message):
    print(f"{Colors.GREEN}[信息]{Colors.ENDC} {message}")

def print_warning(message):
    print(f"{Colors.WARNING}[警告]{Colors.ENDC} {message}")
    
def print_error(message):
    print(f"{Colors.FAIL}[错误]{Colors.ENDC} {message}")

def print_header(message):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 20} {message} {'=' * 20}{Colors.ENDC}\n")

# 打印欢迎信息
def print_welcome():
    clear_screen()
    print_header("MaiM v62_lianwang 一键安装工具")
    print("""
此工具将帮助您快速安装MaiM v62_lianwang联网工具版。

主要功能特性：
- 增强联网能力和知识获取系统
- 全新搜索引擎集成与知识库管理
- 工具系统重构与增强
- 优化部署与配置流程
    """)
    input("\n按Enter键继续...")

# 检测操作系统类型
def get_os_type():
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Linux":
        return "linux"
    elif system == "Darwin":
        return "macos"
    else:
        return "unknown"

# 检查Python版本
def check_python_version():
    print_step(1, "检查Python版本")
    
    version_info = sys.version_info
    if version_info.major >= 3 and version_info.minor >= 8:
        print_info(f"Python版本检查通过: {sys.version}")
        return True
    else:
        print_error(f"Python版本过低: {sys.version}，需要Python 3.8+")
        return False

# 自定义文件删除函数，处理只读文件
def remove_readonly(func, path, _):
    """处理只读文件的自定义错误处理函数"""
    os.chmod(path, stat.S_IWRITE)
    func(path)

# 安全删除目录函数
def safe_rmtree(path):
    """安全删除目录，处理文件被锁定或权限问题"""
    if not os.path.exists(path):
        return
    
    try:
        # 尝试正常删除
        shutil.rmtree(path)
    except Exception as e:
        print_warning(f"标准删除失败，尝试强制删除: {e}")
        try:
            # Windows特定处理
            if platform.system() == "Windows":
                # 尝试使用系统命令删除
                subprocess.run(f'rd /s /q "{path}"', shell=True, check=False)
                if os.path.exists(path):
                    # 尝试使用错误处理函数进行递归删除
                    shutil.rmtree(path, onerror=remove_readonly)
            else:
                # Linux/macOS系统
                subprocess.run(f'rm -rf "{path}"', shell=True, check=False)
        except Exception as e2:
            print_error(f"无法删除目录 {path}: {e2}")
            print_info("请在安装完成后手动删除该目录")

# 选择安装目录
def choose_install_dir():
    print_step(2, "选择安装目录")
    
    # 默认安装目录
    default_dir = "MaiM（联网工具）v62_lianwang"
    
    # 询问用户安装目录
    user_dir = input(f"请输入安装目录（直接回车使用默认: {default_dir}）: ")
    install_dir = user_dir.strip() if user_dir.strip() else default_dir
    
    # 检查目录是否已存在
    if os.path.exists(install_dir):
        print_warning(f"目录已存在: {install_dir}")
        overwrite = input("是否覆盖已存在的目录? (y/n): ")
        if overwrite.lower() != 'y':
            print_error("安装已取消")
            return None
        
        # 删除已存在的目录
        print_info(f"正在删除已存在的目录: {install_dir}")
        safe_rmtree(install_dir)
    
    # 创建安装目录
    try:
        os.makedirs(install_dir, exist_ok=True)
        print_info(f"安装目录设置为: {os.path.abspath(install_dir)}")
        return install_dir
    except Exception as e:
        print_error(f"无法创建安装目录: {e}")
        return None

# 下载或准备v62_lianwang版本文件
def prepare_v10_files(install_dir):
    print_step(3, "准备MaiM v62_lianwang文件")
    
    # 尝试查找各种可能的本地版本目录名
    source_finder_dirs = [
        "./MaiM（联网工具）v62_lianwang",
        "MaiM（联网工具）v62_lianwang",
        "../MaiM（联网工具）v62_lianwang",
        os.path.join(os.getcwd(), "MaiM（联网工具）v62_lianwang"),
        os.path.abspath("MaiM（联网工具）v62_lianwang"),
        "MaiM(联网工具)v62_lianwang",  # 可能的变体
        "MaiM-v62_lianwang",
        "MaiM_v62_lianwang"
    ]
    
    # 检查上述目录是否存在，但跳过与安装目录相同的路径
    source_dir = None
    for dir_path in source_finder_dirs:
        try:
            # 如果是安装目录本身，则跳过
            if os.path.abspath(dir_path) == os.path.abspath(install_dir):
                continue
                
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                source_dir = dir_path
                print_info(f"找到本地安装文件: {source_dir}")
                break
        except Exception as e:
            print_warning(f"检查路径时出错: {dir_path}, 错误: {e}")
    
    # 如果找到本地版本文件
    if source_dir:
        try:
            print_info(f"开始复制文件: 从 {source_dir} 到 {install_dir}")
            # 复制文件，排除不需要的文件
            for root, dirs, files in os.walk(source_dir):
                # 跳过不需要的目录
                dirs[:] = [d for d in dirs if d not in ['__pycache__', 'temp', 'tmp', '.git', 'venv', '.venv', 'node_modules']]
                
                # 计算相对路径
                rel_path = os.path.relpath(root, source_dir)
                if rel_path == '.':
                    rel_path = ''
                
                # 创建目标目录
                target_dir = os.path.join(install_dir, rel_path)
                os.makedirs(target_dir, exist_ok=True)
                
                # 复制文件
                for file in files:
                    if file.endswith(('.pyc', '.pyo', '.pyd', '.log', '.tmp')):
                        continue  # 跳过不需要的文件类型
                    
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    try:
                        shutil.copy2(src_file, dst_file)
                    except Exception as e:
                        print_warning(f"无法复制文件 {src_file}: {e}")
            
            print_info(f"v62_lianwang文件准备完成: {os.path.abspath(install_dir)}")
            return install_dir
        except Exception as e:
            print_error(f"复制文件时出错: {e}")
            print_info("将尝试其他方法...")
    
    # 如果本地没找到或复制失败，尝试手动输入路径或下载
    print_info("未找到本地安装文件或复制失败，请选择下一步操作")
    source_option = input("请选择操作 [1:指定源文件路径, 2:下载安装包, q:退出]: ")
    
    if source_option.lower() == 'q':
        return None
    elif source_option == '1':
        # 手动指定路径
        user_source_dir = input("请输入MaiM v62_lianwang的完整路径: ")
        if not user_source_dir:
            print_error("未提供有效路径")
            return None
        
        if os.path.exists(user_source_dir) and os.path.isdir(user_source_dir):
            try:
                print_info(f"开始复制文件: 从 {user_source_dir} 到 {install_dir}")
                # 复制文件，排除不需要的文件
                for root, dirs, files in os.walk(user_source_dir):
                    # 跳过不需要的目录
                    dirs[:] = [d for d in dirs if d not in ['__pycache__', 'temp', 'tmp', '.git', 'venv', '.venv', 'node_modules']]
                    
                    # 计算相对路径
                    rel_path = os.path.relpath(root, user_source_dir)
                    if rel_path == '.':
                        rel_path = ''
                    
                    # 创建目标目录
                    target_dir = os.path.join(install_dir, rel_path)
                    os.makedirs(target_dir, exist_ok=True)
                    
                    # 复制文件
                    for file in files:
                        if file.endswith(('.pyc', '.pyo', '.pyd', '.log', '.tmp')):
                            continue  # 跳过不需要的文件类型
                        
                        src_file = os.path.join(root, file)
                        dst_file = os.path.join(target_dir, file)
                        try:
                            shutil.copy2(src_file, dst_file)
                        except Exception as e:
                            print_warning(f"无法复制文件 {src_file}: {e}")
                
                print_info(f"v62_lianwang文件准备完成: {os.path.abspath(install_dir)}")
                return install_dir
            except Exception as e:
                print_error(f"复制文件时出错: {e}")
                return None
        else:
            print_error(f"指定的路径不存在或不是目录: {user_source_dir}")
            return None
    elif source_option == '2':
        # 从网络下载
        download_url = input("请输入MaiM v62_lianwang的下载链接(ZIP格式): ")
        if not download_url:
            print_error("未提供下载链接")
            return None
        
        try:
            # 创建临时文件
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            temp_zip.close()
            
            # 下载文件
            print_info(f"正在下载MaiM v62_lianwang...")
            urllib.request.urlretrieve(download_url, temp_zip.name)
            
            # 解压文件
            print_info(f"正在解压文件...")
            with zipfile.ZipFile(temp_zip.name, 'r') as zip_ref:
                zip_ref.extractall(install_dir)
            
            # 删除临时文件
            os.unlink(temp_zip.name)
            
            print_info(f"v62_lianwang文件准备完成: {os.path.abspath(install_dir)}")
            return install_dir
        except Exception as e:
            print_error(f"下载或解压失败: {e}")
            return None
    else:
        print_error("无效的选项")
        return None

# 安装依赖
def install_dependencies(install_dir):
    print_step(4, "安装必要依赖")
    
    requirements_file = os.path.join(install_dir, "MaiBot", "requirements.txt")
    
    if not os.path.exists(requirements_file):
        print_error(f"未找到依赖文件: {requirements_file}")
        return False
    
    try:
        print_info("安装Python依赖...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_file])
        
        # 安装新版本特有的依赖
        print_info("安装联网功能所需依赖...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp", "beautifulsoup4", "urllib3", "toml"])
        
        print_info("依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"依赖安装失败: {e}")
        return False

# 配置MaiBot
def configure_maibot(install_dir):
    print_step(5, "配置MaiBot")
    
    maibot_dir = os.path.join(install_dir, "MaiBot")
    
    if not os.path.exists(maibot_dir):
        print_error(f"MaiBot目录不存在: {maibot_dir}")
        return False
    
    # 配置文件路径
    env_file = os.path.join(maibot_dir, ".env")
    config_file = os.path.join(maibot_dir, "config.toml")
    template_file = os.path.join(maibot_dir, "template", "bot_config_template.toml")
    
    # 设置.env文件
    try:
        print_info("配置.env文件")
        
        # 检查是否有模板.env文件
        template_env = os.path.join(maibot_dir, "template", ".env.template")
        
        if os.path.exists(template_env):
            shutil.copy(template_env, env_file)
            print_info("从模板创建.env文件")
        else:
            # 创建基本的.env文件
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write("# MaiBot环境配置文件\n\n")
                f.write("# API密钥 (请替换为您的密钥)\n")
                f.write("OPENAI_API_KEY=your_openai_api_key_here\n")
                f.write("ANTHROPIC_API_KEY=your_anthropic_api_key_here\n\n")
                f.write("# 搜索引擎配置\n")
                f.write("SEARXNG_URL=http://localhost:32768\n")
                f.write("SEARCH_COOLDOWN_SECONDS=600\n")
            print_info("创建基本.env文件，请稍后配置API密钥")
        
        # 提示用户配置API密钥
        print_warning("请确保在安装完成后修改.env文件，添加您的API密钥")
    except Exception as e:
        print_error(f".env文件配置失败: {e}")
    
    # 设置config.toml文件
    try:
        print_info("配置config.toml文件")
        
        if os.path.exists(template_file):
            shutil.copy(template_file, config_file)
            print_info("从模板创建配置文件")
        else:
            print_warning("未找到配置模板，请在安装后手动配置")
    except Exception as e:
        print_error(f"配置文件设置失败: {e}")
    
    return True

# 安装Docker
def install_docker():
    print_step("附加", "Docker安装")
    
    # 检查Docker是否已安装
    try:
        subprocess.check_call(["docker", "--version"], stdout=subprocess.DEVNULL)
        print_info("检测到Docker已安装")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_warning("未检测到Docker")
    
    # 询问是否安装Docker
    install_choice = input("是否需要安装Docker? (y/n): ")
    if install_choice.lower() != 'y':
        print_info("已跳过Docker安装")
        return False
    
    # 根据操作系统选择安装方法
    if platform.system() == "Windows":
        print_info("Windows系统需要手动安装Docker Desktop")
        print_info("请访问: https://www.docker.com/products/docker-desktop/")
        print_info("下载并安装Docker Desktop后重新运行此脚本")
        return False
    elif platform.system() == "Linux":
        # 检测Linux发行版
        try:
            with open("/etc/os-release") as f:
                os_info = f.read()
            
            if "ubuntu" in os_info.lower() or "debian" in os_info.lower():
                print_info("正在安装Docker (Ubuntu/Debian)...")
                commands = [
                    "sudo apt update",
                    "sudo apt install -y apt-transport-https ca-certificates curl software-properties-common",
                    "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -",
                    "sudo add-apt-repository \"deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable\"",
                    "sudo apt update",
                    "sudo apt install -y docker-ce"
                ]
                for cmd in commands:
                    print_info(f"执行: {cmd}")
                    result = subprocess.run(cmd, shell=True, check=False)
                    if result.returncode != 0:
                        print_error(f"命令执行失败: {cmd}")
                        return False
                
                # 添加当前用户到docker组
                subprocess.run("sudo usermod -aG docker $USER", shell=True, check=False)
                print_info("Docker安装完成，请重新登录以应用组权限更改")
                return True
            
            elif "centos" in os_info.lower() or "rhel" in os_info.lower() or "fedora" in os_info.lower():
                print_info("正在安装Docker (CentOS/RHEL/Fedora)...")
                commands = [
                    "sudo yum install -y yum-utils",
                    "sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo",
                    "sudo yum install -y docker-ce docker-ce-cli containerd.io",
                    "sudo systemctl start docker",
                    "sudo systemctl enable docker"
                ]
                for cmd in commands:
                    print_info(f"执行: {cmd}")
                    result = subprocess.run(cmd, shell=True, check=False)
                    if result.returncode != 0:
                        print_error(f"命令执行失败: {cmd}")
                        return False
                
                # 添加当前用户到docker组
                subprocess.run("sudo usermod -aG docker $USER", shell=True, check=False)
                print_info("Docker安装完成，请重新登录以应用组权限更改")
                return True
            
            else:
                print_warning("未能识别的Linux发行版，请手动安装Docker")
                print_info("请参考Docker官方文档: https://docs.docker.com/engine/install/")
                return False
        except Exception as e:
            print_error(f"安装Docker时出错: {e}")
            return False
    
    elif platform.system() == "Darwin":  # macOS
        print_info("macOS系统需要手动安装Docker Desktop")
        print_info("请访问: https://www.docker.com/products/docker-desktop/")
        print_info("下载并安装Docker Desktop后重新运行此脚本")
        return False
    
    else:
        print_warning("未识别的操作系统，请手动安装Docker")
        return False

# 安装SearXNG搜索引擎
def setup_searxng():
    print_step(6, "设置SearXNG搜索引擎")
    
    # 询问是否需要设置SearXNG
    setup_choice = input("是否需要设置SearXNG搜索引擎? (y/n): ")
    if setup_choice.lower() != 'y':
        print_info("已跳过SearXNG设置")
        
        # 提供公共实例信息
        print_info("您可以使用公共SearXNG实例:")
        print_info("1. 编辑MaiBot/.env文件，添加如下配置:")
        print_info("   SEARXNG_URL=https://searx.be  # 或其他公共实例")
        print_info("2. 公共实例列表: https://searx.space/")
        
        return True
    
    # 检查Docker是否已安装
    docker_available = False
    try:
        subprocess.check_call(["docker", "--version"], stdout=subprocess.DEVNULL)
        docker_available = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_warning("未检测到Docker，需要先安装Docker")
        if install_docker():
            docker_available = True
    
    if not docker_available:
        print_warning("Docker未安装，无法自动配置SearXNG")
        print_info("请使用公共SearXNG实例:")
        print_info("1. 编辑MaiBot/.env文件，添加如下配置:")
        print_info("   SEARXNG_URL=https://searx.be  # 或其他公共实例")
        print_info("2. 公共实例列表: https://searx.space/")
        return True
    
    # 询问端口设置
    default_port = 32768
    port_input = input(f"请指定SearXNG使用的端口 (直接回车使用默认: {default_port}): ")
    port = int(port_input) if port_input.strip().isdigit() else default_port
    
    # 检查SearXNG是否已运行
    try:
        result = subprocess.check_output(["docker", "ps", "-a", "--filter", "name=searxng"], text=True)
        if "searxng" in result:
            print_info("SearXNG容器已存在")
            
            # 检查容器状态
            if "Up" in result:
                print_info("SearXNG容器正在运行")
                # 询问是否重启
                restart = input("是否重启SearXNG容器? (y/n): ")
                if restart.lower() == 'y':
                    print_info("正在重启SearXNG容器...")
                    subprocess.call(["docker", "restart", "searxng"])
                return True
            else:
                # 尝试启动已存在的容器
                print_info("尝试启动SearXNG容器...")
                subprocess.check_call(["docker", "start", "searxng"])
                print_info("SearXNG容器已启动")
                return True
    except subprocess.CalledProcessError as e:
        print_error(f"Docker命令执行失败: {e}")
    
    # 安装SearXNG
    print_info("正在拉取SearXNG镜像...")
    try:
        # 检查是否已存在searxng容器
        result = subprocess.check_output(["docker", "ps", "-a", "--filter", "name=searxng"], text=True)
        if "searxng" in result:
            # 删除已存在的容器
            print_info("删除已存在的searxng容器...")
            subprocess.call(["docker", "rm", "-f", "searxng"])
        
        # 拉取镜像
        subprocess.check_call(["docker", "pull", "searxng/searxng"])
        
        # 询问是否持久化数据
        persist = input("是否持久化SearXNG数据? (y/n): ")
        
        if persist.lower() == 'y':
            # 创建数据目录
            data_dir = "./searxng_data"
            os.makedirs(data_dir, exist_ok=True)
            
            print_info(f"正在启动SearXNG容器，端口: {port}，数据目录: {data_dir}")
            subprocess.check_call([
                "docker", "run", "-d",
                "-p", f"{port}:8080",
                "-v", f"{os.path.abspath(data_dir)}:/etc/searxng", 
                "--name", "searxng",
                "--restart", "unless-stopped",
                "searxng/searxng"
            ])
        else:
            print_info(f"正在启动SearXNG容器，端口: {port}")
            subprocess.check_call([
                "docker", "run", "-d", 
                "-p", f"{port}:8080", 
                "--name", "searxng",
                "--restart", "unless-stopped",
                "searxng/searxng"
            ])
        
        print_info("SearXNG搜索引擎设置完成")
        print_info(f"您可以通过 http://localhost:{port} 访问SearXNG")
        
        # 添加环境变量配置提示
        print_info("请确保在 .env 文件中添加以下配置:")
        print_info(f"SEARXNG_URL=http://localhost:{port}")
        print_info("SEARCH_COOLDOWN_SECONDS=600")
        
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"SearXNG安装失败: {e}")
        print_warning("请参考文档手动设置SearXNG搜索引擎")
        return False

# 创建启动脚本
def create_launcher(install_dir):
    print_step(7, "创建启动脚本")
    
    os_type = get_os_type()
    
    if os_type == "windows":
        # 创建Windows批处理文件
        launcher_path = os.path.join(install_dir, "启动MaiM.bat")
        with open(launcher_path, 'w', encoding='utf-8') as f:
            f.write('@echo off\n')
            f.write('title MaiM v62_lianwang 启动器\n')
            f.write('echo MaiM v62_lianwang 联网工具版 启动中...\n')
            f.write('echo.\n')
            f.write('cd /d "%~dp0MaiBot"\n')
            f.write('echo 1. 启动MaiBot...\n')
            f.write('start "" python bot.py\n')
            f.write('timeout /t 5 > nul\n')
            f.write('echo 2. 启动MaiBot-Napcat-Adapter...\n')
            f.write('cd /d "%~dp0MaiBot-Napcat-Adapter"\n')
            f.write('start "" python main.py\n')
            f.write('timeout /t 3 > nul\n')
            f.write('echo 3. 启动客户端...\n')
            f.write('cd /d "%~dp0"\n')
            f.write('start "" python bot_client_gui.py\n')
            f.write('echo.\n')
            f.write('echo MaiM v62_lianwang 已启动完成!\n')
            f.write('echo 如需停止，请关闭所有相关窗口。\n')
            f.write('timeout /t 10\n')
            
        print_info(f"启动脚本已创建: {launcher_path}")
    else:
        # 创建Linux/macOS shell脚本
        launcher_path = os.path.join(install_dir, "start_maim.sh")
        with open(launcher_path, 'w', encoding='utf-8') as f:
            f.write('#!/bin/bash\n')
            f.write('echo "MaiM v62_lianwang 联网工具版 启动中..."\n')
            f.write('echo\n')
            f.write('cd "$(dirname "$0")/MaiBot"\n')
            f.write('echo "1. 启动MaiBot..."\n')
            f.write('python bot.py &\n')
            f.write('sleep 5\n')
            f.write('echo "2. 启动MaiBot-Napcat-Adapter..."\n')
            f.write('cd "$(dirname "$0")/MaiBot-Napcat-Adapter"\n')
            f.write('python main.py &\n')
            f.write('sleep 3\n')
            f.write('echo "3. 启动客户端..."\n')
            f.write('cd "$(dirname "$0")"\n')
            f.write('python bot_client_gui.py &\n')
            f.write('echo\n')
            f.write('echo "MaiM v62_lianwang 已启动完成!"\n')
            f.write('echo "如需停止，请使用 pkill -f python"\n')
        
        # 设置执行权限
        os.chmod(launcher_path, 0o755)
        print_info(f"启动脚本已创建: {launcher_path}")
    
    return True

# 完成安装
def finalize_install(install_dir):
    print_step(8, "完成安装")
    
    # 创建安装完成标记
    with open(os.path.join(install_dir, "install_completed.txt"), 'w', encoding='utf-8') as f:
        f.write(f"安装完成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"安装工具版本: MaiM v62_lianwang 一键安装工具\n")
        f.write(f"Python版本: {sys.version}\n")
        f.write(f"操作系统: {platform.system()} {platform.version()}\n")
    
    print_header("安装完成")
    print(f"""
{Colors.GREEN}MaiM v62_lianwang 已成功安装！{Colors.ENDC}

您可以通过以下方式启动MaiM v62_lianwang:
1. 双击 "{os.path.join(install_dir, '启动MaiM.bat' if get_os_type() == 'windows' else 'start_maim.sh')}"

安装注意事项:
{Colors.WARNING}1. 请手动配置您的API密钥到 {os.path.join(install_dir, 'MaiBot', '.env')} 文件中{Colors.ENDC}
2. 如需调整SearXNG搜索引擎配置，请编辑.env文件中的SEARXNG_URL参数

{Colors.BLUE}感谢您使用MaiM！{Colors.ENDC}
    """)
    
    return True

# 主函数
def main():
    try:
        # 打印欢迎信息
        print_welcome()
        
        # 检查Python版本
        if not check_python_version():
            input("按Enter键退出...")
            return
        
        # 选择安装目录
        install_dir = choose_install_dir()
        if not install_dir:
            print_error("选择安装目录失败，无法继续安装")
            input("按Enter键退出...")
            return
        
        # 准备v62_lianwang文件
        install_dir = prepare_v10_files(install_dir)
        if not install_dir:
            print_error("准备安装文件失败，无法继续安装")
            input("按Enter键退出...")
            return
        
        # 安装依赖
        if not install_dependencies(install_dir):
            print_warning("依赖安装出现问题")
            user_choice = input("是否继续? (y/n): ")
            if user_choice.lower() != 'y':
                input("按Enter键退出...")
                return
        
        # 配置MaiBot
        configure_maibot(install_dir)
        
        # 设置SearXNG搜索引擎
        setup_searxng()
        
        # 创建启动脚本
        create_launcher(install_dir)
        
        # 完成安装
        finalize_install(install_dir)
        
        print_info("安装过程已完成！按Enter键退出...")
        input("")
    except KeyboardInterrupt:
        print_warning("\n安装过程被用户中断")
        print_info("如需重新安装，请重新运行此脚本")
        return
    except Exception as e:
        print_error(f"安装过程中出现未预期的错误: {e}")
        # 打印详细错误信息，帮助调试
        import traceback
        traceback.print_exc()
        input("按Enter键退出...")
        return

if __name__ == "__main__":
    main() 