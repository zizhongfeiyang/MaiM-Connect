from fastapi import FastAPI, APIRouter
from typing import Optional
from uvicorn import Config, Server as UvicornServer
import os
import logging

logger = logging.getLogger(__name__)


class Server:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, app_name: str = "MaiMCore"):
        self.app = FastAPI(title=app_name)
        self._host: str = "127.0.0.1"
        self._port: int = 8080
        self._server: Optional[UvicornServer] = None
        self.set_address(host, port)

    def register_router(self, router: APIRouter, prefix: str = ""):
        """注册路由

        APIRouter 用于对相关的路由端点进行分组和模块化管理：
        1. 可以将相关的端点组织在一起，便于管理
        2. 支持添加统一的路由前缀
        3. 可以为一组路由添加共同的依赖项、标签等

        示例:
            router = APIRouter()

            @router.get("/users")
            def get_users():
                return {"users": [...]}

            @router.post("/users")
            def create_user():
                return {"msg": "user created"}

            # 注册路由，添加前缀 "/api/v1"
            server.register_router(router, prefix="/api/v1")
        """
        self.app.include_router(router, prefix=prefix)

    def set_address(self, host: Optional[str] = None, port: Optional[int] = None):
        """设置服务器地址和端口"""
        if host:
            self._host = host
        if port:
            self._port = port

    async def run(self):
        """启动服务器"""
        config = Config(app=self.app, host=self._host, port=self._port)
        self._server = UvicornServer(config=config)
        try:
            await self._server.serve()
        except KeyboardInterrupt:
            await self.shutdown()
            raise
        except Exception as e:
            await self.shutdown()
            raise RuntimeError(f"服务器运行错误: {str(e)}") from e
        finally:
            await self.shutdown()

    async def shutdown(self):
        """安全关闭服务器"""
        if self._server:
            try:
                # 设置退出标志
                self._server.should_exit = True
                
                # 等待服务器关闭
                await self._server.shutdown()
                
                # 清理资源
                if hasattr(self._server, 'servers'):
                    for server in self._server.servers:
                        await server.shutdown()
                
                # 等待所有连接关闭
                if hasattr(self._server, 'connections'):
                    for conn in self._server.connections:
                        await conn.close()
                
                # 清理服务器实例
                self._server = None
                
                logger.info("服务器已安全关闭")
            except Exception as e:
                logger.error(f"服务器关闭时发生错误: {e}")
                raise

    def get_app(self) -> FastAPI:
        """获取 FastAPI 实例"""
        return self.app


global_server = Server(host=os.environ["HOST"], port=int(os.environ["PORT"]))
