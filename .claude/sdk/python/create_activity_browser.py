# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, "/home/wangg/workspace/.claude/sdk/python")

from browser_sdk import BrowserSDK

sdk = BrowserSDK()  # 配置从 db-config.md 读取

result = sdk.create_browser(
    name="活动",
    app_id=1076,
    form_id=-1063,
    fields=[
        {"field_id": 31170, "is_show": "1", "show_order": 1, "is_title": True, "is_query": "1", "query_order": 1, "is_order": "1", "order_num": 1, "order_type": "a", "is_quick_search": "1"},
        {"field_id": 31171, "is_show": "1", "show_order": 2, "is_query": "1", "query_order": 2},
        {"field_id": 31176, "is_show": "1", "show_order": 3, "is_query": "1", "query_order": 3},
    ],
    description="",
    page_number=10
)

print("创建结果:", result)
