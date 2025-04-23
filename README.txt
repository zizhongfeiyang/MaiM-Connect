==================================================
MaiM v62_lianwang 联网工具版 - 详细安装指南
==================================================

感谢您使用MaiM！本安装包将帮助您安装MaiM v62_lianwang联网工具版。

【新版亮点】
* 智能联网搜索：自动获取实时网络信息
* 知识库管理：将搜索结果存储并智能管理
* 工具系统增强：支持多种工具调用和集成
* 提升系统稳定性和部署便捷性

【系统要求】
1. 操作系统：Windows 10/11 或 Linux/macOS
2. Python 3.8 或更高版本
3. 内存：建议至少 4GB RAM
4. 磁盘空间：建议至少 2GB 可用空间
5. 网络连接：稳定的互联网连接

【前置条件】
1. Python 环境安装：
   - Windows: 访问 https://www.python.org/downloads/ 下载并安装
   - 安装时请勾选"Add Python to PATH"选项
   - 安装完成后，在命令行输入 python --version 验证安装

2. Docker 安装（可选，用于搜索引擎）：
   - Windows: 访问 https://www.docker.com/products/docker-desktop/ 下载并安装
   - 安装完成后，确保 Docker Desktop 正在运行

【详细安装步骤】
1. 解压安装包
   - 将下载的安装包解压到任意目录（建议使用英文路径）
   - 例如：D:\MaiM_Install

2. 运行安装脚本
   - 打开命令行（Windows: 按 Win+R，输入 cmd 并回车）
   - 进入安装包目录：
     cd D:\MaiM_Install
   - 运行安装脚本：
     python upgrade_v04_to_v10.py

3. 配置安装选项
   - 选择安装目录（建议使用英文路径）
   - 选择是否安装本地搜索引擎（需要 Docker）
   - 等待安装完成

4. 配置 API 密钥
   - 进入安装目录
   - 找到 MaiBot/.env 文件
   - 使用文本编辑器打开
   - 填入您的 API 密钥：
     OPENAI_API_KEY=您的API密钥
     SEARXNG_URL=http://localhost:32768  # 如果使用本地搜索引擎

5. 启动系统
   - Windows: 双击运行 start.bat
   - Linux/macOS: 在终端执行 ./start.sh

【搜索引擎配置】
1. 本地搜索引擎（推荐）：
   - 安装脚本会自动配置 Docker 版 SearXNG
   - 默认端口：32768
   - 访问 http://localhost:32768 验证是否正常运行

2. 公共搜索引擎：
   - 如果无法使用 Docker，可以配置公共实例
   - 编辑 MaiBot/.env 文件：
     SEARXNG_URL=https://searx.be  # 或其他公共实例
   - 公共实例列表：https://searx.space/

【常见问题解答】
Q: 安装过程中出现 Python 相关错误？
A: 确保已正确安装 Python 3.8+，并添加到系统环境变量

Q: Docker 安装失败或无法启动？
A: 可以跳过 Docker 安装，使用公共搜索引擎实例

Q: 如何验证安装是否成功？
A: 检查以下内容：
   - 安装目录下是否有 MaiBot 文件夹
   - .env 文件中的 API 密钥是否正确配置
   - 启动脚本是否可以正常运行

Q: 启动后无法使用联网功能？
A: 检查：
   - 网络连接是否正常
   - SearXNG 是否正常运行
   - .env 文件中的 SEARXNG_URL 配置是否正确

Q: 如何更新系统？
A: 下载新版本安装包，重复安装步骤即可

【故障排除】
1. 依赖安装失败：
   - 手动安装依赖：pip install -r requirements.txt
   - 安装特殊依赖：pip install aiohttp beautifulsoup4 urllib3 toml

2. 启动失败：
   - 检查日志文件：MaiBot/logs/error.log
   - 确认 API 密钥配置正确
   - 验证所有依赖已安装

3. 联网功能异常：
   - 检查网络连接
   - 验证 SearXNG 配置
   - 尝试使用其他公共搜索引擎实例

【获取帮助】
- 查看详细文档：安装包中的打包说明.md
- 联系技术支持：support@maim.com
- 访问官方网站：https://www.maim.com

================================================== 