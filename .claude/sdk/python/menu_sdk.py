# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 菜单（Menu）

通过直连 SQL Server 数据库，封装门户菜单的创建、编辑、查询、删除操作。
SDK 只管执行，不做分析。

依赖：pip install pymssql

使用示例：
    from menu_sdk import MenuSDK

    sdk = XXX()  # 配置从 db-config.md 读取

    # 创建一级菜单（党团管理）
    menu_id = sdk.create_menu(
        name="党团管理",
        parent_id=0,
    )

    # 在一级菜单下创建子菜单（末级，带查询）
    sdk.create_menu(
        name="发展类型",
        parent_id=menu_id,
        query_id=2861,
    )

    # 查询菜单树
    tree = sdk.get_menu_tree()

    # 删除菜单
    sdk.delete_menu(menu_id)
"""

import pymssql
import os
import requests
from typing import List, Dict, Optional
from db_config import load_oa_config

from mcp_register import expose
from db_config import load_db_config


class MenuSDK:
    """门户菜单 SDK — 左侧菜单的 CRUD"""

    def __init__(self, host: str = None, user: str = None, password: str = None, database: str = None, port: int = None):
        defaults = load_db_config()
        self.host = host or defaults.get("host")
        self.user = user or defaults.get("user")
        self.password = password or defaults.get("password")
        self.database = database or defaults.get("database")
        self.port = port or defaults.get("port")
        if not self.password:
            raise RuntimeError("数据库密码未配置，请检查 .claude/sdk/db-config.md ")
        # OA 前端地址（用于调用 JSP 缓存清理接口）
        self.oa_host = load_oa_config()["oa_host"]

    @expose(
        description="清除菜单缓存。通过 HTTP 调用 clearMenuCache.jsp 使菜单变更立即生效。删除/创建/修改菜单后自动调用，也可手动触发。",
        read_only=True
    )
    def clear_menu_cache(self) -> dict:
        """
        清除菜单缓存，使菜单变更立即生效。

        Returns:
            缓存刷新结果，或失败时返回空字典
        """
        return self._clear_cache()

    def _clear_cache(self):
        """清除菜单缓存，通过 HTTP 调用 clearMenuCache.jsp"""
        url = self.oa_host + "/clearMenuCache.jsp"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception:
            pass

    def _connect(self):
        return pymssql.connect(
            server=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database
            # 注意：不使用 charset，手动处理中文编码
        )

    def _encode(self, s):
        """Python Unicode → GBK bytes，适配 SQL Server varchar 列"""
        if s is None:
            return ""
        return str(s).encode("gbk")

    def _decode(self, val):
        """SQL Server varchar 列读取还原"""
        if val is None:
            return ""
        if isinstance(val, bytes):
            return val.decode("gbk")
        if isinstance(val, str):
            try:
                return val.encode("latin1").decode("gbk")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return val
        return str(val)

    def _get_menu_tables(self):
        """返回左侧菜单表名"""
        return "LeftMenuInfo", "LeftMenuConfig"

    def _get_next_menu_id(self, cursor) -> int:
        """生成下一个菜单 ID（调用泛微存储过程 LeftMenuSequenceId_Get，与 Portal API 保持一致）"""
        cursor.execute(
            "DECLARE @flag INT, @msg VARCHAR(100); "
            "EXEC LeftMenuSequenceId_Get @flag OUTPUT, @msg OUTPUT; "
            "SELECT @flag AS new_id"
        )
        row = cursor.fetchone()
        if row and row[0]:
            return int(row[0])
        # 存储过程失败时降级：取 MIN(id)-1
        info_table, _ = self._get_menu_tables()
        cursor.execute("SELECT ISNULL(MIN(id), 0) - 1 FROM %s" % info_table)
        row = cursor.fetchone()
        return int(row[0]) if row else -1

    def _get_max_view_index(self, cursor, config_table: str, parent_id: int) -> int:
        """获取指定父级下的最大 viewIndex"""
        cursor.execute(
            "SELECT ISNULL(MAX(viewIndex), 0) FROM %s WHERE parentId = %s" % (config_table, parent_id)
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    # ============================================================
    #  查询
    # ============================================================

    @expose(
        description="查询左侧门户菜单树，返回树形结构。",
        read_only=True
    )
    def get_menu_tree(self, resource_id: int = 1, resource_type: int = 1) -> List[Dict]:
        """
        查询左侧菜单树结构。

        :param resource_id: 资源 ID（默认 1）
        :param resource_type: 资源类型（默认 1）
        :return: 树形结构的菜单列表
        """
        info_table, config_table = self._get_menu_tables()
        conn = self._connect()
        cursor = conn.cursor()

        try:
            # 关联 config 表，只查可见菜单
            sql = (
                "SELECT a.id, a.parentId, a.menuLevel, a.defaultIndex, a.module, "
                "a.isCustom, a.iconClassName, a.iconUrl, a.linkAddress, a.fullrouteurl, "
                "a.mobxrouteurl, a.baseTarget, a.topIconUrl, a.topmenuname, "
                "b.visible, b.viewIndex, b.customName "
                "FROM %s a "
                "INNER JOIN %s b ON a.id = b.infoId "
                "WHERE b.resourceid = %%s AND b.resourcetype = %%s "
                "ORDER BY b.viewIndex" % (info_table, config_table)
            )
            cursor.execute(sql, (resource_id, resource_type))
            rows = cursor.fetchall()

            # 构建菜单列表
            all_menus = []
            for row in rows:
                all_menus.append({
                    "id": row[0],
                    "parent_id": row[1],
                    "menu_level": row[2],
                    "default_index": row[3],
                    "module": self._decode(row[4]),
                    "is_custom": self._decode(row[5]),
                    "icon_class_name": self._decode(row[6]),
                    "icon_url": self._decode(row[7]),
                    "link_address": self._decode(row[8]),
                    "fullrouteurl": self._decode(row[9]),
                    "mobxrouteurl": self._decode(row[10]),
                    "base_target": self._decode(row[11]),
                    "top_icon_url": self._decode(row[12]),
                    "top_menu_name": self._decode(row[13]),
                    "visible": row[14],
                    "view_index": row[15],
                    "custom_name": self._decode(row[16]),
                    "children": [],
                })

            # 构建树
            menu_map = {m["id"]: m for m in all_menus}
            tree = []
            for m in all_menus:
                if m["parent_id"] == 0:
                    tree.append(m)
                elif m["parent_id"] in menu_map:
                    menu_map[m["parent_id"]]["children"].append(m)

            return tree
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="查询左侧菜单项的详细信息。",
        read_only=True
    )
    def get_menu_detail(self, menu_id: int) -> Dict:
        """
        查询单个菜单项的详细信息。

        :param menu_id: 菜单 ID
        :return: 菜单详细信息
        """
        info_table, config_table = self._get_menu_tables()
        conn = self._connect()
        cursor = conn.cursor()

        try:
            sql = (
                "SELECT a.id, a.parentId, a.menuLevel, a.defaultIndex, a.module, "
                "a.isCustom, a.iconClassName, a.iconUrl, a.linkAddress, a.fullrouteurl, "
                "a.mobxrouteurl, a.baseTarget, a.topIconUrl, a.topmenuname, "
                "a.useCustomName, a.customName, a.customName_e, a.customName_t, "
                "b.visible, b.viewIndex, b.customName as cfg_customName, b.locked "
                "FROM %s a "
                "LEFT JOIN %s b ON a.id = b.infoId "
                "WHERE a.id = %%s" % (info_table, config_table)
            )
            cursor.execute(sql, (menu_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("菜单不存在，ID=%d" % menu_id)

            # 查询附加参数
            cursor.execute(
                "SELECT params, menutype1 FROM menuparams WHERE menuid = %s",
                (str(menu_id),)
            )
            param_row = cursor.fetchone()

            result = {
                "id": row[0],
                "parent_id": row[1],
                "menu_level": row[2],
                "default_index": row[3],
                "module": self._decode(row[4]),
                "is_custom": self._decode(row[5]),
                "icon_class_name": self._decode(row[6]),
                "icon_url": self._decode(row[7]),
                "link_address": self._decode(row[8]),
                "fullrouteurl": self._decode(row[9]),
                "mobxrouteurl": self._decode(row[10]),
                "base_target": self._decode(row[11]),
                "top_icon_url": self._decode(row[12]),
                "top_menu_name": self._decode(row[13]),
                "use_custom_name": self._decode(row[14]),
                "custom_name": self._decode(row[15]),
                "custom_name_e": self._decode(row[16]),
                "custom_name_t": self._decode(row[17]),
                "visible": row[18] if row[18] else "0",
                "view_index": row[19] if row[19] else 0,
                "cfg_custom_name": self._decode(row[20]) if row[20] else "",
                "locked": row[21] if row[21] else "0",
            }
            if param_row:
                result["params"] = self._decode(param_row[0])
                result["menutype1"] = self._decode(param_row[1])

            return result
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  创建菜单
    # ============================================================

    @expose(
        description="创建门户菜单。只需传菜单名、上级菜单、（可选）查询ID，其余自动处理。",
        examples=[{
            "name": "党团管理",
            "parent_id": 0,
        }, {
            "name": "发展类型",
            "parent_id": 1234,
            "query_id": 2861,
        }],
    )
    def create_menu(
        self,
        name: str,
        parent_id: int = 0,
        query_id: int = None,
        resource_id: int = 1,
        resource_type: int = 1,
        visible: str = "1",
    ) -> int:
        """
        创建左侧菜单项。内置业务规则：
        1. 顶部简称自动为 "AI配置{name}"
        2. 有下级（parent_id=0 或该菜单会被其他菜单引用为父级）→ link_address 留空
           末级（传了 query_id）→ 自动拼接 /spa/cube/index.html#/main/cube/search?customid={query_id}
        3. 打开位置（baseTarget）固定 NULL
        4. 图标全不配置
        5. menu_level 根据 parent_id 自动计算

        :param name: 菜单名称（必填）
        :param parent_id: 父级菜单 ID，0 表示一级菜单
        :param query_id: 末级菜单关联的查询 ID（mode_customsearch.id），传了则自动生成完整链接
        :param resource_id: 资源 ID
        :param resource_type: 资源类型
        :param visible: 是否可见，"1" 可见，"0" 不可见
        :return: 新建菜单的 ID
        """
        if not name:
            raise ValueError("菜单名称不能为空")

        info_table, config_table = self._get_menu_tables()
        conn = self._connect()
        cursor = conn.cursor()

        try:
            # 自动计算 menu_level
            if parent_id == 0:
                menu_level = 1
            else:
                cursor.execute(
                    "SELECT menuLevel, customName FROM %s WHERE id = %s" % (info_table, parent_id)
                )
                parent_row = cursor.fetchone()
                if not parent_row:
                    raise ValueError("父级菜单不存在，ID=%d" % parent_id)
                # 系统根节点（customName 为空）不能作为父菜单
                parent_custom_name = self._decode(parent_row[1]) if parent_row[1] else ""
                if not parent_custom_name.strip():
                    raise ValueError(
                        "父级菜单 ID=%d 是系统根节点（无名称），不能作为父菜单。"
                        "一级菜单请使用 parent_id=0" % parent_id
                    )
                menu_level = int(parent_row[0]) + 1

            # 自动计算 default_index
            cursor.execute("SELECT ISNULL(MAX(defaultIndex), 0) + 1 FROM %s WHERE parentId = %s" % (info_table, parent_id))
            default_index = int(cursor.fetchone()[0])

            # 自动计算 viewIndex
            cursor.execute("SELECT ISNULL(MAX(viewIndex), 0) + 1 FROM %s" % config_table)
            view_index = int(cursor.fetchone()[0])

            # 链接地址：末级拼接，有下级留空
            if query_id:
                link_address = "/spa/cube/index.html#/main/cube/search?customid=%d" % query_id
            else:
                link_address = ""

            # 顶部简称：AI配置 + 菜单名称
            top_menu_name = "AI配置" + name

            # 生成菜单 ID
            menu_id = self._get_next_menu_id(cursor)

            # 1. 插入 Info 表（固定值对齐手动创建 -618）
            cursor.execute(
                "INSERT INTO %s "
                "(id, parentId, menuLevel, defaultIndex, module, relatedModuleId, "
                "isCustom, useCustomName, "
                "linkAddress, fullrouteurl, mobxrouteurl, baseTarget, "
                "iconUrl, topIconUrl, iconType, iconFrom, iconClassName, iconImgSrc, "
                "topmenuname, customName, customName_e, customName_t, refersubid) "
                "VALUES (%%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s)" % info_table,
                (menu_id, parent_id, menu_level, default_index,
                 None,   # module
                 12,     # relatedModuleId（固定值）
                 "2",    # isCustom（对齐手动创建）
                 "1",    # useCustomName（对齐手动创建）
                 self._encode(link_address),
                 self._encode(link_address),  # fullrouteurl 与 linkAddress 一致
                 "",     # mobxrouteurl
                 "",     # baseTarget（空串，非NULL）
                 "",     # iconUrl
                 "",     # topIconUrl
                 "",     # iconType
                 "",     # iconFrom
                 "",     # iconClassName
                 "",     # iconImgSrc
                 self._encode(top_menu_name),
                 self._encode(name),
                 "",     # customName_e
                 "",     # customName_t
                 -1)     # refersubid
            )

            # 2. 插入 Config 表（对齐手动创建 -618）
            cursor.execute(
                "INSERT INTO %s "
                "(infoId, userId, visible, viewIndex, resourceid, resourcetype, locked, "
                "lockedById, useCustomName, "
                "customName, customName_e, customName_t, topmenuname) "
                "VALUES (%%s, 0, %%s, %%s, %%s, %%s, '0', 0, '0', %%s, '', '', '')" % config_table,
                (menu_id, visible, view_index,
                 resource_id, str(resource_type),
                 self._encode(name))
            )

            conn.commit()

            # 清缓存使菜单生效
            self._clear_cache()

            return menu_id
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  编辑菜单
    # ============================================================

    @expose(
        description="编辑已有菜单项的属性。",
    )
    def update_menu(
        self,
        menu_id: int,
        name: str = None,
        parent_id: int = None,
        query_id: int = None,
        default_index: int = None,
        visible: str = None,
        resource_id: int = 1,
        resource_type: int = 1,
    ) -> Dict:
        """
        编辑左侧菜单项。只传需要修改的字段，不传的字段不修改。

        :param menu_id: 菜单 ID
        :param name: 菜单名称
        :param parent_id: 父级菜单 ID
        :param query_id: 查询 ID，传了则自动重新拼接链接
        :param default_index: 显示顺序
        :param visible: 可见性，"1" 或 "0"
        :param resource_id: 资源 ID（默认 1）
        :param resource_type: 资源类型（默认 1）
        :return: {"menu_id": int, "updated_fields": list}
        """
        info_table, config_table = self._get_menu_tables()
        conn = self._connect()
        cursor = conn.cursor()

        try:
            # 确认菜单存在
            cursor.execute("SELECT id, parentId FROM %s WHERE id = %s" % (info_table, menu_id))
            row = cursor.fetchone()
            if not row:
                raise ValueError("菜单不存在，ID=%d" % menu_id)

            updated = []
            info_updates = {}
            config_updates = {}

            if name is not None:
                info_updates["customName"] = self._encode(name)
                config_updates["customName"] = self._encode(name)
                # 更新 topmenuname 也带 AI配置 前缀
                config_updates["topmenuname"] = self._encode("AI配置" + name)
                info_updates["topmenuname"] = self._encode("AI配置" + name)
                updated.append("name")

            if parent_id is not None:
                info_updates["parentId"] = parent_id
                updated.append("parent_id")

            if query_id is not None:
                link_address = "/spa/cube/index.html#/main/cube/search?customid=%d" % query_id
                info_updates["linkAddress"] = self._encode(link_address)
                updated.append("link_address")

            if default_index is not None:
                info_updates["defaultIndex"] = default_index
                updated.append("default_index")

            if visible is not None:
                config_updates["visible"] = visible
                updated.append("visible")

            if info_updates:
                set_parts = []
                values = []
                for k, v in info_updates.items():
                    set_parts.append("%s = %%s" % k)
                    values.append(v)
                values.append(menu_id)
                cursor.execute(
                    "UPDATE %s SET %s WHERE id = %%s" % (info_table, ", ".join(set_parts)),
                    tuple(values)
                )

            # 更新 Config 表
            if config_updates:
                cursor.execute(
                    "SELECT COUNT(*) FROM %s WHERE infoId = %s AND resourceid = %s AND resourcetype = %s" %
                    (config_table, menu_id, resource_id, resource_type)
                )
                if int(cursor.fetchone()[0]) > 0:
                    set_parts = []
                    values = []
                    for k, v in config_updates.items():
                        set_parts.append("%s = %%s" % k)
                        values.append(v)
                    values.extend([menu_id, resource_id, resource_type])
                    cursor.execute(
                        "UPDATE %s SET %s WHERE infoId = %%s AND resourceid = %%s AND resourcetype = %%s" % (config_table, ", ".join(set_parts)),
                        tuple(values)
                    )
                else:
                    # Config 不存在则新建
                    cursor.execute("SELECT ISNULL(MAX(viewIndex), 0) + 1 FROM %s" % config_table)
                    vi = int(cursor.fetchone()[0])
                    cursor.execute(
                        "INSERT INTO %s (infoId, visible, viewIndex, resourceid, resourcetype, locked, customName, topmenuname) "
                        "VALUES (%%s, %%s, %%s, %%s, %%s, '0', %%s, %%s)" % config_table,
                        (menu_id,
                         config_updates.get("visible", "1"),
                         vi, resource_id, resource_type,
                         config_updates.get("customName", self._encode("")),
                         config_updates.get("topmenuname", self._encode("")))
                    )

            conn.commit()

            # 清缓存使菜单生效
            self._clear_cache()

            return {"menu_id": menu_id, "updated_fields": updated}
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  删除菜单
    # ============================================================

    @expose(
        description="删除左侧菜单项及其所有子菜单，同时清理 Config 和 menuparams 记录。",
        destructive=True
    )
    def delete_menu(self, menu_id: int) -> Dict:
        """
        删除左侧菜单项（含所有子菜单）。

        :param menu_id: 菜单 ID
        :return: {"deleted_menu_ids": [...], "deleted_config_count": int}
        """
        info_table, config_table = self._get_menu_tables()
        conn = self._connect()
        cursor = conn.cursor()

        try:
            # 递归查找所有子菜单 ID
            ids_to_delete = [menu_id]
            queue = [menu_id]
            while queue:
                pid = queue.pop(0)
                cursor.execute("SELECT id FROM %s WHERE parentId = %s" % (info_table, pid))
                children = [int(r[0]) for r in cursor.fetchall()]
                ids_to_delete.extend(children)
                queue.extend(children)

            # 删除 Config 记录
            placeholders = ",".join(["%s"] * len(ids_to_delete))
            cursor.execute(
                "DELETE FROM %s WHERE infoId IN (%s)" % (config_table, placeholders),
                tuple(ids_to_delete)
            )
            deleted_config = cursor.rowcount

            # 删除 menuparams
            str_ids = [str(i) for i in ids_to_delete]
            placeholders2 = ",".join(["%s"] * len(str_ids))
            cursor.execute(
                "DELETE FROM menuparams WHERE menuid IN (%s) AND menutype = 'left'",
                tuple(str_ids)
            )

            # 删除 Info 记录
            cursor.execute(
                "DELETE FROM %s WHERE id IN (%s)" % (info_table, placeholders),
                tuple(ids_to_delete)
            )

            conn.commit()

            # 清缓存使菜单生效
            self._clear_cache()

            return {
                "deleted_menu_ids": ids_to_delete,
                "deleted_config_count": deleted_config,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  批量设置可见性（对应 setMenuTreeDataCmd）
    # ============================================================

    @expose(
        description="批量设置左侧菜单可见性。将 checked_ids 设为可见，unChecked_ids 设为不可见。",
    )
    def set_menu_visibility(
        self,
        checked_ids: List[int] = None,
        un_checked_ids: List[int] = None,
        resource_id: int = 1,
        resource_type: int = 1,
    ) -> Dict:
        """
        批量切换左侧菜单可见性（对应 setMenuTreeDataCmd）。

        :param checked_ids: 设为可见的菜单 ID 列表
        :param un_checked_ids: 设为不可见的菜单 ID 列表
        :param resource_id: 资源 ID
        :param resource_type: 资源类型
        :return: {"checked_count": int, "unchecked_count": int}
        """
        _, config_table = self._get_menu_tables()
        conn = self._connect()
        cursor = conn.cursor()

        try:
            checked_count = 0
            unchecked_count = 0

            if checked_ids:
                placeholders = ",".join(["%%s"] * len(checked_ids))
                sql = ("UPDATE %s SET visible = '1' WHERE infoId IN (%s) AND resourceid = %%s AND resourcetype = %%s" %
                    (config_table, placeholders))
                cursor.execute(sql, tuple(checked_ids) + (resource_id, resource_type))
                checked_count = cursor.rowcount

            if un_checked_ids:
                placeholders = ",".join(["%%s"] * len(un_checked_ids))
                sql = ("UPDATE %s SET visible = '0' WHERE infoId IN (%s) AND resourceid = %%s AND resourcetype = %%s" %
                    (config_table, placeholders))
                cursor.execute(sql, tuple(un_checked_ids) + (resource_id, resource_type))
                unchecked_count = cursor.rowcount

            conn.commit()
            return {"checked_count": checked_count, "unchecked_count": unchecked_count}
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  创建子菜单（便捷方法）
    # ============================================================

    @expose(
        description="在指定父菜单下批量创建左侧子菜单。末级子菜单传 query_id 自动拼接链接，有下级的子菜单不传 query_id。",
        examples=[{
            "parent_id": 0,
            "children": [
                {"name": "党团管理"},
                {"name": "发展类型", "query_id": 2861},
                {"name": "届级管理", "query_id": 2862},
            ]
        }]
    )
    def create_sub_menus(
        self,
        parent_id: int,
        children: List[Dict] = None,
        resource_id: int = 1,
        resource_type: int = 1,
    ) -> List[Dict]:
        """
        批量创建左侧子菜单。

        :param parent_id: 父菜单 ID
        :param children: 子菜单配置，每项含 name（必填）和 query_id（选填，末级才需要）
        :param resource_id: 资源 ID
        :param resource_type: 资源类型
        :return: 创建的菜单 ID 列表
        """
        if not children:
            raise ValueError("children 不能为空")

        results = []
        for child in children:
            menu_id = self.create_menu(
                name=child["name"],
                parent_id=parent_id,
                query_id=child.get("query_id"),
                resource_id=resource_id,
                resource_type=resource_type,
                visible=child.get("visible", "1"),
            )
            results.append({"name": child["name"], "menu_id": menu_id})

        return results
