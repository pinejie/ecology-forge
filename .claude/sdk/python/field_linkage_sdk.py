# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 字段联动（Field Linkage）

通过直连 SQL Server 数据库，封装字段联动的 CRUD 操作。
字段联动：当某个字段的值变化时，自动从数据库查询数据并填充到其他字段。

依赖：pip install pymssql

存储结构：
    modeDataInputentry（联动规则入口）
      └→ modeDataInputmain（条件设置 + 数据源）
           ├→ modeDataInputtable（引用表配置）
           └→ modeDataInputfield（字段映射：Type=1条件 / Type=2赋值）

使用示例：
    from field_linkage_sdk import FieldLinkageSDK

    sdk = XXX()  # 配置从 db-config.md 读取

    # 查询模块现有联动规则
    rules = sdk.list_linkages(module_id=2405)

    # 创建联动规则
    entry_id = sdk.create_linkage(
        module_id=2405,
        trigger_field_id=30238,
        trigger_field_type=0,
        trigger_name="带出房间号",
        datasource="$ECOLOGY_SYS_LOCAL_POOLNAME",
        tables=[{"tablename": "uf_ss", "alias": "", "formid": ""}],
        conditions=[{"db_field": "mc", "target_field_id": 30238, "condition": 0}],
        assignments=[{"db_field": "mc", "target_field_id": 30256}],
    )
"""

import pymssql
import os
import uuid
from typing import List, Dict, Optional

from mcp_register import expose
from db_config import load_db_config


class FieldLinkageSDK:
    """建模引擎 SDK — 字段联动操作"""

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
            database=self.database,
            charset="cp936"
        )

    def _clear_cache(self):
        pass

    def _encode(self, s):
        """字符串编码为 cp936 bytes，保证中文正确存入 SQL Server"""
        if s is None:
            return ""
        return str(s).encode("cp936")

    def _decode(self, b):
        """cp936 bytes 解码为字符串"""
        if isinstance(b, bytes):
            return b.decode("cp936")
        return str(b or "")

    # ============================================================
    #  查询联动规则
    # ============================================================

    @expose(
        description="查询泛微 OA 建模引擎中模块的字段联动规则列表",
        examples=[
            {"module_id": 2405},
        ],
        read_only=True
    )
    def list_linkages(self, module_id: int) -> List[Dict]:
        """
        查询模块的字段联动规则列表

        :param module_id: 模块 ID
        :return: 联动规则列表
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, modeid, triggerName, triggerfieldname, type, detailindex, isenabled, isdel, isecme, isesb "
                "FROM modeDataInputentry WHERE modeid = %s AND isdel = 0 ORDER BY id",
                (module_id,)
            )
            result = []
            for row in cursor.fetchall():
                entry_id = int(row[0])
                rule = {
                    "id": entry_id,
                    "modeid": int(row[1]),
                    "trigger_name": self._decode(row[2]),
                    "trigger_field": self._decode(row[3]),
                    "type": str(row[4] or "0"),
                    "detailindex": str(row[5] or ""),
                    "isenabled": int(row[6]),
                    "isdel": int(row[7]),
                }

                # 查询条件设置（main）
                cursor.execute(
                    "SELECT id, entryID, WhereClause, IsCycle, OrderID, datasourcename "
                    "FROM modeDataInputmain WHERE entryID = %s ORDER BY OrderID",
                    (entry_id,)
                )
                mains = []
                for m_row in cursor.fetchall():
                    main_id = int(m_row[0])
                    main = {
                        "id": main_id,
                        "entryID": int(m_row[1]),
                        "where_clause": str(m_row[2] or ""),
                        "is_cycle": int(m_row[3]),
                        "order_id": int(m_row[4]),
                        "datasource": str(m_row[5] or ""),
                    }

                    # 引用表
                    cursor.execute(
                        "SELECT id, DataInputID, TableName, Alias, FormId "
                        "FROM modeDataInputtable WHERE DataInputID = %s",
                        (main_id,)
                    )
                    main["tables"] = [
                        {"id": int(t[0]), "tablename": str(t[2] or ""), "alias": str(t[3] or ""), "formid": str(t[4] or "")}
                        for t in cursor.fetchall()
                    ]

                    # 字段映射
                    cursor.execute(
                        "SELECT id, DataInputID, TableID, Type, DBFieldName, PageFieldName, conditions "
                        "FROM modeDataInputfield WHERE DataInputID = %s ORDER BY pagefieldindex",
                        (main_id,)
                    )
                    main["fields"] = [
                        {
                            "id": int(f[0]),
                            "type": int(f[3]),
                            "db_field": str(f[4] or ""),
                            "page_field": str(f[5] or ""),
                            "conditions": int(f[6]) if f[6] is not None else None,
                        }
                        for f in cursor.fetchall()
                    ]
                    mains.append(main)

                rule["mains"] = mains
                result.append(rule)
            return result
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  创建联动规则
    # ============================================================

    @expose(
        description="在泛微 OA 建模引擎中创建字段联动规则。全量替换模式：若模块已有同名触发字段的规则，先删除旧规则再插入。",
        examples=[
            {
                "module_id": 2405,
                "trigger_field_id": 30238,
                "trigger_field_type": 0,
                "trigger_name": "带出房间号",
                "datasource": "$ECOLOGY_SYS_LOCAL_POOLNAME",
                "tables": [{"tablename": "uf_ss", "alias": "", "formid": ""}],
                "conditions": [{"db_field": "mc", "target_field_id": 30238, "condition": 0}],
                "assignments": [{"db_field": "mc", "target_field_id": 30256}],
            }
        ],
        destructive=True
    )
    def create_linkage(
        self,
        module_id: int,
        trigger_field_id: int,
        trigger_field_type: int = 0,
        trigger_name: str = "",
        datasource: str = "$ECOLOGY_SYS_LOCAL_POOLNAME",
        tables: List[Dict] = None,
        conditions: List[Dict] = None,
        assignments: List[Dict] = None,
        detailindex: str = "0",
        isenabled: int = 1,
    ) -> int:
        """
        创建字段联动规则

        :param module_id: 模块 ID
        :param trigger_field_id: 触发字段 ID（workflow_billfield.id）
        :param trigger_field_type: 0=主表，1=明细表
        :param trigger_name: 联动名称（如"带出房间号"）
        :param datasource: 数据源名称，默认 $ECOLOGY_SYS_LOCAL_POOLNAME
        :param tables: 引用表列表，格式 [{"tablename": "HrmResource", "alias": "r", "formid": ""}]
        :param conditions: 条件字段列表，格式 [{"db_field": "id", "target_field_id": 30238, "condition": 0}]
        :param assignments: 赋值字段列表，格式 [{"db_field": "lastname", "target_field_id": 30235}]
        :param detailindex: 明细表标识，主表="0"，明细表=明细表 orderid
        :param isenabled: 1=启用，0=禁用
        :return: 新建规则的 entry_id
        """
        if not trigger_name:
            raise ValueError("trigger_name 不能为空")
        if not tables:
            raise ValueError("tables 不能为空")
        if not conditions:
            raise ValueError("conditions 不能为空")
        if not assignments:
            raise ValueError("assignments 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 全量替换：删除同名触发字段的旧规则
            trigger_field_str = "field%d" % trigger_field_id
            cursor.execute(
                "SELECT id FROM modeDataInputentry "
                "WHERE modeid = %s AND triggerfieldname = %s AND isdel = 0",
                (module_id, trigger_field_str)
            )
            old_ids = [int(r[0]) for r in cursor.fetchall()]
            for old_id in old_ids:
                cursor.execute("DELETE FROM modeDataInputfield WHERE DataInputID IN (SELECT id FROM modeDataInputmain WHERE entryID = %s)", (old_id,))
                cursor.execute("DELETE FROM modeDataInputtable WHERE DataInputID IN (SELECT id FROM modeDataInputmain WHERE entryID = %s)", (old_id,))
                cursor.execute("DELETE FROM modeDataInputmain WHERE entryID = %s", (old_id,))
                cursor.execute("DELETE FROM modeDataInputentry WHERE id = %s", (old_id,))

            cube_uuid = str(uuid.uuid4()).upper().replace("-", "")

            # 1. 插入 entry
            cursor.execute(
                "INSERT INTO modeDataInputentry "
                "(modeid, triggerName, triggerfieldname, type, detailindex, isenabled, isdel, isecme, isesb, cubeuuid) "
                "VALUES (%s, %s, %s, '0', %s, %s, 0, 0, 0, %s)",
                (module_id, self._encode(trigger_name), trigger_field_str, detailindex, isenabled, cube_uuid)
            )
            cursor.execute("SELECT max(id) AS entryId FROM modeDataInputentry")
            entry_id = int(cursor.fetchone()[0])

            # 2. 插入 main
            cursor.execute(
                "INSERT INTO modeDataInputmain "
                "(entryID, WhereClause, IsCycle, OrderID, datasourcename, cubeuuid) "
                "VALUES (%s, '', 1, 1, %s, %s)",
                (entry_id, datasource, cube_uuid)
            )
            cursor.execute("SELECT max(id) AS DataInputID FROM modeDataInputmain")
            main_id = int(cursor.fetchone()[0])

            # 3. 插入 tables
            for tbl in tables:
                cursor.execute(
                    "INSERT INTO modeDataInputtable (DataInputID, TableName, Alias, FormId, cubeuuid) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (main_id, tbl.get("tablename", ""), tbl.get("alias", ""), tbl.get("formid", ""), cube_uuid)
                )

            # 4. 插入 conditions (Type=1)
            for i, cond in enumerate(conditions):
                # 根据 db_field 匹配对应的 table
                db_field_full = cond.get("db_field", "")
                table_id = self._find_table_id(cursor, main_id, db_field_full, tables)
                cursor.execute(
                    "INSERT INTO modeDataInputfield "
                    "(DataInputID, TableID, Type, DBFieldName, PageFieldName, treenodeid, pagefieldindex, conditions, cubeuuid) "
                    "VALUES (%s, %s, 1, %s, 'field%s', '', 0, %s, %s)",
                    (main_id, table_id, db_field_full, cond["target_field_id"], cond.get("condition", 0), cube_uuid)
                )

            # 5. 插入 assignments (Type=2)
            for i, asgn in enumerate(assignments):
                db_field_full = asgn.get("db_field", "")
                table_id = self._find_table_id(cursor, main_id, db_field_full, tables)
                cursor.execute(
                    "INSERT INTO modeDataInputfield "
                    "(DataInputID, TableID, Type, DBFieldName, PageFieldName, treenodeid, pagefieldindex, conditions, cubeuuid) "
                    "VALUES (%s, %s, 2, %s, 'field%s', '', 0, NULL, %s)",
                    (main_id, table_id, db_field_full, asgn["target_field_id"], cube_uuid)
                )

            conn.commit()
            self._clear_cache()
            return entry_id
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  删除联动规则
    # ============================================================

    @expose(
        description="物理删除泛微 OA 建模引擎中的字段联动规则及所有关联数据",
        examples=[
            {"entry_id": 106},
        ],
        destructive=True
    )
    def delete_linkage(self, entry_id: int):
        """
        物理删除字段联动规则

        :param entry_id: 联动规则 entry ID
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM modeDataInputmain WHERE entryID = %s", (entry_id,))
            main_ids = [int(r[0]) for r in cursor.fetchall()]
            for mid in main_ids:
                cursor.execute("DELETE FROM modeDataInputfield WHERE DataInputID = %s", (mid,))
                cursor.execute("DELETE FROM modeDataInputtable WHERE DataInputID = %s", (mid,))
                cursor.execute("DELETE FROM modeDataInputmain WHERE entryID = %s", (entry_id,))
            cursor.execute("DELETE FROM modeDataInputentry WHERE id = %s", (entry_id,))
            conn.commit()
            self._clear_cache()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  切换启用状态
    # ============================================================

    @expose(
        description="切换字段联动规则的启用/禁用状态",
        examples=[
            {"entry_id": 106, "isenabled": 0},
        ]
    )
    def toggle_enabled(self, entry_id: int, isenabled: int):
        """
        切换联动规则启用状态

        :param entry_id: 联动规则 entry ID
        :param isenabled: 1=启用，0=禁用
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE modeDataInputentry SET isenabled = %s WHERE id = %s",
                (isenabled, entry_id)
            )
            conn.commit()
            self._clear_cache()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  内部方法
    # ============================================================

    def _find_table_id(self, cursor, main_id: int, db_field: str, tables: List[Dict]) -> int:
        """根据数据库字段名找到对应的 modeDataInputtable.id"""
        # 从 db_field 提取表别名前缀（如 "r.departmentid" → "r"）
        parts = db_field.split(".")
        alias = parts[0] if len(parts) > 1 else ""

        cursor.execute(
            "SELECT id FROM modeDataInputtable WHERE DataInputID = %s",
            (main_id,)
        )
        for row in cursor.fetchall():
            tid = int(row[0])
            cursor.execute("SELECT Alias FROM modeDataInputtable WHERE id = %s", (tid,))
            t_alias = cursor.fetchone()[0] or ""
            # 如果别名匹配，或者没有别名且只有一张表
            if alias and t_alias == alias:
                return tid
            elif not alias and len(tables) == 1:
                return tid

        # 兜底：返回第一张表的 ID
        cursor.execute("SELECT TOP 1 id FROM modeDataInputtable WHERE DataInputID = %s", (main_id,))
        row = cursor.fetchone()
        return int(row[0]) if row else 0
