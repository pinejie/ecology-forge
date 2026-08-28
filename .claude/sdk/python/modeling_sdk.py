# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 应用（App）

通过直连 SQL Server 数据库，封装建模引擎的应用操作。

依赖：pip install pymssql

使用示例：
    from modeling_sdk import ModelingSDK

    sdk = ModelingSDK(host="...", user="sa", password="Weaver@2001", database="ecology")
    app_id = sdk.create_app("测试应用", parent_id=1054)
"""

import pymssql
import os
from typing import List, Dict, Optional

from mcp_register import expose
from db_config import load_db_config


class ModelingSDK:
    """建模引擎 SDK — 应用操作"""

    def __init__(self, host: str = None, user: str = None, password: str = None, database: str = None, port: int = None):
        # 优先级：显式参数 > db-config.md > 环境变量
        defaults = load_db_config()
        self.host = host or defaults.get("host")
        self.user = user or defaults.get("user")
        self.password = password or defaults.get("password")
        self.database = database or defaults.get("database")
        self.port = port or defaults.get("port")
        if not self.password:
            raise RuntimeError("数据库密码未配置，请检查 .claude/sdk/db-config.md ")

    def _connect(self):
        return pymssql.connect(
            server=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="cp936"
        )

    def _encode(self, s):
        """字符串编码为 cp936 bytes，保证中文正确传入 SQL Server"""
        if s is None:
            return ""
        return str(s).encode("cp936")

    def _get_sub_company_id(self, cursor) -> int:
        """获取当前系统的 subCompanyId"""
        cursor.execute("SELECT fmdetachable FROM SystemSet")
        row = cursor.fetchone()
        fmdetachable = str(row[0]) if row else "0"

        if fmdetachable == "1":
            cursor.execute("SELECT fmdftsubcomid, dftsubcomid FROM SystemSet")
            row = cursor.fetchone()
            if row:
                sub_id = int(row[0] or -1)
                if sub_id in (-1, 0):
                    sub_id = int(row[1] or -1)
                if sub_id in (-1, 0):
                    cursor.execute("SELECT MIN(id) FROM HrmSubCompany")
                    r = cursor.fetchone()
                    sub_id = int(r[0]) if r else 0
                return sub_id if sub_id > 0 else 0
        return 0

    def _clear_cache(self):
        """清除建模缓存 — 通过调用 OA 暴露的 REST 接口（后续实现）"""
        pass

    # ============================================================
    #  应用（App）操作
    # ============================================================

    @expose(
        description="在泛微 OA 建模引擎中创建一个新应用。默认创建在「AI实践应用」下（按名称查找，不存在则自动创建），也可指定其他已有应用作为上级。",
        examples=[
            {"name": "测试应用"},
            {"name": "项目管理", "parent_id": 1}
        ],
        error_hints={
            "名称不能为空": "请提供应用名称",
            "parent_id 不能为 0 或负数": "请指定有效的上级应用 ID，可用 list_apps 查询",
            "上级应用不存在": "请检查 parent_id 是否正确，可用 list_apps 查询"
        }
    )
    def create_app(
        self,
        name: str,
        parent_id: int = None,
        description: str = "",
        show_order: float = 0
    ) -> int:
        """
        创建应用

        :param name: 应用名称（必填）
        :param parent_id: 上级应用 ID（选填）。不传时自动查找名为「AI实践应用」的应用作为父级；若不存在则在根应用下自动创建
        :param description: 应用描述（选填）
        :param show_order: 显示顺序，数值越小越靠前（默认 0）
        :return: 新建应用的 ID
        """
        if not name or not name.strip():
            raise ValueError("应用名称不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 默认父级：按名称查找「AI实践应用」，不存在则在根应用下自动创建
            if parent_id is None:
                cursor.execute(
                    "SELECT id FROM modeTreeField WHERE treeFieldName = %s AND isdelete = 0",
                    (self._encode("AI实践应用"),)
                )
                row = cursor.fetchone()
                if row:
                    parent_id = int(row[0])
                else:
                    # 找根应用（superFieldid=0 的顶级节点）
                    cursor.execute(
                        "SELECT id, ISNULL(allSuperFieldId, '') FROM modeTreeField "
                        "WHERE ISNULL(superFieldid, 0) = 0 AND isdelete = 0"
                    )
                    root = cursor.fetchone()
                    if not root:
                        raise ValueError("未找到根应用，无法自动创建「AI实践应用」")
                    root_id = int(root[0])
                    root_all = str(root[1] or "")

                    sub_company = self._get_sub_company_id(cursor)
                    all_super = "%s,%s" % (root_all, root_id) if root_all else str(root_id)

                    cursor.execute(
                        "INSERT INTO modeTreeField "
                        "(treeFieldName, treeFieldDesc, superFieldid, allSuperFieldId, treelevel, "
                        "isLast, showOrder, isdelete, subcompanyid, icon, iconColor, iconBg, "
                        "mobileappid, cubeuuid) "
                        "VALUES (%s, %s, %s, %s, 1, '0', 0, 0, %s, '', '', '', 0, NEWID())",
                        (self._encode("AI实践应用"), self._encode("AI 创建的应用统一挂载在此"),
                         root_id, all_super, sub_company)
                    )
                    cursor.execute("SELECT MAX(id) FROM modeTreeField")
                    parent_id = int(cursor.fetchone()[0])
                    # AI实践应用 创建完成后，清一次缓存，让后续操作能查到它
                    self._clear_cache()

            if parent_id <= 0:
                raise ValueError("parent_id 不能为 0 或负数，请指定有效的上级应用 ID")

            # 计算 allSuperFieldId 和 treelevel
            cursor.execute(
                "SELECT allSuperFieldId, treelevel FROM modeTreeField WHERE id = %s",
                (parent_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("上级应用不存在，ID=%d" % parent_id)
            parent_all = str(row[0] or "")
            parent_level = int(row[1] or 0)
            all_super = "%s,%s" % (parent_all, parent_id)
            treelevel = parent_level + 1

            sub_company = self._get_sub_company_id(cursor)

            cursor.execute(
                "INSERT INTO modeTreeField "
                "(treeFieldName, treeFieldDesc, superFieldid, allSuperFieldId, treelevel, "
                "isLast, showOrder, isdelete, subcompanyid, icon, iconColor, iconBg, "
                "mobileappid, cubeuuid) "
                "VALUES (%s, %s, %s, %s, %s, '1', %s, 0, %s, '', '', '', 0, NEWID())",
                (self._encode(name), self._encode(description), parent_id,
                 all_super, treelevel, show_order, sub_company)
            )
            conn.commit()

            # 获取新建的 ID
            cursor.execute("SELECT MAX(id) AS newId FROM modeTreeField")
            row = cursor.fetchone()
            new_id = int(row[0]) if row else -1

            self._clear_cache()
            return new_id

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="修改泛微 OA 建模引擎中已有应用的名称",
        examples=[
            {"app_id": 1066, "new_name": "新名称"}
        ],
        error_hints={
            "新名称不能为空": "请提供有效的新名称"
        }
    )
    def rename_app(self, app_id: int, new_name: str):
        """
        修改应用名称

        :param app_id: 应用 ID（必填）
        :param new_name: 新名称（必填）
        """
        if not new_name or not new_name.strip():
            raise ValueError("新名称不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE modeTreeField SET treeFieldName = %s WHERE id = %s",
                (self._encode(new_name), app_id)
            )
            conn.commit()
            self._clear_cache()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="物理删除泛微 OA 建模引擎中的应用及其所有关联资源（模块、查询、浏览框、布局、菜单等）",
        examples=[
            {"app_id": 1066}
        ],
        destructive=True
    )
    def delete_app(self, app_id: int):
        """
        删除应用（物理删除，级联清理所有关联资源）

        :param app_id: 应用 ID（必填）
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 1. 查找该应用下的所有模块
            cursor.execute("SELECT id FROM modeinfo WHERE modetype = %s", (app_id,))
            module_ids = [int(r[0]) for r in cursor.fetchall()]

            # 2. 清理每个模块的关联资源
            for mid in module_ids:
                # 删除模块的查询列表
                cursor.execute("SELECT id FROM mode_customsearch WHERE modeid = %s", (mid,))
                query_ids = [int(r[0]) for r in cursor.fetchall()]
                for qid in query_ids:
                    cursor.execute("DELETE FROM mode_CustomDspField WHERE customid = %s", (qid,))
                    cursor.execute("DELETE FROM mode_customsearch WHERE id = %s", (qid,))

                # 删除模块的布局
                cursor.execute("SELECT id FROM modehtmllayout WHERE modeid = %s", (mid,))
                layout_ids = [int(r[0]) for r in cursor.fetchall()]
                if layout_ids:
                    lph = ','.join([str(x) for x in layout_ids])
                    cursor.execute("DELETE FROM modeformfield WHERE layoutid IN (%s)" % lph)
                    cursor.execute("DELETE FROM modeformgroup WHERE layoutid IN (%s)" % lph)
                    cursor.execute("DELETE FROM modehtmllayout WHERE id IN (%s)" % lph)

                # 删除模块权限
                cursor.execute("DELETE FROM moderightinfo WHERE modeid = %s", (mid,))

                # 删除模块
                cursor.execute("DELETE FROM modeinfo WHERE id = %s", (mid,))

            # 3. 删除该应用下的所有自定义浏览框（含 MODE_BROWSER 映射）
            cursor.execute("SELECT id FROM mode_custombrowser WHERE appid = %s", (app_id,))
            browser_ids = [int(r[0]) for r in cursor.fetchall()]
            if browser_ids:
                bph = ','.join([str(x) for x in browser_ids])
                cursor.execute("DELETE FROM mode_CustombrowserDspField WHERE customid IN (%s)" % bph)
                cursor.execute("DELETE FROM MODE_BROWSER WHERE customid IN (%s)" % bph)
                cursor.execute("DELETE FROM mode_custombrowser WHERE id IN (%s)" % bph)

            # 4. 删除关联该应用的菜单（linkAddress 包含该应用的查询 ID）
            cursor.execute("SELECT id FROM mode_customsearch WHERE appid = %s", (app_id,))
            app_query_ids = [int(r[0]) for r in cursor.fetchall()]
            if app_query_ids:
                for qid in app_query_ids:
                    cursor.execute("DELETE FROM mode_CustomDspField WHERE customid = %s", (qid,))
                    cursor.execute("DELETE FROM mode_customsearch WHERE id = %s", (qid,))

            # 5. 删除应用节点
            cursor.execute("DELETE FROM modeTreeField WHERE id = %s", (app_id,))

            conn.commit()
            self._clear_cache()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="查询泛微 OA 建模引擎中的应用列表",
        examples=[
            {"parent_id": 0},
            {"parent_id": 1054}
        ],
        read_only=True
    )
    def list_apps(self, parent_id: int = 0) -> List[Dict]:
        """
        查询应用列表

        :param parent_id: 上级应用 ID，0 表示查根节点（默认 0）
        :return: 应用列表 [{"id": ..., "name": ..., "desc": ..., "showOrder": ..., "treelevel": ...}]
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, treeFieldName, treeFieldDesc, showOrder, treelevel "
                "FROM modeTreeField WHERE superFieldid = %s AND isdelete = 0 "
                "ORDER BY showOrder, id",
                (parent_id,)
            )
            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": int(row[0]),
                    "name": str(row[1] or ""),
                    "desc": str(row[2] or ""),
                    "showOrder": row[3],
                    "treelevel": int(row[4]) if row[4] else 0
                })
            return result
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="将泛微 OA 建模引擎中的应用移动到另一个上级节点下",
        examples=[
            {"app_id": 1066, "new_parent_id": 1054}
        ],
        error_hints={
            "目标上级应用不存在": "请检查 new_parent_id 是否正确"
        }
    )
    def move_app(self, app_id: int, new_parent_id: int = 0):
        """
        移动应用到新的上级节点

        :param app_id: 要移动的应用 ID（必填）
        :param new_parent_id: 新上级应用 ID，0 表示移到根节点（默认 0）
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            if new_parent_id == 0:
                new_all = ""
                new_level = 0
            else:
                cursor.execute(
                    "SELECT allSuperFieldId, treelevel FROM modeTreeField WHERE id = %s",
                    (new_parent_id,)
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError("目标上级应用不存在")
                new_all = "%s,%s" % (str(row[0] or ''), new_parent_id)
                new_level = int(row[1] or 0) + 1

            cursor.execute(
                "UPDATE modeTreeField SET superFieldid = %s, allSuperFieldId = %s, treelevel = %s WHERE id = %s",
                (new_parent_id, new_all, new_level, app_id)
            )
            conn.commit()
            self._clear_cache()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
