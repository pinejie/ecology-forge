# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 模块（Module）

通过直连 SQL Server 数据库，封装建模引擎的模块操作。

依赖：pip install pymssql

使用示例：
    from module_sdk import ModuleSDK

    sdk = XXX()  # 配置从 db-config.md 读取
    module_id = sdk.create_module("项目基本信息", app_id=1066, form_id=-1003)
"""

import pymssql
import os
import uuid
from typing import List, Dict, Optional

from mcp_register import expose
from layout_sdk import LayoutSDK
from field_linkage_sdk import FieldLinkageSDK
from db_config import load_db_config


class ModuleSDK:
    """建模引擎 SDK — 模块操作"""

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

    def _clear_cache(self):
        """清除建模缓存"""
        pass

    def _create_page_expands(self, cursor, mode_id: int):
        """
        为新建模块创建标准页面扩展（按钮组）。
        共 31 条，覆盖搜索、保存、编辑、删除、导出、批量操作等。
        与建模引擎页面创建模块时生成的扩展保持一致。
        幂等：先删已有数据，再插入新的。
        """
        import uuid as _uuid

        cube_uuid = str(_uuid.uuid4()).upper().replace("-", "")

        # 幂等：先查该模块是否已有页面扩展，若有则先删
        cursor.execute("SELECT COUNT(*) FROM mode_pageexpand WHERE modeid = %s", (mode_id,))
        existing_count = int(cursor.fetchone()[0])
        if existing_count > 0:
            cursor.execute(
                "DELETE FROM mode_batchset WHERE expandid IN "
                "(SELECT id FROM mode_pageexpand WHERE modeid = %s)",
                (mode_id,)
            )
            cursor.execute("DELETE FROM mode_pageexpand WHERE modeid = %s", (mode_id,))

        # 标准页面扩展模板：(name, showorder, isshow, isbatch, defaultenable, issystemflag)
        # isbatch=1: 参与批量操作（API getBatchSetInfo 筛选 isbatch in(1,2)）
        # defaultenable=1: 默认启用（搜索、清空条件、批量保存、新建、删除、批量导入/共享/导出）
        # issystemflag: 唯一标识，与 2456 标准数据保持一致
        page_expands = [
            ("搜索",       0.00,   1, 1, 1, 100, " "),
            ("保存",       1.00,   1, 0, 0, 1, " "),
            ("保存",       2.00,   1, 0, 0, 2, " "),
            ("编辑",       3.00,   1, 0, 0, 3, " "),
            ("共享",       4.00,   1, 0, 0, 4, " "),
            ("删除",       5.00,   1, 0, 0, 5, " "),
            ("删除",       6.00,   1, 0, 0, 6, " "),
            ("打印",       7.00,   1, 0, 0, 7, " "),
            ("清空条件",   8.00,   1, 0, 1, 8, " "),
            ("日志",       8.00,   1, 0, 0, 9, " "),
            ("保存并新建", 9.00,   1, 0, 0, 10, " "),
            ("保存并复制", 10.00,  0, 0, 0, 17, " "),
            ("草稿",       13.00,  0, 0, 0, 13, " "),
            ("导出",       14.00,  0, 0, 0, 14, " "),
            ("批量保存",   98.00,  1, 1, 1, 98, " "),
            ("批量保存",   99.00,  1, 1, 1, 99, " "),
            ("新建",       101.00, 1, 1, 1, 101, " "),
            ("批量新增",   101.50, 1, 1, 0, 16, " "),
            ("删除",       102.00, 1, 1, 1, 102, " "),
            ("批量导入",   103.00, 1, 1, 1, 103, " "),
            ("批量共享",   104.00, 1, 1, 1, 104, " "),
            ("导出",       105.00, 1, 1, 1, 105, "1"),
            ("显示列定制", 106.00, 1, 1, 0, 106, " "),
            ("批量修改",   107.00, 1, 1, 0, 15, " "),
            ("地图页面",   110.00, 0, 1, 0, 110, " "),
            ("批量设置标签", 167.00, 0, 1, 0, 167, " "),
            ("生成二维码", 168.00, 0, 0, 0, 11, " "),
            ("批量生成二维码", 169.00, 0, 1, 0, 12, " "),
            ("生成条形码", 170.00, 0, 0, 0, 170, " "),
            ("批量生成条形码", 171.00, 0, 1, 0, 171, " "),
            ("批量打印",   172.00, 0, 1, 0, 172, " "),
        ]

        for name, order, isshow, isbatch, defaultenable, issystemflag, isshowpageexpand in page_expands:
            cursor.execute(
                "INSERT INTO mode_pageexpand "
                "(modeid, expendname, showtype, opentype, hreftype, hrefid, "
                "hreftarget, showcondition, showconditioncn, isshow, showorder, "
                "issystem, issystemflag, isbatch, defaultenable, expenddesc, "
                "createpage, managepage, viewpage, moniterpage, "
                "mainid, showcondition2, tabshowtype, groupid, isquickbutton, "
                "defaultselect, isshowpageexpand, isenabletip, tiptype, "
                "tipdatasourceid, tipsql, tipjk, expendcallbackfn, icon, "
                "checkselectrow, cubeuuid) "
                "VALUES "
                "(%s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, "
                "%s, %s)",
                (
                    mode_id, self._encode(name), 2, 3, 0, 0,
                    "", None, None, isshow, order,
                    1, issystemflag, isbatch, defaultenable, self._encode(name),
                    0, 0, 0, 0,
                    None, None, None, None, None,
                    None, isshowpageexpand, None, None,
                    None, None, None, None, None,
                    None, cube_uuid
                )
            )

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

    # ============================================================
    #  模块（Module）操作
    # ============================================================

    @expose(
        description="在泛微 OA 建模引擎中创建一个新模块。自动查找同名已有模块获取表单和应用信息，也可手动指定。支持传入布局分组配置。",
        examples=[
            {"name": "项目基本信息", "app_id": 1066, "form_id": -1003, "layout_config": {"groups": [{"name": "基础信息", "fields": ["字段1", "字段2"]}]}},
            {"name": "宿舍登记测试", "app_id": 1066, "form_id": -1013, "layout_config": {"groups": [{"name": "登记信息", "fields": ["登记人", "登记日期"]}, {"name": "住宿信息", "fields": ["房间号", "床位", "入住日期"]}]}}
        ],
        error_hints={
            "找不到同名模块对应的表单": "请先创建表单，或手动指定 app_id 和 form_id",
            "同名模块不唯一": "请手动指定 app_id"
        }
    )
    def create_module(
        self,
        name: str,
        app_id: int = None,
        form_id: int = None,
        title: str = None,
        desc: str = "",
        show_order: float = -1,
        layout_config: Dict = None,
        field_linkages: List[Dict] = None
    ) -> int:
        """
        创建模块

        :param name: 模块名称（必填）。会自动查找同名模块获取 form_id 和 app_id
        :param app_id: 所属应用 ID（选填）。不传则自动查找
        :param form_id: 关联表单 ID（选填）。不传则自动查找
        :param title: 页面标题（选填），默认与模块名称相同
        :param desc: 模块描述（选填，默认空）
        :param show_order: 显示顺序（选填，-1 表示默认排序）
        :param layout_config: 布局分组配置（必填）。格式：{"groups": [{"name": "组名", "fields": ["字段1", "字段2"]}]}
        :param field_linkages: 字段联动配置（选填）。格式见 field_linkage_sdk.create_linkage 参数
        :return: 新建模块的 ID

        自动规则：
        - app_id 和 form_id 都不传时，查找同名模块（modename = name）
        - 找到后自动使用该模块的 form_id 和 modetype（作为 app_id）
        - 页面标题默认等于模块名称，可通过 title 参数自定义
        """
        if not name or not name.strip():
            raise ValueError("模块名称不能为空")
        if not layout_config or "groups" not in layout_config:
            raise ValueError("布局分组配置不能为空，格式：{\"groups\": [{\"name\": \"组名\", \"fields\": [\"字段1\", \"字段2\"]}]}")

        mod_title = title if title else name

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 自动查找：如果 app_id 和 form_id 都没传，查找同名模块
            if app_id is None and form_id is None:
                cursor.execute(
                    "SELECT id, modetype, formid FROM modeinfo WHERE modename = %s AND isdelete = 0",
                    (name,)
                )
                rows = cursor.fetchall()
                if rows:
                    # 取第一条
                    app_id = int(rows[0][1])
                    form_id = int(rows[0][2]) if rows[0][2] else 0
                else:
                    raise ValueError("未找到名为 '%s' 的已有模块，请先创建对应表单，或手动指定 app_id 和 form_id" % name)

            # 验证应用是否存在
            cursor.execute(
                "SELECT id FROM modeTreeField WHERE id = %s AND isdelete = 0",
                (app_id,)
            )
            if not cursor.fetchone():
                raise ValueError("所属应用不存在，ID=%d" % app_id)

            sub_company = self._get_sub_company_id(cursor)
            mode_uuid = str(uuid.uuid4()).upper().replace("-", "")

            cursor.execute(
                "INSERT INTO modeinfo "
                "(modename, modetitle, modedesc, modetype, formid, subcompanyid, "
                "dsporder, isdelete, empowmentType, isallowreply, replyposition, "
                "isAtAll, categorytype, selectcategory, isaddrightbyworkflow, "
                "iswatermark, isdelfile, isfrontmultlang, iscustomorder, "
                "iscustompage, classprotect, DefaultShared, NonDefaultShared, "
                "seccategory, cubeuuid) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, '0,0', 0, 1, '0', 0, 0, 1, 0, 0, 0, 0, 0, 0, ' ', ' ', 5, %s)",
                (
                    self._encode(name),
                    self._encode(mod_title),
                    self._encode(desc),
                    app_id,
                    form_id,
                    sub_company,
                    show_order,
                    mode_uuid
                )
            )
            # 注意：不在这里 commit，等权限记录全部插入后再统一提交

            # 获取新建的 ID
            cursor.execute("SELECT MAX(id) AS newId FROM modeinfo")
            row = cursor.fetchone()
            new_id = int(row[0]) if row else -1

            # 插入 6 条默认权限记录（与页面创建模块行为一致）
            cube_uuid = str(uuid.uuid4()).upper().replace("-", "")
            default_rights = [
                (3, 80, 0),    # 默认共享 - 创建人本人
                (99, 81, 0),   # 初始化 - 创建人直接上级
                (99, 84, 10),  # 初始化 - 待确认
                (99, 85, 10),  # 初始化 - 创建人部门
                (99, 89, 10),  # 初始化 - 创建人所有上级
                (99, 90, 0),   # 初始化 - 创建人本岗位
            ]
            for righttype, sharetype, showlevel in default_rights:
                cursor.execute(
                    "INSERT INTO moderightinfo "
                    "(modeid, righttype, sharetype, relatedid, rolelevel, showlevel, "
                    "javafilename, layoutid, layoutid1, layoutorder, isrolelimited, "
                    "rolefieldtype, rolefield, higherlevel, importtype, conditiontype, "
                    "conditionsql, conditiontext, showlevel2, modifytime, "
                    "hrmCompanyVirtualType, orgrelation, joblevel, jobleveltext, "
                    "browsersharetype, javafileAddress, isfromimportall, needrebuild, cubeuuid) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        new_id, righttype, sharetype, 0, 0, showlevel,
                        "", 0, 0, 0, 0, 0, 0, 0, 0, 0, "", "", None, "",
                        "0", 0, 0, "0", 0, "", None, 0, cube_uuid
                    )
                )

            # 默认共享权限：所有人查看 + 系统管理员（总部）完全控制
            share_rights = [
                (1, 5, 0, 0, 0),   # righttype=1, sharetype=5(所有人), showlevel=0
                (3, 4, 2, 2, 2),   # righttype=3, sharetype=4(角色), relatedid=2(系统管理员), rolelevel=2(总部)
            ]
            for righttype, sharetype, relatedid, rolelevel, showlevel in share_rights:
                cursor.execute(
                    "INSERT INTO moderightinfo "
                    "(modeid, righttype, sharetype, relatedid, rolelevel, showlevel, "
                    "javafilename, layoutid, layoutid1, layoutorder, isrolelimited, "
                    "rolefieldtype, rolefield, higherlevel, importtype, conditiontype, "
                    "conditionsql, conditiontext, showlevel2, modifytime, "
                    "hrmCompanyVirtualType, orgrelation, joblevel, jobleveltext, "
                    "browsersharetype, javafileAddress, isfromimportall, needrebuild, cubeuuid) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        new_id, righttype, sharetype, relatedid, rolelevel, showlevel,
                        "", 0, 0, -1, 0, None, None, 0, 1, None, None, None, None,
                        "", "0", 0, 0, "0", 0, "", None, 0, cube_uuid
                    )
                )

            # 默认创建权限：系统管理员（总部）
            cursor.execute(
                "INSERT INTO moderightinfo "
                "(modeid, righttype, sharetype, relatedid, rolelevel, showlevel, "
                "javafilename, layoutid, layoutid1, layoutorder, isrolelimited, "
                "rolefieldtype, rolefield, higherlevel, importtype, conditiontype, "
                "conditionsql, conditiontext, showlevel2, modifytime, "
                "hrmCompanyVirtualType, orgrelation, joblevel, jobleveltext, "
                "browsersharetype, javafileAddress, isfromimportall, needrebuild, cubeuuid) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    new_id, 0, 4, 2, 2, 0,
                    "", 0, 0, -1, 0, None, None, 0, 1, None, None, None, None,
                    "", "0", 0, 0, "0", 0, "", None, 0, cube_uuid
                )
            )

            # 自动创建页面扩展（标准按钮组）
            self._create_page_expands(cursor, new_id)

            # 统一提交：模块 + 9 条权限记录 + 页面扩展
            conn.commit()

            # 创建日志表 ModeViewLog_{module_id}
            log_table = "ModeViewLog_%d" % new_id
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = %s",
                (log_table,)
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "SELECT * INTO [%s] FROM ModeViewLog_0 WHERE 1=0" % log_table
                )
                cursor.execute(
                    "ALTER TABLE [%s] ADD CONSTRAINT [PK_%s] PRIMARY KEY NONCLUSTERED (id)"
                    % (log_table, log_table)
                )
                cursor.execute(
                    "CREATE CLUSTERED INDEX [%s_operatetype] ON [%s](operatetype)"
                    % (log_table, log_table)
                )
                conn.commit()

            # 自动创建布局（查看/新建/编辑三种）
            layout_sdk = LayoutSDK(
                host=self.host, user=self.user,
                password=self.password, database=self.database
            )
            layout_sdk.insert_layout(form_id=form_id, modeid=new_id, config=layout_config)

            # 自动创建字段联动（可选）
            if field_linkages:
                linkage_sdk = FieldLinkageSDK(
                    host=self.host, user=self.user,
                    password=self.password, database=self.database
                )
                for linkage in field_linkages:
                    linkage_sdk.create_linkage(module_id=new_id, **linkage)

            self._clear_cache()
            return new_id

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="查询泛微 OA 建模引擎中的模块列表",
        examples=[
            {"app_id": 1066},
            {}
        ],
        read_only=True
    )
    def list_modules(self, app_id: int = None) -> List[Dict]:
        """
        查询模块列表

        :param app_id: 所属应用 ID，不传则查所有模块（默认查所有）
        :return: 模块列表 [{"id": ..., "name": ..., "desc": ..., "app_id": ..., "form_id": ..., "subcompanyid": ...}]
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            if app_id is not None:
                cursor.execute(
                    "SELECT id, modename, modedesc, modetype, formid, subcompanyid, dsporder "
                    "FROM modeinfo WHERE modetype = %s AND isdelete = 0 "
                    "ORDER BY dsporder, id",
                    (app_id,)
                )
            else:
                cursor.execute(
                    "SELECT id, modename, modedesc, modetype, formid, subcompanyid, dsporder "
                    "FROM modeinfo WHERE isdelete = 0 "
                    "ORDER BY modetype, dsporder, id"
                )

            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": int(row[0]),
                    "name": str(row[1] or ""),
                    "desc": str(row[2] or ""),
                    "app_id": int(row[3]) if row[3] else 0,
                    "form_id": int(row[4]) if row[4] else 0,
                    "subcompanyid": int(row[5]) if row[5] else 0,
                    "showOrder": row[6]
                })
            return result
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="修改泛微 OA 建模引擎中已有模块的名称或描述",
        examples=[
            {"module_id": 2394, "new_name": "新模块名称"},
            {"module_id": 2394, "new_desc": "新的模块描述"}
        ],
        error_hints={
            "模块不存在": "请检查 module_id 是否正确，可用 list_modules 查询"
        }
    )
    def update_module(
        self,
        module_id: int,
        new_name: str = None,
        new_desc: str = None
    ):
        """
        更新模块信息

        :param module_id: 模块 ID（必填）
        :param new_name: 新名称（选填，不传则不修改）
        :param new_desc: 新描述（选填，不传则不修改）
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 验证模块是否存在
            cursor.execute(
                "SELECT modename, modedesc FROM modeinfo WHERE id = %s AND isdelete = 0",
                (module_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("模块不存在，ID=%d" % module_id)

            if new_name is not None or new_desc is not None:
                if new_name is not None:
                    cursor.execute(
                        "UPDATE modeinfo SET modename = %s, modetitle = %s WHERE id = %s",
                        (self._encode(new_name), self._encode(new_name), module_id)
                    )
                if new_desc is not None:
                    cursor.execute(
                        "UPDATE modeinfo SET modedesc = %s WHERE id = %s",
                        (self._encode(new_desc), module_id)
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
        description="物理删除泛微 OA 建模引擎中的模块及所有关联数据（布局、权限、查询、显示字段等）",
        examples=[
            {"module_id": 2394}
        ],
        destructive=True
    )
    def delete_module(self, module_id: int) -> Dict:
        """
        删除模块（物理删除，级联清理所有关联资源）

        :param module_id: 模块 ID（必填）
        :return: {"module_name": str, "deleted": {"modeinfo": 1, "moderightinfo": N, ...}}
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 确认模块存在
            cursor.execute("SELECT modename FROM modeinfo WHERE id = %s", (module_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("模块不存在，ID=%d" % module_id)
            module_name = str(row[0] or "")

            # 先删模块的查询列表
            cursor.execute("SELECT id FROM mode_customsearch WHERE modeid = %s", (module_id,))
            query_ids = [int(r[0]) for r in cursor.fetchall()]
            for qid in query_ids:
                cursor.execute("DELETE FROM mode_CustomDspField WHERE customid = %s", (qid,))
                cursor.execute("DELETE FROM mode_batchset WHERE customsearchid = %s", (qid,))
                cursor.execute("DELETE FROM mode_customsearch WHERE id = %s", (qid,))

            # 统计各表待删数据
            stats = {}
            for tbl, col in [
                ("modeinfo", "id"),
                ("moderightinfo", "modeid"),
                ("modehtmllayout", "modeid"),
                ("mode_pageexpand", "modeid"),
            ]:
                cursor.execute("SELECT COUNT(*) FROM %s WHERE %s = %%s" % (tbl, col), (module_id,))
                stats[tbl] = int(cursor.fetchone()[0])

            # 布局子表需要特殊处理
            cursor.execute("SELECT id FROM modehtmllayout WHERE modeid = %s", (module_id,))
            layout_ids = [int(r[0]) for r in cursor.fetchall()]
            if layout_ids:
                lph = ','.join([str(x) for x in layout_ids])
                cursor.execute("SELECT COUNT(*) FROM modeformfield WHERE layoutid IN (%s)" % lph)
                stats["modeformfield"] = int(cursor.fetchone()[0])
                cursor.execute("SELECT COUNT(*) FROM modeformgroup WHERE layoutid IN (%s)" % lph)
                stats["modeformgroup"] = int(cursor.fetchone()[0])
            else:
                stats["modeformfield"] = 0
                stats["modeformgroup"] = 0

            stats["mode_customsearch"] = len(query_ids)

            # 先删 mode_batchset
            cursor.execute(
                "DELETE FROM mode_batchset WHERE expandid IN "
                "(SELECT id FROM mode_pageexpand WHERE modeid = %s)",
                (module_id,)
            )
            stats["mode_batchset"] = cursor.rowcount

            # 按依赖顺序删除：子表 → 主表
            if layout_ids:
                lph = ','.join([str(x) for x in layout_ids])
                cursor.execute("DELETE FROM modeformfield WHERE layoutid IN (%s)" % lph)
                cursor.execute("DELETE FROM modeformgroup WHERE layoutid IN (%s)" % lph)
                cursor.execute("DELETE FROM modehtmllayout WHERE id IN (%s)" % lph)
            cursor.execute("DELETE FROM moderightinfo WHERE modeid = %s", (module_id,))
            cursor.execute("DELETE FROM mode_pageexpand WHERE modeid = %s", (module_id,))

            # 删除字段联动表（按依赖顺序：子 → 父）
            cursor.execute(
                "DELETE FROM modeDataInputfield WHERE DataInputID IN "
                "(SELECT id FROM modeDataInputmain WHERE entryID IN "
                "(SELECT id FROM modeDataInputentry WHERE modeid = %s))",
                (module_id,)
            )
            cursor.execute(
                "DELETE FROM modeDataInputtable WHERE DataInputID IN "
                "(SELECT id FROM modeDataInputmain WHERE entryID IN "
                "(SELECT id FROM modeDataInputentry WHERE modeid = %s))",
                (module_id,)
            )
            cursor.execute(
                "DELETE FROM modeDataInputmain WHERE entryID IN "
                "(SELECT id FROM modeDataInputentry WHERE modeid = %s)",
                (module_id,)
            )
            cursor.execute(
                "DELETE FROM modeDataInputentry WHERE modeid = %s",
                (module_id,)
            )

            cursor.execute("DELETE FROM modeinfo WHERE id = %s", (module_id,))

            conn.commit()

            # 删除日志表 ModeViewLog_{module_id}
            log_table = "ModeViewLog_%d" % module_id
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = %s",
                (log_table,)
            )
            if cursor.fetchone()[0] > 0:
                cursor.execute("DROP TABLE [%s]" % log_table)
                conn.commit()

            self._clear_cache()
            return {
                "module_name": module_name,
                "deleted": dict(stats, total=sum(stats.values())),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="查询泛微 OA 建模引擎中模块的详情信息",
        examples=[
            {"module_id": 2394}
        ],
        read_only=True
    )
    def get_module_detail(self, module_id: int) -> Dict:
        """
        查询模块详情

        :param module_id: 模块 ID（必填）
        :return: 模块详情 {"id": ..., "name": ..., "desc": ..., "app_id": ..., "form_id": ..., "modetype": ..., 更多字段...}
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM modeinfo WHERE id = %s", (module_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("模块不存在，ID=%d" % module_id)

            cols = [desc[0] for desc in cursor.description]
            result = {}
            for i, val in enumerate(row):
                key = cols[i]
                if val is None:
                    result[key] = None
                elif isinstance(val, int):
                    result[key] = val
                elif isinstance(val, float):
                    result[key] = val
                else:
                    result[key] = str(val) if val != "" else ""
            return result
        finally:
            cursor.close()
            conn.close()
