# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 表单（Form）

通过直连 SQL Server 数据库，封装建模引擎的表单创建操作。

依赖：pip install pymssql

使用示例：
    from form_sdk import FormSDK

    sdk = FormSDK(host="...", user="sa", password="Weaver@2001", database="ecology")
    form_id = sdk.create_form("测试订单", app_id=1054, table_name="uf_TestOrder", fields=[...])

规则文档：docs/sdk-references/form-rules.md
"""

import pymssql
import os
import random
import string
import uuid
import time
from typing import List, Dict, Optional
from pypinyin import pinyin, Style

from mcp_register import expose
from cache_sdk import refresh_label_cache
from db_config import load_db_config


class FormSDK:
    """建模引擎表单创建 SDK"""

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
        )

    def _encode(self, s):
        """Python Unicode → GBK bytes，适配 SQL Server varchar 列写入"""
        if s is None:
            return ""
        return str(s).encode("gbk")

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

    def _generate_table_name(self, form_name: str, max_len: int = 20) -> str:
        """
        生成数据库表名：uf_ + 中文拼音首字母，长度不超过 max_len，
        只含英文、下划线、数字。如冲突则追加随机字符串。
        """
        # 提取中文部分的拼音首字母
        pinyin_letters = []
        for char in form_name:
            if '\u4e00' <= char <= '\u9fff':
                # 中文字符 → 拼音首字母
                initial = pinyin(char, style=Style.FIRST_LETTER)[0][0]
                if initial:
                    pinyin_letters.append(initial.lower())
            elif char.isalnum():
                # 英文/数字保留
                pinyin_letters.append(char.lower())

        pinyin_str = ''.join(pinyin_letters)
        # 表名 = uf_ + 拼音，截断到 max_len
        table_name = ("uf_" + pinyin_str)[:max_len]

        return table_name

    def _check_table_name_available(self, cursor, table_name: str) -> str:
        """
        检查表名是否可用（查物理表是否存在），如已被占用则追加随机后缀。
        """
        original = table_name
        max_len = 20
        attempts = 0
        while attempts < 10:
            cursor.execute(
                "SELECT COUNT(*) FROM sysobjects WHERE type='U' AND name = %s",
                (table_name,)
            )
            row = cursor.fetchone()
            if row and int(row[0]) > 0:
                # 物理表已存在，追加 4 位随机字符
                suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                table_name = original[:max_len - 5] + '_' + suffix
                attempts += 1
            else:
                return table_name

        raise ValueError("表名 %s 已被占用，请更换表单名称" % original)

    def _get_next_id(self, cursor, table: str) -> int:
        """生成非自增表的下一个 ID（MAX(id)+1），加简单重试防冲突"""
        for attempt in range(5):
            cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM %s" % table)
            row = cursor.fetchone()
            next_id = int(row[0]) if row else 1
            # 验证该 ID 尚未被占用（防并发冲突）
            cursor.execute("SELECT COUNT(*) FROM %s WHERE id = %s" % (table, next_id))
            row = cursor.fetchone()
            if row and int(row[0]) != 0:
                time.sleep(0.05 * (attempt + 1))
                continue
            # 对于 HtmlLabelIndex，还需检查 HtmlLabelInfo 是否有残留记录
            # （表单删除时 HtmlLabelInfo 可能未清理，复用会导致 labelname 重复）
            if table == "HtmlLabelIndex":
                cursor.execute("SELECT COUNT(*) FROM HtmlLabelInfo WHERE indexid = %s", (next_id,))
                row = cursor.fetchone()
                if row and int(row[0]) != 0:
                    time.sleep(0.05 * (attempt + 1))
                    continue
            return next_id
        raise RuntimeError(
            "生成 ID 冲突：表 %s 连续 5 次获取的 ID 已被占用，可能存在高并发写入" % table
        )

    def _get_next_form_id(self, cursor) -> int:
        """生成 workflow_bill 的表单 ID（负数，与浏览器创建保持一致）"""
        cursor.execute("SELECT ISNULL(MIN(id), 0) - 1 FROM workflow_bill")
        row = cursor.fetchone()
        return int(row[0]) if row else -1

    def _get_sub_company_id(self, cursor) -> int:
        """获取当前系统的默认 subCompanyId"""
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

    def _create_label(self, cursor, name: str) -> int:
        """
        创建表单/字段的标签（HtmlLabelIndex + 3 条 HtmlLabelInfo）
        一律新建，不复用已有标签。
        每次 INSERT 后验证记录存在，确保非原子 ID 生成不会留下空引用。
        """
        # 生成新标签 ID（带冲突重试）
        label_id = self._get_next_id(cursor, "HtmlLabelIndex")

        # INSERT HtmlLabelIndex
        cursor.execute(
            "INSERT INTO HtmlLabelIndex(id, indexdesc) VALUES(%s, %s)",
            (label_id, self._encode(name))
        )
        # 验证
        cursor.execute("SELECT COUNT(*) FROM HtmlLabelIndex WHERE id = %s", (label_id,))
        if int(cursor.fetchone()[0]) == 0:
            raise RuntimeError("HtmlLabelIndex 插入失败：id=%d，name=%s" % (label_id, name))

        # INSERT 3 条 HtmlLabelInfo（languageid 7, 8, 9）
        for lang_id in (7, 8, 9):
            cursor.execute(
                "INSERT INTO HtmlLabelInfo(indexid, labelname, languageid) VALUES(%s, %s, %s)",
                (label_id, self._encode(name), lang_id)
            )
            # 验证
            cursor.execute(
                "SELECT COUNT(*) FROM HtmlLabelInfo WHERE indexid = %s AND languageid = %s",
                (label_id, lang_id)
            )
            if int(cursor.fetchone()[0]) == 0:
                raise RuntimeError(
                    "HtmlLabelInfo 插入失败：indexid=%d, languageid=%d, name=%s"
                    % (label_id, lang_id, name)
                )

        return label_id

    # ============================================================
    #  浏览框（Browser）查询
    # ============================================================

    @expose(
        description="查询泛微 OA 所有可用浏览框列表",
        examples=[{}],
        read_only=True
    )
    def list_browsers(self) -> List[Dict]:
        """
        查询所有可用浏览框，返回 id、名称、fielddbtype。
        以 wf_browser_config 为主表（名称直接可用），
        LEFT JOIN workflow_browserurl 获取 fielddbtype。
        只返回 type 为数字的记录（系统浏览框）。
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT c.type, c.description, b.fielddbtype "
                "FROM wf_browser_config c "
                "LEFT JOIN workflow_browserurl b ON c.type = CAST(b.id AS varchar) "
                "WHERE ISNUMERIC(c.type) = 1 "
                "ORDER BY CAST(c.type AS int)"
            )
            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": int(row[0]),
                    "name": self._decode(row[1]),
                    "dbType": str(row[2] or "integer")
                })
            return result
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="按名称搜索浏览框",
        examples=[
            {"keyword": "人员"},
            {"keyword": "分部"}
        ],
        read_only=True
    )
    def search_browser(self, keyword: str) -> List[Dict]:
        """
        按名称模糊搜索浏览框。优先搜 wf_browser_config（E9 新版），
        同时兜底搜 workflow_browserurl（经典版如"日期"）。

        :param keyword: 搜索关键词
        :return: 匹配的浏览框列表
        """
        if not keyword or not keyword.strip():
            raise ValueError("搜索关键词不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 1. 搜 wf_browser_config
            cursor.execute(
                "SELECT c.type, c.description, b.fielddbtype "
                "FROM wf_browser_config c "
                "LEFT JOIN workflow_browserurl b ON c.type = CAST(b.id AS varchar) "
                "WHERE ISNUMERIC(c.type) = 1 AND c.description LIKE %s "
                "ORDER BY CAST(c.type AS int)",
                ('%' + keyword + '%',)
            )
            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": int(row[0]),
                    "name": self._decode(row[1]),
                    "dbType": str(row[2] or "integer")
                })

            # 2. 兜底搜 workflow_browserurl（经典版，如"日期"）
            if result:
                exclude_ids = ",".join(str(r["id"]) for r in result)
                not_in_clause = " AND b.id NOT IN (" + exclude_ids + ")"
            else:
                not_in_clause = ""
            cursor.execute(
                "SELECT b.id, h.labelname, b.fielddbtype "
                "FROM workflow_browserurl b "
                "INNER JOIN HtmlLabelInfo h ON b.labelid = h.indexid AND h.languageid = 7 "
                "WHERE h.labelname LIKE %s" + not_in_clause,
                ('%' + keyword + '%',)
            )
            for row in cursor.fetchall():
                result.append({
                    "id": int(row[0]),
                    "name": self._decode(row[1]),
                    "dbType": str(row[2] or "integer")
                })
            return result
        finally:
            cursor.close()
            conn.close()

    def _resolve_browser_id(self, cursor, field: Dict) -> int:
        """
        浏览框字段解析：支持 browser_id 或 browser_name。
        如果传了 browser_name，自动查表匹配 browser_id。
        """
        browser_id = field.get("browser_id", 0)
        browser_name = field.get("browser_name", "")

        if browser_id and browser_id > 0:
            return browser_id

        if browser_name:
            # 1. 先查 wf_browser_config（E9 新版）
            cursor.execute(
                "SELECT c.type FROM wf_browser_config c "
                "WHERE ISNUMERIC(c.type) = 1 AND c.description = %s",
                (self._encode(browser_name),)
            )
            row = cursor.fetchone()
            if row:
                return int(row[0])

            # 2. 兜底查 workflow_browserurl（经典版，需 JOIN HtmlLabelInfo）
            cursor.execute(
                "SELECT b.id FROM workflow_browserurl b "
                "INNER JOIN HtmlLabelInfo h ON b.labelid = h.indexid AND h.languageid = 7 "
                "WHERE h.labelname = %s",
                (self._encode(browser_name),)
            )
            row = cursor.fetchone()
            if row:
                return int(row[0])

            # 3. 查自定义浏览框（mode_custombrowser），只返回 formid 指向有效表单的记录
            cursor.execute(
                "SELECT mcb.id FROM mode_custombrowser mcb "
                "WHERE mcb.customname = %s "
                "AND EXISTS (SELECT 1 FROM workflow_bill WHERE id = mcb.formid)",
                (self._encode(browser_name),)
            )
            row = cursor.fetchone()
            if row:
                return int(row[0])

            # 精确匹配全部失败，提示搜索
            cursor.execute(
                "SELECT TOP 5 c.type, c.description FROM wf_browser_config c "
                "WHERE ISNUMERIC(c.type) = 1 AND c.description LIKE %s",
                ('%' + browser_name + '%',)
            )
            hints = [self._decode(r[1]) + "(id=" + str(int(r[0])) + ")" for r in cursor.fetchall()]
            raise ValueError(
                "未找到浏览框 '%s'，可用选项: %s" % (browser_name, ", ".join(hints))
            )

        return 0

    # ============================================================
    #  字段类型自动推断（智能模式）
    # ============================================================

    def _auto_detect_field_type(self, cursor, name: str, label: str) -> Dict:
        """
        根据字段名/标签自动推断字段类型。
        判断顺序：精确匹配浏览框 → 高优先推断(checkbox) → 关键词映射浏览框 → 自定义浏览框 → 关键词推断 → 兜底文本

        返回: 完整的 field dict（含 type, fielddbtype 等所有必要参数）
        """
        label_str = label.strip()
        name_str = name.strip().lower()

        # ========== 1. 精确匹配系统浏览框 ==========
        cursor.execute(
            "SELECT b.id, b.fielddbtype, h.labelname "
            "FROM workflow_browserurl b "
            "LEFT JOIN HtmlLabelInfo h ON b.labelid = h.indexid AND h.languageid = 7 "
            "WHERE ISNUMERIC(b.id) = 1"
        )
        for row in cursor.fetchall():
            br_name = self._decode(row[2]) if isinstance(row[2], str) and row[2] else ""
            # 精确匹配
            if br_name and label_str == br_name:
                result = {
                    "name": name, "label": label,
                    "type": "browser",
                    "browser_id": int(row[0]),
                    "is_multi": str(row[1]).lower() in ("text", "varchar(1000)"),
                }
                # 日期/时间浏览框的物理列类型特殊处理
                br_id = int(row[0])
                br_type = str(row[1] or "")
                if br_id == 2:  # 日期浏览框
                    result["db_type"] = "char(10)"
                elif br_id == 19:  # 时间浏览框
                    result["db_type"] = "char(5)"
                elif br_id == 290:  # 日期时间浏览框
                    result["db_type"] = "varchar(100)"
                return result

        # ========== 2. 关键词推断（高优先级：checkbox 等明确语义） ==========
        # checkbox：是否/有无/同意/确认/完成 — 优先级高于浏览框关键词
        if any(kw in label_str for kw in ["是否", "有无", "同意", "确认", "完成", "通过"]):
            return {"name": name, "label": label, "type": "checkbox"}

        # ========== 3. 关键词映射到特定系统浏览框 ==========
        # 人员类 → 人力资源(id=1)
        if any(kw in label_str for kw in ["人", "审核", "审批", "申请", "创建", "操作", "经办", "负责人", "主管", "领导", "员工", "职员"]):
            return {
                "name": name, "label": label,
                "type": "browser", "browser_id": 1,  # 人力资源
                "is_multi": False,
            }
        # 部门类 → 部门(id=4)
        if any(kw in label_str for kw in ["部门", "科室", "团队"]):
            return {
                "name": name, "label": label,
                "type": "browser", "browser_id": 4,  # 部门
                "is_multi": False,
            }
        # 多人 → 多人力资源(id=17)
        if any(kw in label_str for kw in ["多", "全体", "参与"]):
            return {
                "name": name, "label": label,
                "type": "browser", "browser_id": 17,  # 多人力资源
                "is_multi": True,
            }
        # 日期类 → 日期浏览框，物理列存日期字符串
        if any(kw in label_str for kw in ["日期"]):
            return {
                "name": name, "label": label,
                "type": "browser", "browser_id": 2,  # 日期
                "is_multi": False,
                "db_type": "char(10)",  # 物理列存日期字符串
            }
        # 时间类 → 时间浏览框，物理列存时间字符串
        if any(kw in label_str for kw in ["时间"]):
            return {
                "name": name, "label": label,
                "type": "browser", "browser_id": 19,  # 时间
                "is_multi": False,
                "db_type": "char(5)",  # 物理列存 HH:mm 格式
            }
        # 年月类 → 年月浏览框，物理列存 varchar(7) 如 "202608"
        if any(kw in label_str for kw in ["年月"]):
            return {
                "name": name, "label": label,
                "type": "browser", "browser_id": 403,  # 年月
                "is_multi": False,
                "db_type": "varchar(7)",  # 物理列存 "YYYYMM" 格式
            }
        # 年份类 → 年份浏览框，物理列存 int
        if any(kw in label_str for kw in ["年份", "年度"]):
            return {
                "name": name, "label": label,
                "type": "browser", "browser_id": 178,  # 年份
                "is_multi": False,
                "db_type": "int",  # 物理列存年份整数
            }
        # 月份类 → 年月浏览框（系统无独立"月份"浏览框），物理列存 varchar(7)
        if "月" in label_str:
            return {
                "name": name, "label": label,
                "type": "browser", "browser_id": 403,  # 年月
                "is_multi": False,
                "db_type": "varchar(7)",  # 物理列存 "YYYYMM" 格式
            }

        # ========== 4. 查自定义浏览框（mode_custombrowser）精确匹配 ==========
        cursor.execute("SELECT id, customname FROM mode_custombrowser")
        for row in cursor.fetchall():
            cb_name = self._decode(row[1]) if isinstance(row[1], str) and row[1] else ""
            if cb_name and label_str == cb_name:
                return {
                    "name": name, "label": label,
                    "type": "browser",
                    "browser_id": int(row[0]),
                    "is_multi": False,
                }

        # ========== 5. 查自定义树形浏览框（mode_customtree）精确匹配 ==========
        cursor.execute("SELECT id, treename FROM mode_customtree")
        for row in cursor.fetchall():
            tr_name = self._decode(row[1]) if isinstance(row[1], str) and row[1] else ""
            if tr_name and label_str == tr_name:
                return {
                    "name": name, "label": label,
                    "type": "browser",
                    "browser_id": int(row[0]),
                    "is_tree": True,
                    "is_multi": False,
                }

        # ========== 5.5 阻塞检查：字段暗示需要自定义浏览框但尚未创建 ==========
        # 字段名/标签包含以下特征时，判定为"应该用自定义浏览框"
        browser_hint_patterns = [
            "关联", "引用", "选择", "对应",  # 语义暗示关联其他表单
            "_id", "id_",                     # 命名规范暗示外键引用
        ]
        is_browser_hint = any(kw in label_str for kw in browser_hint_patterns) or \
                          any(kw in name_str for kw in browser_hint_patterns)
        # 进一步缩小范围：排除已被系统关键词覆盖的场景
        # （如"人员"已被系统浏览框匹配、"是否"已被 checkbox 匹配等）
        if is_browser_hint:
            raise ValueError(
                "字段 '%s'（标签: '%s'）应为自定义浏览框类型，但当前系统中不存在匹配的自定义浏览框。\n"
                "解决步骤：\n"
                "  1. 先创建对应的自定义浏览框（mode_custombrowser），名称需与字段标签完全一致\n"
                "  2. 浏览框的数据源表单必须已存在\n"
                "  3. 创建浏览框后，重新创建该表单字段\n"
                "规则依据：modeling-rules.md 第5节「依赖排序与执行」— 浏览框先于引用它的表单字段创建"
                % (name, label)
            )

        # ========== 6. 关键词推断（其余类型） ==========
        # 金额/价格/费用 → float
        if any(kw in label_str for kw in ["金额", "价格", "费用", "单价", "总价", "成本", "预算", "工资"]):
            return {"name": name, "label": label, "type": "float"}

        # 附件/文件/图片/照片 → file
        if any(kw in label_str for kw in ["附件", "文件", "图片", "照片", "上传"]):
            return {"name": name, "label": label, "type": "file"}

        # 备注/说明/描述/内容/详情/正文 → textarea
        if any(kw in label_str for kw in ["备注", "说明", "描述", "内容", "详情", "正文", "意见", "建议"]):
            return {"name": name, "label": label, "type": "textarea"}

        # 数量/个数/次数 → integer
        if any(kw in label_str for kw in ["数量", "个数", "次数", "天数", "月数", "年数"]):
            return {"name": name, "label": label, "type": "integer"}

        # 邮箱 → text
        if "邮箱" in label_str or "email" in name_str or "mail" in name_str:
            return {"name": name, "label": label, "type": "text", "length": 100}

        # 电话/手机 → text
        if any(kw in label_str for kw in ["电话", "手机", "传真", "座机"]):
            return {"name": name, "label": label, "type": "text", "length": 20}

        # 地址 → text
        if "地址" in label_str:
            return {"name": name, "label": label, "type": "text", "length": 200}

        # ========== 6. 兜底：普通文本 ==========
        return {"name": name, "label": label, "type": "text", "length": 100}

    @expose(
        description="智能添加字段：只传 name 和 label，自动推断字段类型",
        examples=[
            {
                "form_id": -1003,
                "fields": [
                    {"name": "shr", "label": "审核人"},
                    {"name": "sfsp", "label": "是否审批"},
                    {"name": "je", "label": "金额"},
                    {"name": "bz", "label": "备注"},
                    {"name": "fj", "label": "附件"},
                ]
            }
        ]
    )
    def auto_add_fields(self, form_id: int, fields: List[Dict]) -> Dict:
        """
        智能添加字段——只需传 name 和 label，自动推断类型。

        :param form_id: 表单 ID
        :param fields: 字段列表，每个字段只需 name + label（可选覆盖参数）
        :return: {"form_id": int, "fields_added": int, "detected": [...]}
        """
        if not form_id:
            raise ValueError("表单 ID 不能为空")
        if not fields:
            raise ValueError("字段列表不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 验证表单存在
            cursor.execute("SELECT tablename FROM workflow_bill WHERE id = %s", (form_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("表单不存在，ID=%d" % form_id)
            table_name = self._decode(row[0])

            # 自动推断每个字段的类型
            detected = []
            resolved_fields = []
            for field in fields:
                name = field.get("name", "")
                label = field.get("label", "")
                if not name or not label:
                    raise ValueError("字段 name 和 label 不能为空")

                # 如果用户已指定 type，直接用；否则自动推断
                if "type" in field:
                    resolved_fields.append(field)
                    detected.append({"name": name, "label": label, "type": field["type"], "mode": "manual"})
                else:
                    cfg = self._auto_detect_field_type(cursor, name, label)
                    # 用户传入的额外参数合并进去
                    for k, v in field.items():
                        cfg[k] = v
                    resolved_fields.append(cfg)
                    detected.append({"name": name, "label": label, "type": cfg["type"], "mode": "auto"})

            # 批量添加
            self._add_fields(cursor, form_id, table_name, resolved_fields)
            conn.commit()

            return {"form_id": form_id, "fields_added": len(fields), "detected": detected}

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  表单（Form）操作
    # ============================================================

    @expose(
        description="在泛微 OA 建模引擎中创建一个新表单（含物理表和字段）",
        examples=[
            {
                "form_name": "测试订单",
                "app_id": 1054,
                "table_name": "uf_TestOrder",
                "fields": [
                    {"name": "applyuser", "label": "申请人", "type": "browser", "browser_id": 3},
                    {"name": "applydate", "label": "申请日期", "type": "text"}
                ]
            }
        ],
        error_hints={
            "表单名称不能为空": "请提供 form_name",
            "表名必须以 uf_ 开头": "table_name 需以 uf_ 开头",
            "应用不存在": "请检查 app_id 是否正确"
        }
    )
    def create_form(
        self,
        form_name: str,
        app_id: int,
        table_name: str = None,
        form_description: str = "",
        fields: List[Dict] = None,
        detail_tables: List[Dict] = None
    ) -> Dict:
        """
        创建表单（含物理表 + 字段）

        :param form_name: 表单名称（必填）
        :param app_id: 所属应用 ID（必填）
        :param table_name: 物理表名，默认自动生成（uf_ 开头，选填）
        :param form_description: 表单描述（选填）
        :param fields: 字段列表，每个字段是 dict，详见下方说明（选填）
        :param detail_tables: 明细表配置（选填）。格式：[{"name": "表名(uf_xxx_dt1)", "fields": [{"name": "字段名", "label": "标签", "type": "类型"}]}]
        :return: {"form_id": int, "table_name": str}

        字段 dict 格式：
            {
                "name": "字段名（英文）",
                "label": "字段标签（中文）",
                "type": "text|textarea|browser|checkbox|dropdown|radio|multiselect|integer|float|amount|amount-format|file|special|pubchoice",
                    text=普通文本(默认varchar100)
                    integer=整数、float=浮点数(2位小数)、
                    amount=金额转换(中文大写)、amount-format=金额千分位(2位小数)
                "db_type": "varchar(100)|integer|decimal(18,2)|text|char(1)",  # 可选，自动推断
                "browser_id": 1,  # 仅浏览框需要：浏览框 ID，或用 browser_name 代替
                "browser_name": "人力资源",  # 仅浏览框需要：浏览框名称，与 browser_id 二选一
                "is_multi": False,  # 仅浏览框需要：是否多选（系统/自定义浏览框）
                "is_tree": False,  # 仅浏览框需要：是否自定义树形浏览框
                "length": 100,  # 仅 text 类型需要
                "options": ["男", "女"],  # 仅 dropdown/radio/multiselect 需要
                "show_order": 1  # 显示顺序，默认从 1 开始
            }
        """
        if not form_name or not form_name.strip():
            raise ValueError("表单名称不能为空")
        if not app_id:
            raise ValueError("应用 ID 不能为 0")

        # 验证应用存在
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM modeTreeField WHERE id = %s AND isdelete = 0", (app_id,))
            if not cursor.fetchone():
                raise ValueError("应用不存在，ID=%d" % app_id)

            # 生成表名（uf_ + 拼音首字母，纯英文+数字+下划线，≤20字符）
            if not table_name:
                table_name = self._generate_table_name(form_name)
            if not table_name.startswith("uf_"):
                raise ValueError("表名必须以 uf_ 开头")
            if len(table_name) > 20:
                table_name = table_name[:20]

            # ========== 第 1 步：表名校验 ==========
            table_name = self._check_table_name_available(cursor, table_name)

            # ========== 第 2 步：创建表单主记录 ==========
            label_id = self._create_label(cursor, form_name)
            form_id = self._get_next_form_id(cursor)
            cursor.execute(
                "INSERT INTO workflow_bill(id, namelabel, tablename, detailkeyfield, formdes, subcompanyid, subCompanyId3, invalid) "
                "VALUES(%s, %s, %s, 'mainid', %s, 0, -1, NULL)",
                (form_id, label_id, table_name, self._encode(form_description))
            )
            # 验证 workflow_bill 和 namelabel 关联都存在
            cursor.execute("SELECT COUNT(*) FROM workflow_bill WHERE id = %s", (form_id,))
            if int(cursor.fetchone()[0]) == 0:
                raise RuntimeError("workflow_bill 插入失败：id=%d" % form_id)
            cursor.execute(
                "SELECT COUNT(*) FROM HtmlLabelIndex WHERE id = %s", (label_id,)
            )
            if int(cursor.fetchone()[0]) == 0:
                raise RuntimeError(
                    "namelabel=%d 在 HtmlLabelIndex 中不存在，表单将产生空引用" % label_id
                )

            # ========== 第 3 步：创建物理表 ==========
            cursor.execute(
                "CREATE TABLE [%s] (id int IDENTITY(1,1) primary key CLUSTERED, requestId int)" % table_name
            )

            # ========== 第 3.5 步：添加系统字段 ==========
            system_columns = [
                ("formmodeid",          "int"),
                ("modedatacreater",     "int"),
                ("modedatacreatertype", "int"),
                ("modedatacreatedate",  "varchar(10)"),
                ("modedatacreatetime",  "varchar(8)"),
                ("modedatamodifier",    "int"),
                ("modedatamodifydatetime", "varchar(100)"),
                ("form_biz_id",         "varchar(100)"),
                ("MODEUUID",            "varchar(100)"),
            ]
            for col_name, col_type in system_columns:
                cursor.execute(
                    "ALTER TABLE [%s] add [%s] %s" % (table_name, col_name, col_type)
                )

            # ========== 第 4 步：关联到应用 ==========
            cursor.execute(
                "INSERT INTO AppFormInfo(appid, formid) VALUES(%s, %s)",
                (app_id, form_id)
            )

            # ========== 第 5 步：添加字段 ==========
            if fields:
                for field in fields:
                    label_val = field.get("label", field.get("name", ""))
                    # AI 明确指定了 type：用 AI 的 type，auto-detect 只补充缺失参数（如 browser_id）
                    # AI 未指定 type：用 auto-detect 全量推断
                    if field.get("type") is not None:
                        try:
                            detected = self._auto_detect_field_type(cursor, field.get("name", ""), label_val)
                            for k, v in detected.items():
                                if k not in field:
                                    field[k] = v
                        except ValueError:
                            # AI 已明确指定 type，auto-detect 失败不阻塞，直接用 AI 的配置
                            pass
                    else:
                        detected = self._auto_detect_field_type(cursor, field.get("name", ""), label_val)
                        for k, v in detected.items():
                            field[k] = v
                self._add_fields(cursor, form_id, table_name, fields)

            # ========== 第 6 步：创建明细表（如有） ==========
            if detail_tables:
                self._create_detail_tables(cursor, form_id, table_name, detail_tables)

            conn.commit()

            # 校验：下拉/单选/多选字段必须有选项
            cursor.execute(
                "SELECT id, fieldname FROM workflow_billfield "
                "WHERE billid = %s AND fieldhtmltype = '5'",
                (form_id,)
            )
            missing_options = []
            for row in cursor.fetchall():
                fid, fname = row[0], row[1]
                cursor.execute(
                    "SELECT COUNT(*) FROM workflow_SelectItem WHERE fieldid = %s",
                    (fid,)
                )
                if int(cursor.fetchone()[0]) == 0:
                    missing_options.append(fname)
            if missing_options:
                import warnings
                warnings.warn(
                    "下拉字段缺少选项：%s — 请在字段定义中传入 options 参数"
                    % ", ".join(missing_options)
                )

            # 刷新 label 缓存，确保线上立即生效
            refresh_result = refresh_label_cache()

            return {
                "form_id": form_id,
                "table_name": table_name,
                "cache_refreshed": refresh_result.get("status") == "1"
            }

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def _add_fields(self, cursor, form_id: int, table_name: str, fields: List[Dict]):
        """批量添加字段（内部方法，不直接暴露）"""
        type_map = {
            # htmltype=1 文本类
            "text":        {"htmltype": 1, "dbtype": "varchar(%d)", "type_val": 1, "qfws": 0},
            "integer":     {"htmltype": 1, "dbtype": "int",            "type_val": 2, "qfws": 0},
            "float":       {"htmltype": 1, "dbtype": "decimal(38,2)",  "type_val": 3, "qfws": 2},
            "amount":      {"htmltype": 1, "dbtype": "decimal(15,2)",  "type_val": 4, "qfws": 0},
            "amount-format":{"htmltype": 1, "dbtype": "varchar(30)",   "type_val": 5, "qfws": 2},
            # 其他类型
            "textarea":  {"htmltype": 2, "dbtype": "text", "type_val": 1, "qfws": 0, "textheight": 4},
            "browser":   {"htmltype": 3, "dbtype": "int", "type_val": 0, "qfws": 0},  # type/fielddbtype 动态计算
            "checkbox":  {"htmltype": 4, "dbtype": "char(1)", "type_val": 1, "qfws": 0},
            "dropdown":  {"htmltype": 5, "dbtype": "int", "type_val": 1, "qfws": 0},
            "radio":     {"htmltype": 5, "dbtype": "int", "type_val": 3, "qfws": 0},
            "multiselect":{"htmltype": 5, "dbtype": "text", "type_val": 2, "qfws": 0},
            "file":      {"htmltype": 6, "dbtype": "text", "type_val": 1, "qfws": 0, "textheight": 0},
            "special":   {"htmltype": 7, "dbtype": "varchar(4000)", "type_val": 0, "qfws": 0},
            "pubchoice": {"htmltype": 8, "dbtype": "integer", "type_val": 0, "qfws": 0},
        }

        for i, field in enumerate(fields):
            name = field.get("name", "")
            label = field.get("label", "")
            ftype = field.get("type", "text")
            show_order = field.get("show_order", i + 1)

            if not name or not label:
                raise ValueError("字段 name 和 label 不能为空（第 %d 个字段）" % (i + 1))

            # 检查字段是否已存在（避免重复创建）
            cursor.execute(
                "SELECT id FROM workflow_billfield WHERE billid = %s AND fieldname = %s",
                (form_id, name)
            )
            if cursor.fetchone():
                # 字段已存在，跳过
                continue

            cfg = type_map.get(ftype)
            if not cfg:
                raise ValueError("不支持的字段类型：%s（第 %d 个字段）" % (ftype, i + 1))

            # 确定 fielddbtype
            if ftype == "text":
                length = field.get("length", 100)
                fielddbtype = cfg["dbtype"] % length
            else:
                fielddbtype = field.get("db_type", cfg["dbtype"])

            # 多行文本：textheight 控制显示行数，默认 4；支持 html_editor 切到富文本
            textheight = cfg.get("textheight", 0)
            if ftype == "textarea":
                textheight = field.get("rows", textheight)
            imgwidth = 0
            imgheight = 0
            if ftype == "file":
                textheight = field.get("rows", textheight)
            type_val = cfg["type_val"]
            if ftype == "textarea" and field.get("html_editor"):
                type_val = 2  # HTML 富文本编辑器
            if ftype == "file" and field.get("image"):
                type_val = 2  # 上传图片模式
                imgwidth = field.get("img_width", 100)
                imgheight = field.get("img_height", 100)

            # 物理表列类型默认值等于元数据 fielddbtype
            physical_type = fielddbtype

            # 浏览框特殊处理：支持 browser_id 或 browser_name
            # 同时计算 type 和 fielddbtype（不同浏览框类型规则不同）
            # 注意：所有浏览框字段的 linkfield 都为 0，浏览框识别靠 type+fielddbtype
            linkfield = 0
            if ftype == "browser":
                browser_id = self._resolve_browser_id(cursor, field)
                if browser_id == 0:
                    raise ValueError("浏览框字段必须指定 browser_id 或 browser_name（第 %d 个字段）" % (i + 1))

                # 根据浏览框类型计算 type 和 fielddbtype
                is_tree = field.get("is_tree", False)
                is_multi = field.get("is_multi", False)
                if is_tree:
                    # 自定义树形浏览框：type=256(单选)/257(多选)
                    type_val = 257 if is_multi else 256
                    # 查 MODE_BROWSER WHERE customid（mode_custombrowser 的 id）
                    cursor.execute(
                        "SELECT showname FROM MODE_BROWSER WHERE customid = %s",
                        (browser_id,)
                    )
                    show_row = cursor.fetchone()
                    showname = show_row[0] if show_row else str(browser_id)
                    fielddbtype = "browser.%s" % str(showname)
                    physical_type = "varchar(1000)"  # 物理列类型
                else:
                    # 先查 workflow_browserurl 是否存在
                    cursor.execute(
                        "SELECT fielddbtype FROM workflow_browserurl WHERE id = %s",
                        (browser_id,)
                    )
                    br_row = cursor.fetchone()
                    if br_row:
                        # 系统浏览框 / 集成浏览框：type=browser_id, fielddbtype=表中值
                        # 系统浏览框单选/多选是不同 ID（如人员=1/多人力资源=17），
                        # 当 is_multi=True 且 browser_id=1 时自动切换为 17
                        if is_multi and browser_id == 1:
                            browser_id = 17
                            cursor.execute(
                                "SELECT fielddbtype FROM workflow_browserurl WHERE id = %s",
                                (browser_id,)
                            )
                            br_row = cursor.fetchone()
                        type_val = browser_id
                        fielddbtype = str(br_row[0])
                        # 物理列类型必须跟元数据 fielddbtype 对齐
                        physical_type = fielddbtype
                        # 允许 db_type 覆盖物理列类型（如日期字段需存 char(10) 而非 int）
                        if "db_type" in field:
                            physical_type = field["db_type"]
                    else:
                        # 自定义浏览框（不在 workflow_browserurl 中）
                        type_val = 162 if is_multi else 161
                        # 查 MODE_BROWSER WHERE customid（mode_custombrowser 的 id）
                        cursor.execute(
                            "SELECT showname FROM MODE_BROWSER WHERE customid = %s",
                            (browser_id,)
                        )
                        show_row = cursor.fetchone()
                        showname = show_row[0] if show_row else "s"
                        fielddbtype = "browser.%s" % str(showname)
                        physical_type = "varchar(1000)"  # 物理列类型

            # 创建标签
            field_label_id = self._create_label(cursor, label)

            # INSERT 字段元数据（id 由 IDENTITY 自增生成）
            cursor.execute(
                "INSERT INTO workflow_billfield("
                "billid, fieldname, fieldlabel, fielddbtype, fieldhtmltype, type, "
                "dsporder, viewtype, detailtable, textheight, textheight_2, "
                "childfieldid, imgwidth, imgheight, places, qfws, "
                "selectitem, linkfield, selectItemType, pubchoiceId, pubchilchoiceId, "
                "locatetype, fieldshowtypes"
                ") VALUES("
                "%s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, "
                "%s, %s"
                ")",
                (
                    form_id, name, field_label_id, fielddbtype, cfg["htmltype"], type_val,
                    show_order, 0, "", textheight, "",
                    -1, imgwidth, imgheight, 0, cfg["qfws"],
                    0, linkfield, 0, 0, 0,
                    "", 1
                )
            )
            # 获取刚生成的 billfield id（用于 SelectItem 关联）
            cursor.execute("SELECT SCOPE_IDENTITY()")
            row = cursor.fetchone()
            field_id = int(row[0]) if row else None
            if field_id is None:
                raise RuntimeError("无法获取 workflow_billfield 自增 ID")

            # 安全校验：非浏览框字段，物理列类型必须与元数据 fielddbtype 一致
            if not fielddbtype.startswith("browser.") and physical_type != fielddbtype:
                raise RuntimeError(
                    "字段 '%s' 物理列类型(%s)与元数据 fielddbtype(%s)不一致，拒绝创建"
                    % (name, physical_type, fielddbtype)
                )

            # 检查物理列是否已存在（避免重复 ALTER TABLE）
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = %s AND COLUMN_NAME = %s",
                (table_name, name)
            )
            if cursor.fetchone()[0] == 0:
                # ALTER TABLE 物理表加列（使用 physical_type，浏览框元数据 fielddbtype 可能是 browser.xxx）
                cursor.execute(
                    "ALTER TABLE [%s] add [%s] %s" % (table_name, name, physical_type)
                )

            # 选项型字段（dropdown/radio/multiselect）：写入 workflow_SelectItem
            if ftype in ("dropdown", "radio", "multiselect"):
                options = field.get("options", [])
                if isinstance(options, str):
                    options = [o.strip() for o in options.split("|") if o.strip()]
                if options:
                    for idx, opt in enumerate(options):
                        opt_name = opt if isinstance(opt, str) else opt.get("name", "")
                        opt_value = opt.get("value", idx) if isinstance(opt, dict) else idx
                        cursor.execute(
                            "INSERT INTO workflow_SelectItem("
                            "fieldid, isbill, selectvalue, selectname, listorder, isdefault"
                            ") VALUES(%s, %s, %s, %s, %s, %s)",
                            (field_id, 1, opt_value, self._encode(opt_name), idx, "n")
                        )

    def _create_detail_tables(self, cursor, form_id: int, main_table: str, detail_tables: List[Dict]):
        """
        创建明细表：物理表 + workflow_billdetailtable 注册 + workflow_billfield 字段
        """
        import uuid as _uuid

        # 查询主表已有的明细表，确定起始 orderid 和表名序号
        cursor.execute(
            "SELECT MAX(orderid) FROM workflow_billdetailtable WHERE billid = %s",
            (form_id,)
        )
        row = cursor.fetchone()
        max_order = int(row[0]) if row and row[0] else 0
        next_order = max_order + 1

        # 查最后一个明细表的表名，提取数字后缀
        cursor.execute(
            "SELECT TOP 1 tablename FROM workflow_billdetailtable "
            "WHERE billid = %s ORDER BY orderid DESC",
            (form_id,)
        )
        last_row = cursor.fetchone()
        if last_row:
            last_name = str(last_row[0] or "")
            if "_dt" in last_name:
                try:
                    base_suffix = int(last_name.split("_dt")[1]) + 1
                except ValueError:
                    base_suffix = next_order
            else:
                base_suffix = next_order
        else:
            base_suffix = 1

        type_map = {
            "text":        {"htmltype": 1, "dbtype": "varchar(%d)", "type_val": 1, "qfws": 0},
            "integer":     {"htmltype": 1, "dbtype": "int",            "type_val": 2, "qfws": 0},
            "float":       {"htmltype": 1, "dbtype": "decimal(38,2)",  "type_val": 3, "qfws": 2},
            "amount":      {"htmltype": 1, "dbtype": "decimal(15,2)",  "type_val": 4, "qfws": 0},
            "amount-format":{"htmltype": 1, "dbtype": "varchar(30)",   "type_val": 5, "qfws": 2},
            "textarea":  {"htmltype": 2, "dbtype": "text", "type_val": 1, "qfws": 0, "textheight": 4},
            "browser":   {"htmltype": 3, "dbtype": "int", "type_val": 0, "qfws": 0},
            "checkbox":  {"htmltype": 4, "dbtype": "char(1)", "type_val": 1, "qfws": 0},
            "dropdown":  {"htmltype": 5, "dbtype": "int", "type_val": 1, "qfws": 0},
            "radio":     {"htmltype": 5, "dbtype": "int", "type_val": 3, "qfws": 0},
            "multiselect":{"htmltype": 5, "dbtype": "text", "type_val": 2, "qfws": 0},
            "file":      {"htmltype": 6, "dbtype": "text", "type_val": 1, "qfws": 0, "textheight": 0},
            "special":   {"htmltype": 7, "dbtype": "varchar(4000)", "type_val": 0, "qfws": 0},
            "pubchoice": {"htmltype": 8, "dbtype": "integer", "type_val": 0, "qfws": 0},
        }

        for dt in detail_tables:
            dt_name = dt.get("name", "")
            dt_fields = dt.get("fields", [])
            if not dt_name:
                # 自动生成表名：主表名_dt{序号}
                dt_name = "%s_dt%d" % (main_table, base_suffix)
            orderid = next_order

            # 1. 创建物理表：id 自增 + mainid + 业务字段
            cursor.execute(
                "CREATE TABLE [%s] (id int IDENTITY(1,1) primary key CLUSTERED, mainid int)" % dt_name
            )

            # 2. 注册到 workflow_billdetailtable
            uid = str(_uuid.uuid4()).upper()
            cursor.execute(
                "INSERT INTO workflow_billdetailtable (billid, tablename, title, orderid, uuid) "
                "VALUES(%s, %s, %s, %s, %s)",
                (form_id, dt_name, "", orderid, uid)
            )

            # 3. 添加字段到 workflow_billfield（viewtype=1 表示明细表字段）
            for i, field in enumerate(dt_fields):
                name = field.get("name", "")
                label = field.get("label", "")
                ftype = field.get("type", "text")
                show_order = field.get("show_order", i + 1)

                if not name or not label:
                    continue

                # 检查字段是否已存在（避免重复创建）
                cursor.execute(
                    "SELECT id FROM workflow_billfield WHERE billid = %s AND fieldname = %s AND detailtable = %s",
                    (form_id, name, dt_name)
                )
                if cursor.fetchone():
                    # 字段已存在，跳过
                    continue

                cfg = type_map.get(ftype)
                if not cfg:
                    raise ValueError("明细表不支持的字段类型：'%s'（字段 '%s'）" % (ftype, name))

                fielddbtype = cfg["dbtype"]
                if ftype == "text":
                    length = field.get("length", 100)
                    fielddbtype = cfg["dbtype"] % length
                    physical_type = fielddbtype
                else:
                    physical_type = field.get("db_type", cfg["dbtype"])

                textheight = cfg.get("textheight", 0)
                type_val = cfg["type_val"]
                linkfield = 0
                if ftype == "textarea":
                    textheight = field.get("rows", textheight)
                if ftype == "file":
                    textheight = field.get("rows", textheight)
                if ftype == "textarea" and field.get("html_editor"):
                    type_val = 2
                if ftype == "file" and field.get("image"):
                    type_val = 2

                # 浏览框处理：与主表 _add_fields 逻辑对齐
                if ftype == "browser":
                    browser_id = field.get("browser_id", 0)
                    browser_name = field.get("browser_name", "")
                    if not browser_id and browser_name:
                        # 复用 _resolve_browser_id 逻辑
                        browser_id = self._resolve_browser_id(cursor, field)
                    if browser_id == 0:
                        raise ValueError("明细表浏览框字段必须指定 browser_id 或 browser_name（字段 '%s'）" % name)

                    is_tree = field.get("is_tree", False)
                    is_multi = field.get("is_multi", False)
                    if is_tree:
                        type_val = 257 if is_multi else 256
                        cursor.execute(
                            "SELECT showname FROM MODE_BROWSER WHERE customid = %s",
                            (browser_id,)
                        )
                        show_row = cursor.fetchone()
                        showname = show_row[0] if show_row else str(browser_id)
                        fielddbtype = "browser.%s" % str(showname)
                        physical_type = "varchar(1000)"
                    else:
                        cursor.execute(
                            "SELECT fielddbtype FROM workflow_browserurl WHERE id = %s",
                            (browser_id,)
                        )
                        br_row = cursor.fetchone()
                        if br_row:
                            if is_multi and browser_id == 1:
                                browser_id = 17
                                cursor.execute(
                                    "SELECT fielddbtype FROM workflow_browserurl WHERE id = %s",
                                    (browser_id,)
                                )
                                br_row = cursor.fetchone()
                            type_val = browser_id
                            fielddbtype = str(br_row[0])
                            # 物理列类型必须跟元数据 fielddbtype 对齐
                            physical_type = fielddbtype
                        else:
                            type_val = 162 if is_multi else 161
                            cursor.execute(
                                "SELECT showname FROM MODE_BROWSER WHERE customid = %s",
                                (browser_id,)
                            )
                            show_row = cursor.fetchone()
                            showname = show_row[0] if show_row else "s"
                            fielddbtype = "browser.%s" % str(showname)
                            physical_type = "varchar(1000)"  # browser.xxx 不是 SQL 类型
                        # 允许 db_type 覆盖物理列类型
                        if "db_type" in field:
                            physical_type = field["db_type"]

                # 选项字段
                if ftype in ("dropdown", "radio", "multiselect"):
                    fielddbtype = "int" if ftype in ("dropdown", "radio") else "text"

                # 创建标签
                field_label_id = self._create_label(cursor, label)

                # 插入 workflow_billfield（viewtype=1, detailtable=表名）
                cursor.execute(
                    "INSERT INTO workflow_billfield("
                    "billid, fieldname, fieldlabel, fielddbtype, fieldhtmltype, type, "
                    "dsporder, viewtype, detailtable, textheight, textheight_2, "
                    "childfieldid, imgwidth, imgheight, places, qfws, "
                    "selectitem, linkfield, selectItemType, pubchoiceId, pubchilchoiceId, "
                    "locatetype, fieldshowtypes"
                    ") VALUES("
                    "%s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, "
                    "%s, %s"
                    ")",
                    (
                        form_id, name, field_label_id, fielddbtype, cfg["htmltype"], type_val,
                        show_order, 1, dt_name, textheight, "",
                        -1, 0, 0, 0, cfg["qfws"],
                        0, linkfield, 0, 0, 0,
                        "", 1
                    )
                )
                cursor.execute("SELECT SCOPE_IDENTITY()")
                field_id_row = cursor.fetchone()
                field_id = int(field_id_row[0]) if field_id_row else None

                # 安全校验：非浏览框字段，物理列类型必须与元数据 fielddbtype 一致
                if not fielddbtype.startswith("browser.") and physical_type != fielddbtype:
                    raise RuntimeError(
                        "明细表字段 '%s' 物理列类型(%s)与元数据 fielddbtype(%s)不一致，拒绝创建"
                        % (name, physical_type, fielddbtype)
                    )

                # 检查物理列是否已存在（避免重复 ALTER TABLE）
                cursor.execute(
                    "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_NAME = %s AND COLUMN_NAME = %s",
                    (dt_name, name)
                )
                if cursor.fetchone()[0] == 0:
                    # 物理表加列
                    cursor.execute(
                        "ALTER TABLE [%s] add [%s] %s" % (dt_name, name, physical_type)
                    )

                # 选项型字段写入 SelectItem
                if ftype in ("dropdown", "radio", "multiselect"):
                    options = field.get("options", [])
                    if isinstance(options, str):
                        options = [o.strip() for o in options.split("|") if o.strip()]
                    if options:
                        for idx, opt in enumerate(options):
                            opt_name = opt if isinstance(opt, str) else opt.get("name", "")
                            opt_value = opt.get("value", idx) if isinstance(opt, dict) else idx
                            cursor.execute(
                                "INSERT INTO workflow_SelectItem("
                                "fieldid, isbill, selectvalue, selectname, listorder, isdefault"
                                ") VALUES(%s, %s, %s, %s, %s, %s)",
                                (field_id, 1, opt_value, self._encode(opt_name), idx, "n")
                            )

            next_order += 1
            base_suffix += 1

    @expose(
        description="在泛微 OA 建模引擎已有表单上批量添加字段",
        examples=[
            {
                "form_id": 243,
                "fields": [
                    {"name": "applyuser", "label": "申请人", "type": "browser", "browser_id": 3},
                    {"name": "amount", "label": "金额", "type": "text", "db_type": "decimal(18,2)"}
                ]
            }
        ],
        error_hints={
            "表单不存在": "请检查 form_id 是否正确"
        }
    )
    def add_fields(
        self,
        form_id: int,
        fields: List[Dict]
    ) -> Dict:
        """
        在已有表单上批量添加字段

        :param form_id: 表单 ID（必填）
        :param fields: 字段列表（必填），格式同 create_form 的 fields 参数
        :return: {"form_id": int, "fields_added": int}
        """
        if not form_id:
            raise ValueError("表单 ID 不能为空")
        if not fields:
            raise ValueError("字段列表不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 验证表单存在，获取表名
            cursor.execute("SELECT tablename FROM workflow_bill WHERE id = %s", (form_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("表单不存在，ID=%d" % form_id)
            table_name = self._decode(row[0])

            self._add_fields(cursor, form_id, table_name, fields)
            conn.commit()

            return {"form_id": form_id, "fields_added": len(fields)}

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="查询泛微 OA 建模引擎中表单的字段列表",
        examples=[
            {"form_id": 243},
            {"form_id": 243, "include_detail": True}
        ],
        read_only=True
    )
    def list_form_fields(
        self,
        form_id: int,
        include_detail: bool = False
    ) -> List[Dict]:
        """
        查询表单字段列表

        :param form_id: 表单 ID（必填）
        :param include_detail: 是否包含明细表字段（默认 False）
        :return: 字段列表
        """
        if not form_id:
            raise ValueError("表单 ID 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            sql = (
                "SELECT f.id, f.fieldname, f.fielddbtype, f.fieldhtmltype, f.type, "
                "f.dsporder, f.viewtype, f.detailtable, f.linkfield, h.labelname "
                "FROM workflow_billfield f "
                "LEFT JOIN HtmlLabelInfo h ON f.fieldlabel = h.indexid AND h.languageid = 7 "
                "WHERE f.billid = %s AND f.viewtype = 0 "
                "ORDER BY f.dsporder, f.id"
            )
            cursor.execute(sql, (form_id,))

            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": int(row[0]),
                    "name": str(row[1] or ""),
                    "dbType": str(row[2] or ""),
                    "htmlType": int(row[3] or 0),
                    "type": int(row[4] or 0),
                    "showOrder": int(row[5] or 0),
                    "viewType": int(row[6] or 0),
                    "detailTable": str(row[7] or ""),
                    "linkField": int(row[8] or 0),
                    "label": self._decode(row[9])
                })

            # 如果需要明细表字段
            if include_detail:
                cursor.execute(
                    "SELECT tablename FROM workflow_billdetailtable WHERE billid = %s ORDER BY orderid",
                    (form_id,)
                )
                detail_tables = [str(r[0]) for r in cursor.fetchall()]

                for dt_name in detail_tables:
                    cursor.execute(
                        "SELECT f.id, f.fieldname, f.fielddbtype, f.fieldhtmltype, f.type, "
                        "f.dsporder, h.labelname "
                        "FROM workflow_billfield f "
                        "LEFT JOIN HtmlLabelInfo h ON f.fieldlabel = h.indexid AND h.languageid = 7 "
                        "WHERE f.billid = %s AND f.viewtype = 1 AND f.detailtable = %s "
                        "ORDER BY f.dsporder, f.id",
                        (form_id, dt_name)
                    )
                    for row in cursor.fetchall():
                        result.append({
                            "id": int(row[0]),
                            "name": str(row[1] or ""),
                            "dbType": str(row[2] or ""),
                            "htmlType": int(row[3] or 0),
                            "type": int(row[4] or 0),
                            "showOrder": int(row[5] or 0),
                            "viewType": 1,
                            "detailTable": dt_name,
                            "label": self._decode(row[6])
                        })

            return result

        finally:
            cursor.close()
            conn.close()

    @expose(
        description="删除泛微 OA 建模引擎中的表单（物理表 + 元数据 + 本表单专属标签）",
        examples=[
            {"form_id": 243}
        ],
        destructive=True
    )
    def delete_form(self, form_id: int) -> Dict:
        """
        删除表单（物理表 + 元数据 + 本表单专属标签）

        安全规则：
        1. 标签删除前检查是否被其他表单引用，如有引用则跳过标签删除
        2. 只删除本表单 workflow_billfield 中实际引用的 fieldlabel
        3. 物理表删除失败不阻断元数据清理

        :param form_id: 表单 ID（必填）
        :return: {"form_id": int, "table_name": str, "fields_deleted": int, "labels_skipped": int}
        """
        if not form_id:
            raise ValueError("表单 ID 不能为空")

        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 获取表名和标签 ID
            cursor.execute("SELECT tablename, namelabel FROM workflow_bill WHERE id = %s", (form_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("表单不存在，ID=%d" % form_id)
            table_name = self._decode(row[0])
            name_label_id = int(row[1] or 0)

            # 收集字段元数据
            cursor.execute("SELECT id, fieldname, fieldlabel FROM workflow_billfield WHERE billid = %s", (form_id,))
            fields = cursor.fetchall()
            fields_deleted = len(fields)
            labels_skipped = 0

            for field_row in fields:
                fid = int(field_row[0])
                fname = str(field_row[1] or "")
                flabel_id = int(field_row[2] or 0)

                # 删除物理列（跳过 id 和 requestId）
                if fname.lower() not in ("id", "requestid"):
                    try:
                        cursor.execute("ALTER TABLE [%s] drop column [%s]" % (table_name, fname))
                    except Exception:
                        pass  # 列可能已被删除

                # 删除标签前检查是否被其他表单引用
                if flabel_id > 0:
                    cursor.execute(
                        "SELECT COUNT(*) FROM workflow_billfield WHERE fieldlabel = %s AND billid != %s",
                        (flabel_id, form_id)
                    )
                    ref_count = int(cursor.fetchone()[0])
                    if ref_count > 0:
                        # 被其他表单引用，跳过标签删除
                        labels_skipped += 1
                    else:
                        cursor.execute("DELETE FROM HtmlLabelInfo WHERE indexid = %s", (flabel_id,))
                        cursor.execute("DELETE FROM HtmlLabelIndex WHERE id = %s", (flabel_id,))

            # 删除字段选项（下拉框/单选/多选的选项值）
            cursor.execute(
                "DELETE FROM workflow_SelectItem WHERE fieldid IN "
                "(SELECT id FROM workflow_billfield WHERE billid = %s)",
                (form_id,)
            )

            # 删除字段元数据
            cursor.execute("DELETE FROM workflow_billfield WHERE billid = %s", (form_id,))

            # 删除明细表：注册记录 + 物理表（元数据已在上面 workflow_billfield 删除中清理）
            cursor.execute(
                "SELECT tablename FROM workflow_billdetailtable WHERE billid = %s ORDER BY orderid",
                (form_id,)
            )
            detail_tables = [str(r[0]) for r in cursor.fetchall()]
            if detail_tables:
                # 删除明细表注册记录
                cursor.execute(
                    "DELETE FROM workflow_billdetailtable WHERE billid = %s",
                    (form_id,)
                )
                # 删除明细表物理表（失败不阻断）
                for dt_name in detail_tables:
                    try:
                        cursor.execute("DROP TABLE [%s]" % dt_name)
                    except Exception:
                        pass

            # 删除物理表（失败不阻断）
            try:
                cursor.execute("DROP TABLE [%s]" % table_name)
            except Exception:
                pass

            # 删除应用关联
            cursor.execute("DELETE FROM AppFormInfo WHERE formid = %s", (form_id,))

            # 连带删除关联的模块、权限、查询（防止留垃圾）
            cursor.execute("SELECT id FROM modeinfo WHERE formid = %s", (form_id,))
            mode_ids = [int(r[0]) for r in cursor.fetchall()]
            if mode_ids:
                placeholders = ','.join(['%s'] * len(mode_ids))
                cursor.execute(f"DELETE FROM mode_customsearch WHERE modeid IN ({placeholders})", mode_ids)
                cursor.execute(f"DELETE FROM moderightinfo WHERE modeid IN ({placeholders})", mode_ids)
                cursor.execute(f"DELETE FROM modeinfo WHERE id IN ({placeholders})", mode_ids)

            # 删除表单主记录和标签
            cursor.execute("DELETE FROM workflow_bill WHERE id = %s", (form_id,))
            if name_label_id > 0:
                cursor.execute(
                    "SELECT COUNT(*) FROM workflow_billfield WHERE fieldlabel = %s",
                    (name_label_id,)
                )
                if int(cursor.fetchone()[0]) == 0:
                    cursor.execute("DELETE FROM HtmlLabelInfo WHERE indexid = %s", (name_label_id,))
                    cursor.execute("DELETE FROM HtmlLabelIndex WHERE id = %s", (name_label_id,))
                else:
                    labels_skipped += 1

            conn.commit()

            return {
                "form_id": form_id,
                "table_name": table_name,
                "fields_deleted": fields_deleted,
                "labels_skipped": labels_skipped
            }

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @expose(
        description="查询泛微 OA 建模引擎中的表单列表",
        examples=[
            {"app_id": 1054},
            {}
        ],
        read_only=True
    )
    def list_forms(self, app_id: int = None) -> List[Dict]:
        """
        查询表单列表

        :param app_id: 应用 ID 过滤（选填）
        :return: 表单列表
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            sql = (
                "SELECT b.id, b.tablename, b.formdes, b.subcompanyid, h.labelname "
                "FROM workflow_bill b "
                "LEFT JOIN HtmlLabelInfo h ON b.namelabel = h.indexid AND h.languageid = 7"
            )
            params = []

            if app_id:
                sql += " INNER JOIN AppFormInfo af ON b.id = af.formid AND af.appid = %s"
                params.append(app_id)

            sql += " ORDER BY b.id"

            cursor.execute(sql, tuple(params))

            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": int(row[0]),
                    "tableName": self._decode(row[1]),
                    "description": self._decode(row[2]),
                    "subCompanyId": int(row[3] or 0),
                    "name": self._decode(row[4])
                })

            return result

        finally:
            cursor.close()
            conn.close()
