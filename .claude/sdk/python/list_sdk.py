# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 查询列表（List/Query）

通过直连 SQL Server 数据库，封装查询列表配置的 CRUD 操作。
查询列表：模块页面顶部的"查询"功能，用户可保存多个查询条件组合。

依赖：pip install pymssql

存储结构：
    mode_customsearch — 查询配置主表
      └→ mode_CustomDspField — 查询显示字段配置（由其他方法管理）

使用示例：
    from list_sdk import ListSDK

    sdk = XXX()  # 配置从 db-config.md 读取

    # 创建查询
    query_id = sdk.create_query(
        name="按部门查询",
        mode_id=2405,
        app_id=1066,
        form_id=-1013,
        desc="按部门筛选所有记录",
    )
"""

import pymssql
import os
import uuid
from typing import List, Dict, Optional

from mcp_register import expose
from db_config import load_db_config


class ListSDK:
    """建模引擎 SDK — 查询列表操作"""

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

    def _encode(self, s):
        """字符串编码为 cp936 bytes，保证中文正确传入 SQL Server"""
        if s is None:
            return ""
        return str(s).encode("cp936")

    def _decode(self, val):
        """SQL Server varchar 列读取还原：pymssql 默认 latin1 解码，需先转回字节再 GBK 解码"""
        if val is None:
            return ""
        if isinstance(val, str):
            try:
                return val.encode("latin1").decode("gbk")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return val
        return str(val)

    def _clear_cache(self):
        """清除建模缓存"""
        pass

    def _create_batch_set(self, cursor, mode_id: int, customsearchid: int):
        """
        为新建查询创建 mode_batchset 记录。
        读取模块的页面扩展（mode_pageexpand），筛选出需要批量操作的按钮，
        在 mode_batchset 中建立 expandid <-> customsearchid 的关联。
        幂等：先查已有数据，若有则先删再插。
        """
        cube_uuid = str(uuid.uuid4()).upper().replace("-", "")

        # 幂等：先查该查询是否已有 batchset 记录
        cursor.execute("SELECT COUNT(*) FROM mode_batchset WHERE customsearchid = %s", (customsearchid,))
        existing_count = int(cursor.fetchone()[0])
        if existing_count > 0:
            cursor.execute("DELETE FROM mode_batchset WHERE customsearchid = %s", (customsearchid,))

        # 查询模块的页面扩展（查全部，不过滤 isshow）
        cursor.execute("""
            SELECT id, expendname, showorder
            FROM mode_pageexpand
            WHERE modeid = %s
            ORDER BY showorder, id
        """, (mode_id,))
        expands = {}
        for row in cursor.fetchall():
            try:
                name = row[1].encode('latin1').decode('gbk') if row[1] else ''
            except:
                name = str(row[1] or '')
            expands[name] = {"id": int(row[0]), "order": float(row[2])}

        # 需要创建 batchset 的按钮（与建模引擎页面创建模块时保持一致）
        batch_names = [
            ("搜索",           0.00,   1, "搜索",           0),
            ("新建",           101.00, 1, "新建",           1),
            ("批量新增",       101.50, 0, "批量新增",       0),
            ("删除",           102.00, 1, "删除",           0),
            ("批量导入",       103.00, 1, "批量导入",       0),
            ("批量共享",       104.00, 1, "批量共享",       0),
            ("导出",           105.00, 1, "导出",           0),
            ("显示列定制",     106.00, 0, "显示列定制",     0),
            ("地图页面",       110.00, 0, "地图页面",       0),
            ("批量生成二维码", 169.00, 0, "批量生成二维码", 0),
            ("批量生成条形码", 171.00, 0, "批量生成条形码", 0),
            ("批量打印",       172.00, 0, "批量打印",       0),
        ]

        for name, order, isuse, lbname, isshortcut in batch_names:
            if name not in expands:
                continue
            expandid = expands[name]["id"]
            cursor.execute(
                "INSERT INTO mode_batchset "
                "(expandid, showorder, customsearchid, isuse, listbatchname, "
                "isshortcutbutton, isfilter, conditiontype, conditionsql, conditiontext, cubeuuid) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (expandid, order, customsearchid, isuse, self._encode(lbname),
                 isshortcut, 0, None, "", "", cube_uuid)
            )

    # ============================================================
    #  创建查询
    # ============================================================

    @expose(
        description="在泛微 OA 建模引擎中创建一个查询列表配置（总入口）。写入 mode_customsearch 表后，"
                    "自动调用 save_formfields 保存 AI 分析后的字段定义（需传入 fields 参数），"
                    "同时自动追加系统字段 -1/-2。不传 fields 则仅创建查询基础信息。",
        examples=[
            {"name": "按部门查询", "mode_id": 2405, "app_id": 1066, "form_id": -1013, "desc": "按部门筛选所有记录"},
            {"name": "未处理单据", "mode_id": 2381, "app_id": 1062, "form_id": -861, "desc": "筛选状态为未处理的单据", "pagenumber": 20, "enabled": 1, "fields": [
                {"field_id": 123, "is_show": True, "show_order": 1, "is_order_field": 1, "link_type": "form"},
                {"field_id": 456, "is_show": True, "show_order": 2, "is_query": True, "link_type": "form"}
            ]},
        ],
        error_hints={
            "查询名称不能为空": "name 参数必填",
            "模块不存在": "请检查 mode_id 是否正确"
        }
    )
    def create_query(
        self,
        name: str,
        mode_id: int,
        app_id: int,
        form_id: int,
        desc: str = "",
        data_show_type: int = 0,
        open_type: int = 2,
        slider_percentage: int = 80,
        page_number: int = 10,
        enabled: int = 0,
        is_custom: int = 1,
        dis_quick_search: int = 1,
        is_show_query_condition: int = 0,
        fixed_number_forth: int = 0,
        fixed_number_back: int = 0,
        show_order: float = -1,
        fields: List[Dict] = None,
    ) -> int:
        """
        创建查询列表配置

        :param name: 查询名称（必填）
        :param mode_id: 模块 ID（必填）
        :param app_id: 应用 ID（必填）
        :param form_id: 表单 ID（必填，负数表示主表）
        :param desc: 查询描述（选填），建议根据查询含义书写
        :param data_show_type: 数据显示模式，0=列表(默认)，2=excel列表，5=纵向展示列表
        :param open_type: 数据打开方式，0=弹出窗口，1=当前窗口，2=滑动窗口(默认)
        :param slider_percentage: 打开页面占比（滑动窗口百分比），默认 80%
        :param page_number: 每页显示记录数，默认 10
        :param enabled: 是否启用，0=禁用(默认)，1=启用
        :param is_custom: 是否自定义查询，1=是(默认)
        :param dis_quick_search: 是否显示快速搜索，1=显示(默认)
        :param is_show_query_condition: 是否显示查询条件面板，0=不显示(默认)
        :param fixed_number_forth: 前列冻结数，默认 0
        :param fixed_number_back: 后列冻结数，默认 0
        :param show_order: 显示顺序，默认 -1（自动排序）
        :param fields: 字段定义列表（选填），传入后自动调用 save_formfields 保存字段配置。
                       每个字段格式参考 save_formfields 方法的 fields 参数。
                       系统字段 -1/-2 会自动追加到列表末尾。
        :return: 新建查询的 ID
        """
        if not name or not name.strip():
            raise ValueError("查询名称不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 验证模块存在
            cursor.execute(
                "SELECT id FROM modeinfo WHERE id = %s AND isdelete = 0",
                (mode_id,)
            )
            if not cursor.fetchone():
                raise ValueError("模块不存在，ID=%d" % mode_id)

            cube_uuid = str(uuid.uuid4()).upper().replace("-", "")
            search_code = uuid.uuid4().hex

            cursor.execute(
                "INSERT INTO mode_customsearch "
                "(customname, customdesc, modeid, appid, formid, "
                "datashowtype, opentype, sliderPercentage, pagenumber, "
                "enabled, iscustom, disQuickSearch, isShowQueryCondition, "
                "fixednumberForth, fixednumberBack, dsporder, "
                "detailtable, norightlist, secondPassword, syncexport, "
                "cubeuuid, customsearchcode) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    self._encode(name),
                    self._encode(desc),
                    mode_id,
                    app_id,
                    form_id,
                    data_show_type,
                    open_type,
                    str(slider_percentage),
                    page_number,
                    enabled,
                    is_custom,
                    dis_quick_search,
                    is_show_query_condition,
                    fixed_number_forth,
                    fixed_number_back,
                    show_order,
                    "",        # detailtable
                    "0",       # norightlist
                    "0",       # secondPassword
                    "1",       # syncexport
                    cube_uuid,
                    search_code
                )
            )
            conn.commit()

            # 获取新建 ID
            cursor.execute("SELECT MAX(id) AS newId FROM mode_customsearch")
            row = cursor.fetchone()
            new_id = int(row[0]) if row else -1

            if new_id > 0:
                conn.commit()

                if fields:
                    # AI 思考的字段定义 + 系统字段
                    sys_fields = [
                        {"field_id": -1, "is_show": True, "show_order": len(fields) + 1},
                        {"field_id": -2, "is_show": True, "show_order": len(fields) + 2},
                    ]
                    all_fields = fields + sys_fields
                else:
                    # 无 AI fields，自动读取表单字段，用默认策略
                    cursor.execute(
                        "SELECT id FROM workflow_billfield WHERE billid = %s ORDER BY dsporder",
                        (form_id,)
                    )
                    form_fields = cursor.fetchall()
                    all_fields = []
                    for i, f in enumerate(form_fields):
                        all_fields.append({
                            "field_id": int(f[0]),
                            "is_show": True,
                            "show_order": i + 1,
                            "link_type": "form",
                        })
                    # 追加系统字段
                    all_fields.append({"field_id": -1, "is_show": True, "show_order": len(all_fields) + 1})
                    all_fields.append({"field_id": -2, "is_show": True, "show_order": len(all_fields) + 1})

                self.save_formfields(new_id, all_fields)

                # 自动添加"所有人可看"查看权限
                cursor.execute(
                    "INSERT INTO mode_searchPageshareinfo "
                    "(pageid, righttype, sharetype, relatedid, rolelevel, "
                    "showlevel, showlevel2, joblevel, cubeuuid) "
                    "VALUES (%s, 1, 5, 0, 0, 0, 100, 2, %s)",
                    (new_id, str(uuid.uuid4()).upper().replace("-", ""))
                )

                # 自动创建 mode_batchset（页面扩展与查询的关联）
                self._create_batch_set(cursor, mode_id, new_id)

                # 快捷搜索不自动创建，由 AI 根据业务场景分析后通过 QuickSearchSDK 手动添加
                # 详细规则见 .claude/rules/modeling-rules.md 3.9

                conn.commit()

            self._clear_cache()
            return new_id

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  查询列表
    # ============================================================

    @expose(
        description="查询泛微 OA 建模引擎中模块的查询列表配置",
        examples=[
            {"mode_id": 2405},
            {}
        ],
        read_only=True
    )
    def list_queries(self, mode_id: int = None) -> List[Dict]:
        """
        查询列表配置

        :param mode_id: 模块 ID，不传则查所有
        :return: 查询列表 [{"id": ..., "name": ..., "desc": ..., "mode_id": ..., ...}]
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            if mode_id is not None:
                cursor.execute(
                    "SELECT id, customname, customdesc, modeid, appid, formid, "
                    "datashowtype, opentype, sliderPercentage, pagenumber, "
                    "enabled, iscustom, disQuickSearch, isShowQueryCondition, "
                    "fixednumberForth, fixednumberBack, dsporder, customsearchcode "
                    "FROM mode_customsearch WHERE modeid = %s "
                    "ORDER BY dsporder, id",
                    (mode_id,)
                )
            else:
                cursor.execute(
                    "SELECT id, customname, customdesc, modeid, appid, formid, "
                    "datashowtype, opentype, sliderPercentage, pagenumber, "
                    "enabled, iscustom, disQuickSearch, isShowQueryCondition, "
                    "fixednumberForth, fixednumberBack, dsporder, customsearchcode "
                    "FROM mode_customsearch "
                    "ORDER BY modeid, dsporder, id"
                )

            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": int(row[0]),
                    "name": str(row[1] or ""),
                    "desc": str(row[2] or ""),
                    "mode_id": int(row[3]) if row[3] else 0,
                    "app_id": int(row[4]) if row[4] else 0,
                    "form_id": int(row[5]) if row[5] else 0,
                    "data_show_type": int(row[6]) if row[6] else 0,
                    "open_type": int(row[7]) if row[7] else 0,
                    "slider_percentage": str(row[8] or ""),
                    "page_number": int(row[9]) if row[9] else 0,
                    "enabled": int(row[10]),
                    "is_custom": int(row[11]) if row[11] else 0,
                    "dis_quick_search": int(row[12]) if row[12] else 0,
                    "is_show_query_condition": int(row[13]) if row[13] else 0,
                    "fixed_number_forth": int(row[14]) if row[14] else 0,
                    "fixed_number_back": int(row[15]) if row[15] else 0,
                    "show_order": row[16],
                    "search_code": str(row[17] or ""),
                })
            return result
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  更新查询
    # ============================================================

    @expose(
        description="修改泛微 OA 建模引擎中已有查询列表的名称、描述或配置",
        examples=[
            {"query_id": 2732, "new_name": "新查询名称"},
            {"query_id": 2732, "enabled": 1}
        ]
    )
    def update_query(
        self,
        query_id: int,
        new_name: str = None,
        new_desc: str = None,
        enabled: int = None,
        page_number: int = None,
        slider_percentage: int = None,
    ):
        """
        更新查询配置

        :param query_id: 查询 ID（必填）
        :param new_name: 新名称（选填）
        :param new_desc: 新描述（选填）
        :param enabled: 启用状态，0=禁用，1=启用（选填）
        :param page_number: 每页条数（选填）
        :param slider_percentage: 滑动窗口百分比（选填）
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id FROM mode_customsearch WHERE id = %s",
                (query_id,)
            )
            if not cursor.fetchone():
                raise ValueError("查询不存在，ID=%d" % query_id)

            updates = []
            params = []

            if new_name is not None:
                updates.append("customname = %s")
                updates.append("customdesc = %s")
                params.extend([self._encode(new_name), self._encode(new_name)])

            if new_desc is not None:
                updates.append("customdesc = %s")
                params.append(self._encode(new_desc))

            if enabled is not None:
                updates.append("enabled = %s")
                params.append(enabled)

            if page_number is not None:
                updates.append("pagenumber = %s")
                params.append(page_number)

            if slider_percentage is not None:
                updates.append("sliderPercentage = %s")
                params.append(str(slider_percentage))

            if updates:
                params.append(query_id)
                cursor.execute(
                    "UPDATE mode_customsearch SET %s WHERE id = %s" %
                    (", ".join(updates), "%s"),
                    params
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
    #  删除查询
    # ============================================================

    @expose(
        description="物理删除泛微 OA 建模引擎中的查询列表配置及关联显示字段",
        examples=[
            {"query_id": 2732}
        ],
        destructive=True
    )
    def delete_query(self, query_id: int) -> Dict:
        """
        删除查询配置（物理删除）

        :param query_id: 查询 ID（必填）
        :return: {"query_id": int, "status": "deleted"}
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 确认查询存在
            cursor.execute("SELECT id, customname FROM mode_customsearch WHERE id = %s", (query_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("查询不存在，ID=%d" % query_id)

            # 先删 mode_batchset（批量操作关联）
            cursor.execute(
                "DELETE FROM mode_batchset WHERE customsearchid = %s",
                (query_id,)
            )
            # 再删 mode_searchPageshareinfo（查询查看权限）
            cursor.execute(
                "DELETE FROM mode_searchPageshareinfo WHERE pageid = %s",
                (query_id,)
            )
            # 再删 mode_quicksearch_condition（快捷搜索条件）
            cursor.execute(
                "DELETE FROM mode_quicksearch_condition WHERE customid = %s",
                (query_id,)
            )
            # 再删关联显示字段
            cursor.execute(
                "DELETE FROM mode_CustomDspField WHERE customid = %s",
                (query_id,)
            )
            # 最后删主记录
            cursor.execute(
                "DELETE FROM mode_customsearch WHERE id = %s",
                (query_id,)
            )
            conn.commit()
            self._clear_cache()
            return {"query_id": query_id, "status": "deleted"}
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  保存查询字段定义（显示字段/查询条件/标题列等）
    # ============================================================

    @expose(
        description="保存泛微 OA 查询列表的字段定义（显示、查询、排序、链接等）。写入 mode_CustomDspField 表。",
        examples=[
            {"query_id": 2766, "fields": [
                {"field_id": 100, "is_show": True, "show_order": 1, "col_width": 150},
                {"field_id": 101, "is_show": True, "is_query": True, "is_order_field": True, "pri_order": "asc", "show_order": 2, "col_width": 120},
                {"field_id": 102, "is_show": True, "link_type": "workflow", "link_field": "fwdlc", "show_order": 3},
            ]},
        ],
        error_hints={
            "查询不存在": "请检查 query_id 是否正确",
            "字段不存在": "field_id 必须在 workflow_billfield 表中存在"
        }
    )
    def save_formfields(
        self,
        query_id: int,
        fields: List[Dict],
    ) -> int:
        """
        保存查询的字段定义（先删后插）

        :param query_id: 查询 ID（必填）
        :param fields: 字段列表，每项格式：
            {
                "field_id": 字段 ID（workflow_billfield.id，必填），
                "is_show": 是否显示在列表（默认 True），
                "is_query": 是否可查询（默认 False），
                "is_advanced_query": 是否高级查询（默认 False），
                "show_order": 显示顺序（从 1 开始），
                "query_order": 查询条件顺序（默认 0），
                "advanced_query_order": 高级查询顺序（默认 0），
                "is_key": 是否关键字（默认 0），
                "is_order_field": 是否可排序（默认 False），
                "pri_order": 排序类型，"asc"升序/"desc"降序（默认 ""），
                "ordernum": 排序优先级数字，1、2、3...（默认 0），
                "is_stat": 是否可统计（默认 False），
                "is_quick_search": 是否快捷搜索（默认 False），
                "quick_search_order": 快捷搜索顺序（默认 0），
                "link_type": 链接方式（"none"/"form"/"workflow"/"custom"，默认 "form"），
                "link_field": 链接关联的字段名（仅 workflow 类型需要），
            }

            链接方式说明（对应 istitle 字段）：
                - "form"（默认）：istitle=1，点击跳转到本模块表单详情页
                - "form"（默认）：istitle=1，表单建模，固定路径
                - "none"：istitle=0，无链接
                - "workflow"：istitle=2，工作流，用 link_field 指定存 requestid 的字段名
                - "custom"：istitle=3，自定义链接（暂不处理）
        :return: 保存的字段数量
        """
        if not query_id:
            raise ValueError("查询 ID 不能为空")
        if not fields:
            raise ValueError("字段列表不能为空")

        # 链接路径模板
        LINK_PATHS = {
            "form": "/spa/cube/index.html#/main/cube/card?type=$type$&modeId=$modeId$&formId=$formId$&billid=$billid$&opentype=$opentype$&customid=$customid$&viewfrom=$viewfrom$",
        }

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

            # 先删除该查询的旧字段定义和快捷搜索条件
            cursor.execute(
                "DELETE FROM mode_CustomDspField WHERE customid = %s",
                (query_id,)
            )
            cursor.execute(
                "DELETE FROM mode_quicksearch_condition WHERE customid = %s",
                (query_id,)
            )

            # 批量插入新字段
            for i, f in enumerate(fields):
                field_id = f.get("field_id")
                if not field_id:
                    raise ValueError("第 %d 个字段缺少 field_id" % (i + 1))

                # 验证字段存在（系统字段 -1/-2 跳过验证）
                if field_id > 0:
                    cursor.execute(
                        "SELECT id FROM workflow_billfield WHERE id = %s",
                        (field_id,)
                    )
                    if not cursor.fetchone():
                        raise ValueError("字段不存在，field_id=%d" % field_id)

                is_show = "1" if f.get("is_show", True) else "0"
                is_query = "1" if f.get("is_query", False) else "0"
                is_adv = "1" if f.get("is_advanced_query", False) else "0"
                is_key = f.get("is_key", 0)
                is_order = f.get("is_order_field", 0)
                pri_order = f.get("pri_order", "")
                is_stat = "1" if f.get("is_stat", False) else "0"
                show_order = f.get("show_order", i + 1)
                query_order = f.get("query_order", 0)
                adv_order = f.get("advanced_query_order", 0)
                col_width = 5

                # 排序字段：isorder(是否可排序)、ordertype(a升序/b降序)、ordernum(排序优先级)
                is_order = "1" if f.get("is_order_field", False) else "0"
                ordertype = f.get("pri_order", "")  # "asc"→a, "desc"→b
                if ordertype == "asc":
                    ordertype = "a"
                elif ordertype == "desc":
                    ordertype = "d"
                else:
                    ordertype = ""
                ordernum = f.get("ordernum", 0)

                # 处理链接方式 -> istitle，默认表单建模链接
                link_type = f.get("link_type", "form")
                link_field = f.get("link_field", "")

                if link_type == "form":
                    istitle = 1
                    href_link = LINK_PATHS["form"]
                elif link_type == "workflow":
                    istitle = 2
                    if not link_field:
                        raise ValueError("link_type 为 workflow 时，必须指定 link_field（存 requestid 的字段名）")
                    href_link = "/spa/workflow/index_form.jsp#/main/workflow/req?requestid=$%s$&isovertime=0" % link_field
                elif link_type == "custom":
                    istitle = 3
                    href_link = f.get("href_link", "")
                else:
                    istitle = 0
                    href_link = ""

                cursor.execute(
                    "INSERT INTO mode_CustomDspField ("
                    "customid, fieldid, isquery, isadvancedquery, isshow, "
                    "showorder, queryorder, advancedqueryorder, istitle, "
                    "colwidth, iskey, isorder, ordertype, ordernum, isstat, "
                    "hreflink, showmethod"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        query_id, field_id,
                        is_query, is_adv, is_show,
                        show_order, query_order, adv_order, istitle,
                        col_width, is_key, is_order, ordertype, ordernum, is_stat,
                        href_link, 0,
                    )
                )

                # 快捷搜索条件：写入 mode_quicksearch_condition 表
                is_quick_search = f.get("is_quick_search", False)
                quick_search_order = f.get("quick_search_order", 0)
                if is_quick_search:
                    # 获取字段名称
                    cursor.execute(
                        "SELECT fieldname FROM workflow_billfield WHERE id = %s",
                        (field_id,)
                    )
                    row = cursor.fetchone()
                    field_name = str(row[0] or "") if row else ""

                    # 获取字段类型（用于 type 字段）
                    cursor.execute(
                        "SELECT type FROM workflow_billfield WHERE id = %s",
                        (field_id,)
                    )
                    row = cursor.fetchone()
                    field_type = str(row[0] or "0") if row else "0"

                    cursor.execute(
                        "INSERT INTO mode_quicksearch_condition ("
                        "customid, fieldid, customname, type, orderid, groupid, showmodel, cubeuuid"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            query_id, field_id,
                            field_name, field_type,
                            quick_search_order, 0, 0, None
                        )
                    )

            conn.commit()
            self._clear_cache()
            return len(fields)

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  查询字段定义
    # ============================================================

    @expose(
        description="查询泛微 OA 查询列表的字段定义",
        examples=[{"query_id": 2761}],
        read_only=True
    )
    def get_formfields(self, query_id: int) -> List[Dict]:
        """
        查询字段定义

        :param query_id: 查询 ID
        :return: 字段列表
        """
        if not query_id:
            raise ValueError("查询 ID 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT mc.fieldid, mc.isquery, mc.isadvancedquery, mc.isshow, "
                "mc.showorder, mc.queryorder, mc.advancedqueryorder, mc.istitle, "
                "mc.colwidth, mc.iskey, mc.isorderfield, mc.priorder, mc.isstat, "
                "mc.hreflink, mc.showmethod, "
                "wb.fieldname, h.labelname "
                "FROM mode_CustomDspField mc "
                "LEFT JOIN workflow_billfield wb ON mc.fieldid = wb.id "
                "LEFT JOIN HtmlLabelInfo h ON wb.fieldlabel = h.indexid AND h.languageid = 7 "
                "WHERE mc.customid = %s "
                "ORDER BY mc.showorder, mc.id",
                (query_id,)
            )
            result = []
            for row in cursor.fetchall():
                try:
                    label = row[16].encode("latin1").decode("gbk") if row[16] else ""
                except Exception:
                    label = str(row[16] or "")
                result.append({
                    "field_id": int(row[0]) if row[0] else 0,
                    "field_name": str(row[15] or ""),
                    "field_label": label,
                    "is_query": row[1] == "1",
                    "is_advanced_query": row[2] == "1",
                    "is_show": row[3] == "1",
                    "show_order": int(row[4]) if row[4] else 0,
                    "query_order": int(row[5]) if row[5] else 0,
                    "advanced_query_order": int(row[6]),
                    "is_title": row[7] == "1",
                    "col_width": float(row[8]) if row[8] else 0,
                    "is_key": int(row[9]) if row[9] else 0,
                    "is_order_field": int(row[10]) if row[10] else 0,
                    "pri_order": str(row[11] or ""),
                    "is_stat": row[12] == "1",
                    "href_link": str(row[13] or ""),
                    "show_method": int(row[14]) if row[14] else 0,
                })
            return result
        finally:
            cursor.close()
            conn.close()
