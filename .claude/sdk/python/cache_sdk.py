# -*- coding: utf-8 -*-
"""
泛微 OA Label 缓存刷新工具

通过 HTTP 调用 Resin 上的 cacheRefresh.jsp 接口，清除 LabelComInfo 内存缓存。
创建/修改表单字段后自动调用，确保线上显示使用最新 label 数据。

使用示例：
    from cache_sdk import refresh_label_cache, CacheSDK

    # 直接调用
    refresh_label_cache()

    # 或通过 SDK 类
    sdk = CacheSDK()
    sdk.refresh_label_cache()
"""

import requests
from mcp_register import expose

OA_HOST = "http://xcx.zhongda.cn:8080"


class CacheSDK:
    """OA 缓存管理 SDK"""

    def __init__(self, host: str = None):
        self.host = host or OA_HOST

    @expose(
        description="清除 LabelComInfo 内存缓存，使新建/修改的表单 label 立即生效。创建表单后自动调用，无需手动触发。",
    )
    def refresh_label_cache(self) -> dict:
        """
        清除 LabelComInfo 内存缓存。

        Returns:
            {"status": "1", "message": "..."} 或 {"status": "-1", "message": "..."}
        """
        url = self.host + "/cacheRefresh.jsp"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "-1", "message": "缓存刷新失败: " + str(e)}


def refresh_label_cache(host=None):
    """便捷函数：一行调用缓存刷新"""
    return CacheSDK(host=host).refresh_label_cache()
