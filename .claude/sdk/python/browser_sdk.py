# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 自定义浏览框（Browser）

通过直连 SQL Server 数据库，封装建模引擎的自定义浏览框创建操作。
SDK 只管执行，不做分析。调用前需完成字段角色分析（见 .claude/rules/modeling-rules.md 第4节）。

依赖：pip install pymssql requests

使用示例：
    from browser_sdk import BrowserSDK

    sdk = BrowserSDK(host="172.18.28.108", user="sa", password="Weaver@2001", database="ecology")

    # 创建浏览框（基础信息 + 字段定义 + 浏览按钮，一步到位）
    result = sdk.create_browser(
        name="届级管理",
        app_id=1076,
        form_id=-1036,
        fields=[
            {"field_id": 30759, "is_show": "1", "show_order": 1, "is_title": True},
            {"field_id": 30757, "is_show": "1", "show_order": 2},
            {"field_id": 30758, "is_show": "1", "show_order": 3},
            {"field_id": 30761, "is_show": "1", "is_query": "1", "show_order": 4, "query_order": 1},
            {"field_id": 30762, "is_show": "1", "show_order": 5},
        ],
        defaultsql="is_active='1'"
    )
"""

import pymssql
import os
import requests
import time
import uuid
from typing import List, Dict, Optional

from mcp_register import expose
from cache_sdk import refresh_label_cache
from db_config import load_db_config, load_oa_config


class BrowserSDK:
    """建模引擎自定义浏览框创建 SDK"""

    def __init__(self, host: str = None, user: str = None, password: str = None, database: str = None, port: int = None):
        defaults = load_db_config()
        self.host = host or defaults.get("host") or os.environ.get("OA_DB_HOST")
        self.user = user or defaults.get("user") or os.environ.get("OA_DB_USER")
        self.password = password or defaults.get("password") or os.environ.get("OA_DB_PASSWORD")
        self.database = database or defaults.get("database") or os.environ.get("OA_DB_DATABASE")
        self.port = port or defaults.get("port", 1433)
        if not self.password:
            raise RuntimeError("数据库密码未配置，请检查 .claude/sdk/pwd.md 或环境变量 OA_DB_PASSWORD")
        # OA 前端地址（用于调用 JSP 缓存刷新接口）
        self.oa_host = host or load_oa_config()["oa_host"]

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
        """Python Unicode → GBK bytes，适配 SQL Server varchar 列"""
        if s is None:
            return ""
        return str(s).encode("gbk")

    def _decode(self, val):
        """SQL Server varchar 列读取还原"""
        if val is None:
            return ""
        if isinstance(val, str):
            return val.encode("latin1").decode("gbk")
        return str(val)

    def _now_date(self):
        """返回当前日期字符串 YYYY-MM-DD"""
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def _now_time(self):
        """返回当前时间字符串 HH:MM:SS"""
        import datetime
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _get_next_id(self, cursor, table: str) -> int:
        """生成非自增表的下一个 ID（MAX(id)+1）"""
        for attempt in range(5):
            cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM %s" % table)
            row = cursor.fetchone()
            next_id = int(row[0]) if row else 1
            cursor.execute("SELECT COUNT(*) FROM %s WHERE id = %s" % (table, next_id))
            row = cursor.fetchone()
            if row and int(row[0]) == 0:
                return next_id
            time.sleep(0.05)
        raise ValueError("生成 ID 失败，请稍后重试")

    # ============================================================
    #  方法 1：保存浏览框基础信息
    #  对应 SaveOrUpdateCmd（id=0 走新增）
    # ============================================================

    def _save_browser_base(self, cursor, name: str, app_id: int, form_id: int,
                           showname: str,
                           mode_id: int = 0, description: str = "",
                           defaultsql: str = "", page_number: int = 10,
                           dsporder: float = -1.0, data_show_type: str = "0",
                           search_condition_type: str = "1",
                           is_display_draft_data: int = 0) -> int:
        """
        保存浏览框基础信息到 mode_custombrowser 表，并在 MODE_BROWSER 中插入 showname 映射。

        返回 (custom_id, browser_id)。
        """
        custom_id = self._get_next_id(cursor, "mode_custombrowser")

        # 启用 IDENTITY_INSERT
        cursor.execute("SET IDENTITY_INSERT mode_custombrowser ON")
        cursor.execute(
            "INSERT INTO mode_custombrowser "
            "(id, customname, customdesc, formid, appid, modeid, "
            "defaultsql, pagenumber, dsporder, datashowtype, searchconditiontype, "
            "norightlist, detailtable, javafilename, javafileAddress, "
            "datashowtypefilefield, datashowtypefileicon, isDisplayDraftData, "
            "cubeuuid) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NEWID())",
            (custom_id, self._encode(name), self._encode(description),
             form_id, app_id, mode_id, self._encode(defaultsql),
             page_number, dsporder, data_show_type, search_condition_type,
             self._encode(" "), self._encode(""),
             self._encode(""), self._encode(""),
             self._encode(""), self._encode(""),
             is_display_draft_data)
        )
        cursor.execute("SET IDENTITY_INSERT mode_custombrowser OFF")

        # 写入 MODE_BROWSER showname 映射（供 fielddbtype=browser.xxx 引用）
        # 如果 showname 已被活跃浏览框占用，追加时间戳
        cursor.execute(
            "SELECT COUNT(*) FROM MODE_BROWSER mb "
            "INNER JOIN mode_custombrowser mcb ON mb.customid = mcb.id "
            "WHERE mb.showname = %s",
            (showname,)
        )
        if cursor.fetchone()[0] > 0:
            showname = showname + str(int(time.time()))[-4:]
        cursor.execute(
            "INSERT INTO MODE_BROWSER (customid, showname) VALUES (%s, %s)",
            (custom_id, showname)
        )
        cursor.execute("SELECT SCOPE_IDENTITY()")
        browser_id = int(cursor.fetchone()[0])

        return custom_id, browser_id

    # ============================================================
    #  方法 2：字段定义
    #  对应 SaveFieldSetCmd
    # ============================================================

    def _save_field_set(self, cursor, custom_id: int, fields: List[Dict]):
        """
        保存浏览框字段定义到 mode_CustombrowserDspField 表。

        fields 列表中的每个元素：
            field_id: int       - workflow_billfield.id
            is_show: str        - "1" 显示, "0" 隐藏（默认"1"）
            show_order: int     - 展示顺序（默认 0）
            is_query: str       - "1" 可查询, "0" 不可（默认"0"）
            query_order: int    - 查询条件顺序（默认 0）
            is_title: bool/str  - True/"1" 为链接字段（默认 False）
            is_pk: 忽略，固定为 "0"（主键为表自带 id，不由字段定义控制）
            is_quick_search: str - "1" 快捷搜索, "0" 否（默认"0"）
            is_order: str       - "1" 可排序, "0" 否（默认"0"）
            order_type: str     - "a" 升序, "d" 降序（默认"a"）
            order_num: int      - 排序优先级（默认 0）
            col_width: int      - 列宽度（默认 0 自适应）
        """
        for field in fields:
            fid = field["field_id"]
            is_show = str(field.get("is_show", "1"))
            show_order = int(field.get("show_order", 0))
            is_query = str(field.get("is_query", "0"))
            is_query_default_display = is_query  # 查询条件默认显示
            query_order = int(field.get("query_order", 0))
            is_title = "1" if field.get("is_title", False) else "0"
            is_pk = "0"  # 主键固定为表自带 id，不允许字段定义标记
            is_quick = str(field.get("is_quick_search", "0"))
            is_order = str(field.get("is_order", "0"))
            order_type = str(field.get("order_type", "a"))
            order_num = int(field.get("order_num", 0))
            col_width = int(field.get("col_width", 0))

            # 先查是否已存在
            cursor.execute(
                "SELECT id FROM mode_CustombrowserDspField WHERE customid = %s AND fieldid = %s",
                (custom_id, fid)
            )
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    "UPDATE mode_CustombrowserDspField SET "
                    "isshow=%s, showorder=%s, isquery=%s, isquerydefaultdisplay=%s, "
                    "queryorder=%s, istitle=%s, ispk=%s, isquicksearch=%s, isorder=%s, "
                    "ordertype=%s, ordernum=%s, colwidth=%s "
                    "WHERE customid=%s AND fieldid=%s",
                    (is_show, show_order, is_query, is_query_default_display,
                     query_order, is_title, is_pk, is_quick, is_order, order_type,
                     order_num, col_width, custom_id, fid)
                )
            else:
                cursor.execute(
                    "INSERT INTO mode_CustombrowserDspField "
                    "(customid, colwidth, mobilewidth, fieldid, isshow, isquery, "
                    "isquerydefaultdisplay, showorder, queryorder, istitle, isorder, "
                    "ordertype, ordernum, isquicksearch, conditionTransition, ispk, "
                    "shownamelabel, requiredCon, conditionValue, conditionValue1, conditionValue2) "
                    "VALUES (%s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, '0', %s, '0', '0', '', '', '')",
                    (custom_id, col_width, fid, is_show, is_query,
                     is_query_default_display,
                     show_order, query_order, is_title, is_order,
                     order_type, order_num, is_quick, is_pk)
                )

        # 确保只有一个 istitle='1'
        cursor.execute(
            "UPDATE mode_CustombrowserDspField SET istitle='0' "
            "WHERE customid=%s AND fieldid!=%s AND istitle='1'",
            (custom_id, fields[0]["field_id"])
        )

    # ============================================================
    #  方法 3：构建浏览框 SQL 模板（复用逻辑）
    # ============================================================

    def _build_browser_sql(self, cursor, custom_id: int) -> Dict:
        """
        根据浏览框的表单和字段定义，构建 SQL 模板和 URL。
        所有按钮共享同一套 SQL 模板（来自 mode_custombrowser）。

        返回 dict: sqltext, sqltext1, sqltext2, detailpageurl, showpageurl, custom_name
        """
        # 1. 获取浏览框基础信息
        cursor.execute(
            "SELECT formid, modeid, customname FROM mode_custombrowser WHERE id = %s",
            (custom_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("浏览框不存在，customid=%s" % custom_id)
        form_id, mode_id, custom_name = int(row[0]), int(row[1]), row[2]

        # 2. 获取物理表名
        cursor.execute("SELECT tablename FROM workflow_bill WHERE id = %s", (form_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("表单不存在，formid=%s" % form_id)
        table_name = row[0]

        # 3. 获取 title 字段名（istitle=1 的字段）
        cursor.execute(
            "SELECT bf.fieldname FROM mode_CustombrowserDspField df "
            "JOIN workflow_billfield bf ON df.fieldid = bf.id "
            "WHERE df.customid = %s AND df.istitle = '1'",
            (custom_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("未找到 title 字段，customid=%s" % custom_id)
        title_field = row[0]

        # 4. 构建 SQL 模板
        sqltext = "select id,%s,%s from %s" % (title_field, title_field, table_name)
        sqltext1 = "select %s,%s from %s where id=?" % (title_field, title_field, table_name)
        sqltext2 = "select id,%s,%s from %s where %s like ?" % (title_field, title_field, table_name, title_field)

        # 5. 构建 URL
        detailpageurl = "/spa/cube/index.html#/main/cube/card?type=0&modeId=%s&formId=%s&billid=" % (mode_id, form_id)
        showpageurl = "/formmode/browser/CommonSingleBrowser.jsp?customid=%s" % custom_id

        return {
            "sqltext": sqltext, "sqltext1": sqltext1, "sqltext2": sqltext2,
            "detailpageurl": detailpageurl, "showpageurl": showpageurl,
            "custom_name": custom_name,
        }

    # ============================================================
    #  方法 4：为指定 MODE_BROWSER 记录补全按钮配置
    #  对应 CreateBrowserCmd
    # ============================================================

    def _fill_browser_button(self, cursor, custom_id: int, browser_id: int, showname: str):
        """
        补全单条 MODE_BROWSER 记录的按钮配置字段。
        按 browser_id 精确更新，不影响同一 customid 的其他按钮。
        """
        info = self._build_browser_sql(cursor, custom_id)
        name_val = "%s_%s" % (info["custom_name"], showname)

        cursor.execute(
            "UPDATE MODE_BROWSER SET "
            "showclass=1, datafrom=1, browserfrom=1, "
            "sqltext=%s, sqltext1=%s, sqltext2=%s, "
            "searchById=%s, searchByName=%s, "
            "name=%s, detailpageurl=%s, showpageurl=%s, "
            "showtype='', typename='', selecttype='', "
            "ModifyDate=%s, ModifyTime=%s "
            "WHERE id=%s",
            (
                self._encode(info["sqltext"]), self._encode(info["sqltext1"]), self._encode(info["sqltext2"]),
                self._encode(info["sqltext1"]), self._encode(info["sqltext2"]),
                self._encode(name_val), self._encode(info["detailpageurl"]), self._encode(info["showpageurl"]),
                self._encode(self._now_date()), self._encode(self._now_time()),
                browser_id
            )
        )

    # ============================================================
    #  对外接口：一步创建浏览框
    # ============================================================

    @expose(
        description="创建自定义浏览框：基础信息 + 字段定义 + 浏览按钮。fields 参数必须是完整的字段配置列表。",
        examples=[{
            "name": "届级管理",
            "app_id": 1076,
            "form_id": -1036,
            "fields": [
                {"field_id": 30759, "is_title": True, "is_show": "1", "show_order": 1},
                {"field_id": 30757, "is_show": "1", "show_order": 2},
                {"field_id": 30758, "is_show": "1", "show_order": 3},
                {"field_id": 30761, "is_query": "1", "is_show": "1", "show_order": 4, "query_order": 1},
                {"field_id": 30762, "is_show": "1", "show_order": 5},
            ]
        }],
        error_hints={
            "ID 失败": "请稍后重试，可能是并发创建冲突",
            "数据库密码": "请设置环境变量 OA_DB_PASSWORD"
        }
    )
    def create_browser(self, name: str, app_id: int, form_id: int,
                       fields: List[Dict],
                       mode_id: int = 0,
                       description: str = "",
                       defaultsql: str = "",
                       page_number: int = 10,
                       dsporder: float = -1.0) -> Dict:
        """
        创建自定义浏览框（一步到位）。

        Args:
            name: 浏览框名称
            app_id: 所属应用 ID
            form_id: 关联表单 ID
            fields: 字段配置列表，每项必须包含 field_id 和角色配置
            mode_id: 关联模块 ID（默认 0）
            description: 浏览框描述
            defaultsql: 默认查询条件
            page_number: 分页大小（默认 10）
            dsporder: 显示顺序（默认 0）

        Returns:
            {"custom_id": int, "showname": str, "fields_count": int,
             "browser_created": bool, "cache_refreshed": bool}
        """
        if not name:
            raise ValueError("浏览框名称不能为空")
        if not fields:
            raise ValueError("fields 不能为空，至少需要一个字段")

        # 生成拼音 showname（纯英文，避免编码问题）
        from pypinyin import pinyin, Style
        _pinyin_letters = []
        for char in name:
            if '\u4e00' <= char <= '\u9fff':
                _initial = pinyin(char, style=Style.FIRST_LETTER)[0][0]
                if _initial:
                    _pinyin_letters.append(_initial.lower())
            elif char.isalnum():
                _pinyin_letters.append(char.lower())
        showname = (''.join(_pinyin_letters))[:20]

        conn = self._connect()
        cursor = conn.cursor()

        try:
            # ========== 第 1 步：保存基础信息 ==========
            custom_id, browser_id = self._save_browser_base(
                cursor, name, app_id, form_id, showname,
                mode_id=mode_id, description=description,
                defaultsql=defaultsql, page_number=page_number,
                dsporder=dsporder
            )

            # ========== 第 2 步：保存字段定义 ==========
            self._save_field_set(cursor, custom_id, fields)

            # ========== 第 3 步：补全第一个按钮配置 ==========
            self._fill_browser_button(cursor, custom_id, browser_id, showname)

            conn.commit()

            # ========== 第 4 步：刷新缓存使配置生效 ==========
            refresh_result = refresh_label_cache(self.oa_host)
            cache_ok = refresh_result.get("status") == "1"

            return {
                "custom_id": custom_id,
                "showname": showname,
                "fields_count": len(fields),
                "cache_refreshed": cache_ok
            }

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  对外接口：为已有浏览框追加新按钮
    # ============================================================

    @expose(
        description="为已有自定义浏览框追加一个新的浏览按钮（MODE_BROWSER 记录）。同一个浏览框可以有多个按钮，用不同 showname 区分，供不同场景引用。",
        examples=[{
            "custom_id": 2265,
            "showname": "xmmllk2"
        }]
    )
    def add_browser_button(self, custom_id: int, showname: str) -> Dict:
        """
        为已有浏览框追加新按钮。

        Args:
            custom_id: 浏览框 ID（mode_custombrowser.id）
            showname: 按钮的 showname（供 fielddbtype=browser.xxx 引用）

        Returns:
            {"browser_id": int, "showname": str, "cache_refreshed": bool}
        """
        if not showname:
            raise ValueError("showname 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 确认浏览框存在
            cursor.execute("SELECT id FROM mode_custombrowser WHERE id = %s", (custom_id,))
            if not cursor.fetchone():
                raise ValueError("浏览框不存在，customid=%s" % custom_id)

            # showname 去重：只检查活跃浏览框
            cursor.execute(
                "SELECT COUNT(*) FROM MODE_BROWSER mb "
                "INNER JOIN mode_custombrowser mcb ON mb.customid = mcb.id "
                "WHERE mb.showname = %s",
                (showname,)
            )
            if cursor.fetchone()[0] > 0:
                showname = showname + str(int(time.time()))[-4:]

            # 插入新 MODE_BROWSER 记录
            cursor.execute(
                "INSERT INTO MODE_BROWSER (customid, showname) VALUES (%s, %s)",
                (custom_id, showname)
            )
            cursor.execute("SELECT SCOPE_IDENTITY()")
            browser_id = int(cursor.fetchone()[0])

            # 补全按钮配置
            self._fill_browser_button(cursor, custom_id, browser_id, showname)

            conn.commit()

            # 刷新缓存
            refresh_result = refresh_label_cache(self.oa_host)
            cache_ok = refresh_result.get("status") == "1"

            return {
                "browser_id": browser_id,
                "showname": showname,
                "cache_refreshed": cache_ok
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  辅助方法
    # ============================================================

    @expose(
        description="查询表单的所有字段，用于构建浏览框字段配置。返回 workflow_billfield 记录。",
        read_only=True
    )
    def get_form_fields(self, form_id: int) -> List[Dict]:
        """
        获取表单的所有字段信息，用于分析哪些字段适合加入浏览框。

        Args:
            form_id: 表单 ID（workflow_bill.id）

        Returns:
            字段列表，每项含 id, fieldname, fieldlabel, type, fielddbtype
        """
        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT id, fieldname, fieldlabel, type, fielddbtype, fieldhtmltype "
                "FROM workflow_billfield WHERE billid = %s ORDER BY id",
                (form_id,)
            )
            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": row[0],
                    "fieldname": self._decode(row[1]),
                    "fieldlabel": self._decode(row[2]),
                    "type": row[3],
                    "fielddbtype": self._decode(row[4]),
                    "fieldhtmltype": row[5]
                })
            return result
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="删除自定义浏览框及其所有字段配置。",
        destructive=True
    )
    def delete_browser(self, custom_id: int) -> Dict:
        """
        删除自定义浏览框。

        Args:
            custom_id: 浏览框 ID（mode_custombrowser.id）

        Returns:
            {"status": "1", "message": "已删除"}
        """
        conn = self._connect()
        cursor = conn.cursor()

        try:
            # 删除字段配置
            cursor.execute(
                "DELETE FROM mode_CustombrowserDspField WHERE customid = %s",
                (custom_id,)
            )
            # 删除 MODE_BROWSER 映射
            cursor.execute(
                "DELETE FROM MODE_BROWSER WHERE customid = %s",
                (custom_id,)
            )
            # 删除浏览框主记录
            cursor.execute(
                "DELETE FROM mode_custombrowser WHERE id = %s",
                (custom_id,)
            )
            conn.commit()

            return {"status": "1", "message": "浏览框已删除，custom_id=%s" % custom_id}
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="查询指定应用下的所有自定义浏览框。",
        read_only=True
    )
    def list_browsers(self, app_id: int = None) -> List[Dict]:
        """
        列出自定义浏览框。

        Args:
            app_id: 应用 ID（可选，不传则列出所有）

        Returns:
            浏览框列表
        """
        conn = self._connect()
        cursor = conn.cursor()

        try:
            sql = ("SELECT id, customname, formid, appid, modeid, customdesc "
                   "FROM mode_custombrowser")
            params = []
            if app_id is not None:
                sql += " WHERE appid = %s"
                params.append(app_id)
            sql += " ORDER BY id"

            cursor.execute(sql, tuple(params))
            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": row[0],
                    "name": self._decode(row[1]),
                    "form_id": row[2],
                    "app_id": row[3],
                    "mode_id": row[4],
                    "description": self._decode(row[5])
                })
            return result
        finally:
            cursor.close()
            conn.close()
