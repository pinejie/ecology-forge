# -*- coding: utf-8 -*-
"""
建模 SDK 测试脚本

运行：python demo.py
"""

from modeling_sdk import ModelingSDK

# OA 数据库连接信息
SDK = ModelingSDK(
    host="172.18.28.108",
    user="sa",
    password="Weaver@2001",
    database="ecology"
)


def main():
    # 1. 查询根节点应用列表
    print("=== 查询根节点应用列表 ===")
    apps = SDK.list_apps(parent_id=0)
    print(f"根节点共 {len(apps)} 个应用")
    for app in apps[:5]:  # 只显示前 5 个
        print(f"  ID={app['id']}, 名称={app['name']}, 层级={app['treelevel']}")

    # 2. 查询"其它"（ID=1054）下的子应用
    print("\n=== 查询【其它】(ID=1054) 下的应用 ===")
    apps = SDK.list_apps(parent_id=1054)
    print(f"共 {len(apps)} 个应用")
    for app in apps:
        print(f"  ID={app['id']}, 名称={app['name']}")

    # 3. 创建新应用
    print("\n=== 在【其它】下创建应用 ===")
    new_id = SDK.create_app("Python测试应用", parent_id=1054, description="由 Python SDK 创建")
    print(f"新建应用 ID = {new_id}")

    # 4. 再次查询"其它"下的应用，确认创建成功
    print("\n=== 确认新应用已创建 ===")
    apps = SDK.list_apps(parent_id=1054)
    for app in apps:
        marker = " <-- 新建" if app["id"] == new_id else ""
        print(f"  ID={app['id']}, 名称={app['name']}{marker}")

    # 5. 重命名
    print("\n=== 重命名应用 ===")
    SDK.rename_app(new_id, "Python测试-已改名")
    print("重命名完成")

    # 6. 删除（软删除）
    print("\n=== 删除应用 ===")
    SDK.delete_app(new_id)
    print("删除完成")

    # 7. 确认已删除（不再出现在列表中）
    print("\n=== 确认应用已删除 ===")
    apps = SDK.list_apps(parent_id=1054)
    found = any(app["id"] == new_id for app in apps)
    print(f"ID={new_id} 的应用{'已不存在' if not found else '仍然存在'}")


if __name__ == "__main__":
    main()
