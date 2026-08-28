# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 快捷搜索（QuickSearch）

通过直连 SQL Server 数据库，封装查询列表快捷搜索条件的增删改查操作。

依赖：pip install pymssql

存储结构：
    mode_quicksearch_setting    — 快捷搜索主配置（每个查询一条）
    mode_quicksearch_condition  — 快捷搜索条件明细（每个条件一条）

使用示例：
    from quicksearch_sdk import QuickSearchSDK

    sdk = XXX()  # 配置从 db-config.md 读取

    # 创建快捷搜索主配置
    sdk.create_quicksearch_setting(query_id=2732)

    # 添加快捷搜索条件
    sdk.add_quicksearch_condition(query_id=2732, field_id=12345, custom_name="房间号", field_type=1, order_id=0)

    # 查询已有条件
    conditions = sdk.list_quicksearch_conditions(query_id=2732)

    # 修改条件
    sdk.update_quicksearch_condition(query_id=2732, field_id=12345, custom_name="房间编号")

    # 删除条件
    sdk.delete_quicksearch_condition(query_id=2732, field_id=12345)

规则文档：docs/sdk-references/quicksearch-rules.md
"""

import pymssql
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional

from mcp_register import expose
from db_config import load_db_config


class QuickSearchSDK:
    """建模引擎快捷搜索 SDK"""

    def __init__(self, host: str = None, user: str = None, password: str = None, database: str = None, port: int = None):
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
            database=self.database
            # 注意：不使用 charset，手动处理中文编码
        )

    def _encode(self, s):
        """字符串编码为 GBK bytes，适配 SQL Server varchar 列写入"""
        if s is None:
            return ""
        return str(s).encode("gbk")

    def _decode(self, val):
        """SQL Server varchar 列读取还原：pymssql 默认 latin1 解码，需先转回字节再 GBK 解码"""
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

    def _clear_cache(self):
        """清除建模缓存"""
        pass

    def _gen_uuid(self) -> str:
        """生成 40 位以内 UUID（大写无横杠）"""
        return str(uuid.uuid4()).upper().replace("-", "")[:40]

    def _now_date(self) -> str:
        """当前日期 YYYY-MM-DD"""
        return datetime.now().strftime("%Y-%m-%d")

    def _now_time(self) -> str:
        """当前时间 HH:MM:SS"""
        return datetime.now().strftime("%H:%M:%S")

    # ============================================================
    #  创建快捷搜索主配置
    # ============================================================

    @expose(
        description="为查询列表创建快捷搜索主配置（mode_quicksearch_setting）。如果已存在则报错。",
        examples=[
            {"query_id": 2732},
        ],
        error_hints={
            "查询不存在": "请检查 query_id 是否正确",
            "快捷搜索配置已存在": "该查询已有快捷搜索配置，无需重复创建"
        }
    )
    def create_quicksearch_setting(
        self,
        query_id: int,
        is_show_type: int = 0,
        is_hide_name: int = 0,
    ) -> Dict:
        """
        创建快捷搜索主配置

        :param query_id: 查询 ID（必填）
        :param is_show_type: 显示类型，0=默认(默认)
        :param is_hide_name: 是否隐藏名称，0=不隐藏(默认)
        :return: {"query_id": int, "status": "created"}
        """
        if not query_id:
            raise ValueError("查询 ID 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 验证查询存在
            cursor.execute(
                "SELECT id FROM mode_customsearch WHERE id = %s",
                (query_id,)
            )
            if not cursor.fetchone():
                raise ValueError("查询不存在，ID=%d" % query_id)

            # 检查是否已存在
            cursor.execute(
                "SELECT id FROM mode_quicksearch_setting WHERE customid = %s",
                (query_id,)
            )
            if cursor.fetchone():
                raise ValueError("快捷搜索配置已存在，query_id=%d" % query_id)

            cursor.execute(
                "INSERT INTO mode_quicksearch_setting "
                "(customid, isquicksearch, updatetor, updatedate, updatetime, isshowtype, ishidename, cubeuuid) "
                "VALUES (%s, 1, 0, %s, %s, %s, %s, %s)",
                (query_id, self._now_date(), self._now_time(), is_show_type, is_hide_name, self._gen_uuid())
            )
            conn.commit()
            self._clear_cache()

            return {"query_id": query_id, "status": "created"}

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  添加快捷搜索条件
    # ============================================================

    @expose(
        description="为查询列表添加一个快捷搜索条件。自动创建主配置（如果还不存在）。type 固定为 5。",
        examples=[
            {"query_id": 2732, "field_id": 12345, "custom_name": "房间号", "order_id": 0},
            {"query_id": 2732, "field_id": 12346, "custom_name": "入住日期", "order_id": 1, "show_model": 1},
        ],
        error_hints={
            "查询不存在": "请检查 query_id 是否正确",
            "字段不存在": "请检查 field_id 是否在 workflow_billfield 表中"
        }
    )
    def add_quicksearch_condition(
        self,
        query_id: int,
        field_id: int,
        custom_name: str,
        order_id: int = 0,
        group_id: int = 0,
        show_model: int = 0,
    ) -> Dict:
        """
        添加快捷搜索条件

        :param query_id: 查询 ID（必填）
        :param field_id: 字段 ID（workflow_billfield.id，必填）
        :param custom_name: 快捷搜索显示名称（必填）
        :param order_id: 显示顺序，从 0 开始（默认 0）
        :param group_id: 分组 ID，默认 0
        :param show_model: 显示模式，0=文本输入框(默认), 1=日期选择器
        :return: {"query_id": int, "field_id": int, "status": "added"}
        """
        if not query_id:
            raise ValueError("查询 ID 不能为空")
        if not field_id:
            raise ValueError("字段 ID 不能为空")
        if not custom_name or not custom_name.strip():
            raise ValueError("快捷搜索显示名称不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 验证查询存在
            cursor.execute(
                "SELECT id FROM mode_customsearch WHERE id = %s",
                (query_id,)
            )
            if not cursor.fetchone():
                raise ValueError("查询不存在，ID=%d" % query_id)

            # 验证字段存在（系统字段允许）
            if field_id > 0:
                cursor.execute(
                    "SELECT id FROM workflow_billfield WHERE id = %s",
                    (field_id,)
                )
                if not cursor.fetchone():
                    raise ValueError("字段不存在，field_id=%d" % field_id)

            # 自动创建主配置（如果还不存在）
            cursor.execute(
                "SELECT id FROM mode_quicksearch_setting WHERE customid = %s",
                (query_id,)
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO mode_quicksearch_setting "
                    "(customid, isquicksearch, updatetor, updatedate, updatetime, isshowtype, ishidename, cubeuuid) "
                    "VALUES (%s, 1, 0, %s, %s, 0, 0, %s)",
                    (query_id, self._now_date(), self._now_time(), self._gen_uuid())
                )

            # 检查该字段是否已有快捷搜索条件
            cursor.execute(
                "SELECT id FROM mode_quicksearch_condition WHERE customid = %s AND fieldid = %s",
                (query_id, field_id)
            )
            if cursor.fetchone():
                raise ValueError(
                    "该字段已有快捷搜索条件，query_id=%d, field_id=%d" % (query_id, field_id)
                )

            # 插入条件（type 固定为 5）
            cursor.execute(
                "INSERT INTO mode_quicksearch_condition "
                "(customid, fieldid, customname, type, orderid, groupid, showmodel, cubeuuid) "
                "VALUES (%s, %s, %s, 5, %s, %s, %s, %s)",
                (query_id, field_id, self._encode(custom_name),
                 order_id, group_id, show_model, self._gen_uuid())
            )
            conn.commit()
            self._clear_cache()

            return {"query_id": query_id, "field_id": field_id, "status": "added"}

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  查询快捷搜索条件列表
    # ============================================================

    @expose(
        description="查询查询列表的快捷搜索条件列表",
        examples=[
            {"query_id": 2732},
        ],
        read_only=True
    )
    def list_quicksearch_conditions(
        self,
        query_id: int,
    ) -> List[Dict]:
        """
        查询快捷搜索条件列表

        :param query_id: 查询 ID（必填）
        :return: 条件列表，包含 field_id, custom_name, field_type, order_id, group_id, show_model
        """
        if not query_id:
            raise ValueError("查询 ID 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 查询条件明细
            cursor.execute(
                "SELECT qc.fieldid, qc.customname, qc.type, qc.orderid, "
                "qc.groupid, qc.showmodel, qc.cubeuuid, "
                "wf.fieldname, h.labelname "
                "FROM mode_quicksearch_condition qc "
                "LEFT JOIN workflow_billfield wf ON qc.fieldid = wf.id "
                "LEFT JOIN HtmlLabelInfo h ON wf.fieldlabel = h.indexid AND h.languageid = 7 "
                "WHERE qc.customid = %s "
                "ORDER BY qc.orderid",
                (query_id,)
            )
            result = []
            for row in cursor.fetchall():
                result.append({
                    "field_id": int(row[0]) if row[0] else 0,
                    "custom_name": self._decode(row[1]),
                    "field_type": int(row[2]) if row[2] else 5,
                    "order_id": int(row[3]) if row[3] else 0,
                    "group_id": int(row[4]) if row[4] else 0,
                    "show_model": int(row[5]) if row[5] else 0,
                    "cube_uuid": str(row[6] or ""),
                    "field_name": str(row[7] or ""),
                    "field_label": self._decode(row[8]),
                })
            return result
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  更新快捷搜索条件
    # ============================================================

    @expose(
        description="修改已有快捷搜索条件的配置（名称、类型、顺序、显示模式等）",
        examples=[
            {"query_id": 2732, "field_id": 12345, "custom_name": "房间编号"},
            {"query_id": 2732, "field_id": 12345, "order_id": 2, "show_model": 1},
        ],
        error_hints={
            "条件不存在": "请先用 add_quicksearch_condition 添加该条件"
        }
    )
    def update_quicksearch_condition(
        self,
        query_id: int,
        field_id: int,
        custom_name: str = None,
        field_type: int = None,
        order_id: int = None,
        group_id: int = None,
        show_model: int = None,
    ) -> Dict:
        """
        更新快捷搜索条件

        :param query_id: 查询 ID（必填）
        :param field_id: 字段 ID（必填，联合主键）
        :param custom_name: 新显示名称（选填）
        :param field_type: 新字段类型（选填）
        :param order_id: 新显示顺序（选填）
        :param group_id: 新分组 ID（选填）
        :param show_model: 新显示模式（选填）
        :return: {"query_id": int, "field_id": int, "status": "updated"}
        """
        if not query_id:
            raise ValueError("查询 ID 不能为空")
        if not field_id:
            raise ValueError("字段 ID 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 验证条件存在
            cursor.execute(
                "SELECT id FROM mode_quicksearch_condition WHERE customid = %s AND fieldid = %s",
                (query_id, field_id)
            )
            if not cursor.fetchone():
                raise ValueError(
                    "快捷搜索条件不存在，query_id=%d, field_id=%d" % (query_id, field_id)
                )

            updates = []
            params = []

            if custom_name is not None:
                updates.append("customname = %s")
                params.append(self._encode(custom_name))

            if field_type is not None:
                updates.append("type = %s")
                params.append(field_type)

            if order_id is not None:
                updates.append("orderid = %s")
                params.append(order_id)

            if group_id is not None:
                updates.append("groupid = %s")
                params.append(group_id)

            if show_model is not None:
                updates.append("showmodel = %s")
                params.append(show_model)

            if updates:
                params.extend([query_id, field_id])
                cursor.execute(
                    "UPDATE mode_quicksearch_condition SET %s WHERE customid = %s AND fieldid = %s" %
                    (", ".join(updates), "%s", "%s"),
                    params
                )
                conn.commit()
                self._clear_cache()

            return {"query_id": query_id, "field_id": field_id, "status": "updated"}

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  删除快捷搜索条件
    # ============================================================

    @expose(
        description="删除查询列表的一个快捷搜索条件",
        examples=[
            {"query_id": 2732, "field_id": 12345},
        ],
        destructive=True
    )
    def delete_quicksearch_condition(
        self,
        query_id: int,
        field_id: int,
    ) -> Dict:
        """
        删除快捷搜索条件

        :param query_id: 查询 ID（必填）
        :param field_id: 字段 ID（必填）
        :return: {"query_id": int, "field_id": int, "status": "deleted"}
        """
        if not query_id:
            raise ValueError("查询 ID 不能为空")
        if not field_id:
            raise ValueError("字段 ID 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM mode_quicksearch_condition WHERE customid = %s AND fieldid = %s",
                (query_id, field_id)
            )
            conn.commit()
            self._clear_cache()

            return {"query_id": query_id, "field_id": field_id, "status": "deleted"}

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  删除所有快捷搜索条件（含主配置）
    # ============================================================

    @expose(
        description="删除查询列表的所有快捷搜索条件及主配置",
        examples=[
            {"query_id": 2732},
        ],
        destructive=True
    )
    def delete_all_quicksearch_conditions(
        self,
        query_id: int,
    ) -> Dict:
        """
        删除所有快捷搜索条件及主配置

        :param query_id: 查询 ID（必填）
        :return: {"query_id": int, "conditions_deleted": int, "setting_deleted": bool}
        """
        if not query_id:
            raise ValueError("查询 ID 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 删除条件
            cursor.execute(
                "DELETE FROM mode_quicksearch_condition WHERE customid = %s",
                (query_id,)
            )
            conditions_deleted = cursor.rowcount

            # 删除主配置
            cursor.execute(
                "DELETE FROM mode_quicksearch_setting WHERE customid = %s",
                (query_id,)
            )
            setting_deleted = cursor.rowcount > 0

            conn.commit()
            self._clear_cache()

            return {
                "query_id": query_id,
                "conditions_deleted": conditions_deleted,
                "setting_deleted": setting_deleted
            }

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
