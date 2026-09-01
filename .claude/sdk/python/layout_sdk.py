# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 布局 JSON 生成

通过直连 SQL Server 数据库，根据表单字段自动生成 datajson 和 pluginjson。

依赖：pip install pymssql

使用示例：
    from layout_sdk import LayoutSDK

    sdk = XXX()  # 配置从 db-config.md 读取

    # 简单调用：自动查询字段，默认按 ID 排序
    result = sdk.generate_layout_json(form_id=-1003)

    # 带分组配置：按业务逻辑排列字段
    result = sdk.generate_layout_json(
        form_id=-1003,
        config={
            "groups": [
                {"name": "基础信息", "fields": ["登记人", "登记日期"]},
                {"name": "住宿信息", "fields": ["房间号", "入住日期"]}
            ]
        }
    )

    # 返回 {"datajson": {...}, "pluginjson": {...}}
"""

import pymssql
import json
import os
from typing import List, Dict, Optional, Tuple, Any

from mcp_register import expose
from db_config import load_db_config


class LayoutSDK:
    """建模引擎 SDK — 布局 JSON 生成"""

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

    # ============================================================
    #  数据库查询
    # ============================================================

    def _query_form_info(self, cursor, form_id: int) -> Dict:
        """查询表单基本信息（formname, modeid）"""
        cursor.execute("""
            SELECT b.id AS formId, b.tablename, l.labelname AS formname, m.id AS modeid
            FROM workflow_bill b
            JOIN HtmlLabelInfo l ON b.namelabel = l.indexid
            LEFT JOIN modeinfo m ON m.formid = b.id AND m.isdelete = 0
            WHERE b.id = %s
        """, (form_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("未找到表单，ID=%d" % form_id)
        return {
            "form_id": int(row[0]),
            "tablename": str(row[1] or ""),
            "formname": str(row[2] or ""),
            "modeid": int(row[3]) if row[3] else 0
        }

    def _query_fields(self, cursor, bill_id: int) -> Tuple[List[Dict], List[Dict]]:
        """
        查询表单字段。
        返回 (main_fields, detail_fields)
        """
        # 主表字段
        cursor.execute("""
            SELECT bf.id, bf.fieldname, l.labelname AS fieldlabel, bf.fieldhtmltype, bf.type,
                   bf.detailtable, bf.fromUser
            FROM workflow_billfield bf
            JOIN HtmlLabelInfo l ON bf.fieldlabel = l.indexid AND l.languageid = 7
            WHERE bf.billid = %s AND (bf.detailtable = '' OR bf.detailtable IS NULL)
              AND bf.fromUser = '1'
            ORDER BY bf.id
        """, (bill_id,))

        main_fields = []
        for row in cursor.fetchall():
            main_fields.append({
                "id": int(row[0]),
                "fieldname": str(row[1] or ""),
                "label": str(row[2] or ""),
                "fieldhtmltype": str(row[3] or ""),
                "type": self._get_field_type(row[4]),
                "is_required": False,
                "detailtable": "",
            })

        # 明细表字段
        cursor.execute("""
            SELECT bf.id, bf.fieldname, l.labelname AS fieldlabel, bf.fieldhtmltype, bf.type,
                   bf.detailtable, bf.fromUser
            FROM workflow_billfield bf
            JOIN HtmlLabelInfo l ON bf.fieldlabel = l.indexid AND l.languageid = 7
            WHERE bf.billid = %s AND bf.detailtable <> '' AND bf.detailtable IS NOT NULL
              AND bf.fromUser = '1'
            ORDER BY bf.detailtable, bf.id
        """, (bill_id,))

        detail_fields = []
        for row in cursor.fetchall():
            detail_fields.append({
                "id": int(row[0]),
                "fieldname": str(row[1] or ""),
                "label": str(row[2] or ""),
                "fieldhtmltype": str(row[3] or ""),
                "type": self._get_field_type(row[4]),
                "is_required": False,
                "detailtable": str(row[5] or "")
            })

        return main_fields, detail_fields

    def _get_field_type(self, raw_type) -> str:
        """将数据库 type 编码映射为布局用的控件类型"""
        type_map = {
            1: "text",       # 单行文本
            3: "input",      # 浮点数/金额
            2: "browser",    # 日期
            4: "browser",    # 人员
            402: "browser",  # 部门
            403: "browser",  # 分部
            161: "browser",  # 浏览框
            7: "textarea",   # 多行文本
            20: "text",      # 下拉框
            30: "checkbox",  # 是否选择
        }
        return type_map.get(int(raw_type) if raw_type else 0, "text")

    def _get_bg_image(self, field_type: str, is_required: bool) -> str:
        """生成字段控件的 backgroundImage 路径"""
        suffix = "3" if is_required else "2"
        return "/formmode/exceldesign/image/controls/%s%s_wev8.png" % (field_type, suffix)

    # ============================================================
    #  分组配置处理
    # ============================================================

    def _apply_config(self, main_fields: List[Dict], config: Optional[Dict]) -> Tuple[List[Dict], Optional[List[Dict]]]:
        """
        应用分组配置，重排字段顺序。
        返回 (reordered_fields, groups_info)
        groups_info: [{"name": "基础信息", "count": 3}, ...]

        排序规则：严格按 config 中 fields 列表的顺序，不依赖表单原有 dsporder。
        """
        if not config or "groups" not in config:
            return main_fields, None

        groups = config["groups"]
        groups_info = []
        reordered = []
        used_ids = set()

        # 按 config 的字段顺序匹配，而非表单原有顺序
        for group in groups:
            name = group.get("name", "")
            field_names = [f.lower() for f in group.get("fields", [])]
            matched = []

            for keyword in field_names:
                for field in main_fields:
                    if field["id"] in used_ids:
                        continue
                    label_lower = field["label"].lower()
                    fname_lower = field["fieldname"].lower()
                    if keyword in label_lower or keyword in fname_lower:
                        matched.append(field)
                        used_ids.add(field["id"])
                        break

            if matched:
                reordered.extend(matched)
                groups_info.append({"name": name, "count": len(matched)})

        # 未匹配的字段追加到最后
        remaining = [f for f in main_fields if f["id"] not in used_ids]
        if remaining:
            reordered.extend(remaining)
            if groups_info:
                groups_info[-1]["count"] += len(remaining)
            else:
                groups_info.append({"name": "其他", "count": len(remaining)})

        return reordered, groups_info if groups_info else None

    # ============================================================
    #  自动按业务类型分组
    # ============================================================

    # 业务关键词映射：关键词 → 组名
    # 优先级：越靠前的组优先匹配
    BUSINESS_GROUPS = {
        # 人员信息
        "人员信息": ["姓名", "身份证", "电话", "联系人", "户口", "住址", "家庭住址",
                     "性别", "民族", "籍贯", "学历", "政治", "婚姻", "职业",
                     "人员", "员工", "头像", "照片", "邮箱"],
        # 费用信息（优先于住宿信息，因为"结算"等词容易混淆）
        "费用信息": ["金额", "费用", "结算", "计费", "承担", "缴费", "支付", "付款",
                     "收款", "押金", "租金", "房租", "工资", "补贴", "报销", "发票",
                     "财务", "预算", "成本", "收费", "钱", "水电费"],
        # 住宿信息
        "住宿信息": ["房间", "入住", "退宿", "退房", "宿舍", "水电", "燃气", "钥匙",
                     "门禁", "床", "楼层", "床位", "水表", "电表", "燃气表",
                     "热水", "冷水", "电表示数", "初始", "是否有"],
        # 日期时间
        "日期时间": ["日期", "时间", "开始", "结束", "有效期", "到期", "截止",
                     "创建", "更新", "修改", "生效"],
        # 审批状态
        "审批状态": ["审批", "审核", "状态", "流程", "意见", "备注", "原因", "说明",
                     "是否", "选择", "确认", "批准", "同意", "拒绝", "保险"],
        # 附件文件
        "附件信息": ["附件", "文件", "文档", "图片", "照片", "证明", "材料", "合同",
                     "协议", "报告"],
    }

    def _auto_group_by_business(self, main_fields: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        根据字段名称语义自动按业务类型分组，最多 4 组。
        返回 (reordered_fields, groups_info)
        """
        groups_info = []
        reordered = []
        used_ids = set()

        for group_name, keywords in self.BUSINESS_GROUPS.items():
            matched = []
            for field in main_fields:
                if field["id"] in used_ids:
                    continue
                label_lower = field["label"].lower()
                fname_lower = field["fieldname"].lower()
                for kw in keywords:
                    if kw.lower() in label_lower or kw.lower() in fname_lower:
                        matched.append(field)
                        used_ids.add(field["id"])
                        break
            if matched:
                reordered.extend(matched)
                groups_info.append({"name": group_name, "count": len(matched)})

        # 未匹配的字段归入"其他信息"
        remaining = [f for f in main_fields if f["id"] not in used_ids]

        # 最多保留 4 组：前 3 个匹配组 + 其他信息（含未匹配 + 第4组以后的所有）
        if len(groups_info) > 3:
            # 前 3 组保留
            kept = groups_info[:3]
            kept_reorder = []
            used_kept = set()
            idx = 0
            for gi in kept:
                for _ in range(gi["count"]):
                    if idx < len(reordered):
                        kept_reorder.append(reordered[idx])
                        used_kept.add(reordered[idx]["id"])
                        idx += 1
            # 剩余所有字段归入"其他信息"
            others = [f for f in main_fields if f["id"] not in used_kept]
            kept_reorder.extend(others)
            kept.append({"name": "其他信息", "count": len(others)})
            return kept_reorder, kept

        if remaining:
            reordered.extend(remaining)
            groups_info.append({"name": "其他信息", "count": len(remaining)})

        return reordered, groups_info

    # ============================================================
    #  布局计算
    # ============================================================

    def _compute_layout(self, main_fields: List[Dict], detail_fields: List[Dict],
                        groups_info: Optional[List[Dict]] = None) -> Dict:
        """
        计算布局行分配。
        返回 layout_plan 包含 rows, field_rows, group_rows, last_field_row, detail_entry_row 等
        """
        main_count = len(main_fields)
        has_detail = len(detail_fields) > 0

        # 按分组组织字段
        if groups_info and main_count > 0:
            groups_plan = []
            field_idx = 0
            for gi in groups_info:
                gc = gi["count"]
                if field_idx < main_count:
                    groups_plan.append((gi["name"], main_fields[field_idx:field_idx + gc]))
                    field_idx += gc
            # 剩余字段归入最后一组
            if field_idx < main_count:
                groups_plan[-1] = (groups_plan[-1][0], groups_plan[-1][1] + main_fields[field_idx:])
        else:
            groups_plan = [(None, main_fields)]

        # 计算行位置
        rows = []
        field_rows = []
        group_rows = []
        current_row = 3  # row_0/1/2 是固定的

        for gi, (gname, gfields) in enumerate(groups_plan):
            if gname:
                rows.append(("group", current_row, gname))
                group_rows.append((current_row, gname))
                current_row += 1
                if gfields:
                    rows.append(("separator", current_row, None))
                    current_row += 1

            # 字段配对：普通字段两两一行，textarea(2) 和附件(6) 独占一行
            pair_buffer = []  # 缓冲普通字段，凑一对
            for i, f in enumerate(gfields):
                is_full = f.get("fieldhtmltype") in ("2", "6")

                # 先处理缓冲区中的配对
                if is_full and pair_buffer:
                    # 缓冲区有未配对字段，先flush
                    pending = pair_buffer.pop(0)
                    rows.append(("separator", current_row, None))
                    current_row += 1
                    rows.append(("field", current_row, (pending, None)))
                    field_rows.append((current_row, pending, None, False))
                    current_row += 1

                if is_full:
                    rows.append(("field_full", current_row, f))
                    field_rows.append((current_row, f, None, True))
                    current_row += 1
                else:
                    pair_buffer.append(f)
                    if len(pair_buffer) == 2:
                        f1, f2 = pair_buffer.pop(0), pair_buffer.pop(0)
                        rows.append(("separator", current_row, None))
                        current_row += 1
                        rows.append(("field", current_row, (f1, f2)))
                        field_rows.append((current_row, f1, f2, False))
                        current_row += 1

            # 处理剩余未配对的普通字段
            for f in pair_buffer:
                rows.append(("separator", current_row, None))
                current_row += 1
                rows.append(("field", current_row, (f, None)))
                field_rows.append((current_row, f, None, False))
                current_row += 1

            # 组间分隔
            if gname and gi < len(groups_plan) - 1:
                rows.append(("separator", current_row, None))
                current_row += 1

        detail_entry_row = None
        if has_detail:
            # 明细表前加一行 height=10 的空行分割
            rows.append(("separator", current_row, None))
            current_row += 1
            detail_entry_row = current_row
            rows.append(("detail", detail_entry_row, None))
            current_row += 1

        last_field_row = field_rows[-1][0] if field_rows else 3
        total_rows = current_row + 1  # +1 结尾空行

        return {
            "rows": rows,
            "field_rows": field_rows,
            "group_rows": group_rows,
            "last_field_row": last_field_row,
            "detail_entry_row": detail_entry_row,
            "total_rows": total_rows,
            "main_count": main_count,
            "has_detail": has_detail,
        }

    # ============================================================
    #  datajson 生成
    # ============================================================

    def _build_datajson(self, form_info: Dict, main_fields: List[Dict],
                        detail_fields: List[Dict], layout: Dict) -> Dict:
        """生成完整的 datajson"""
        has_detail = layout["has_detail"]
        last_field_row = layout["last_field_row"]
        detail_entry_row = layout["detail_entry_row"]

        # rowheads
        rowheads = {"row_0": "30", "row_1": "30", "row_2": "10"}
        for row_type, row_idx, data in layout["rows"]:
            if row_type in ("group", "field", "field_full", "detail"):
                rowheads["row_%d" % row_idx] = "30"
            elif row_type == "separator":
                rowheads["row_%d" % row_idx] = "10"

        # colheads
        colheads = {
            "col_0": "6%", "col_1": "6%", "col_2": "10%", "col_3": "16%",
            "col_4": "6%", "col_5": "10%", "col_6": "16%", "col_7": "6%", "col_8": "5%"
        }

        ec = []
        border_bottom = [{"kind": "bottom", "style": "1", "color": "#90badd"}]
        border_full = [
            {"kind": "top", "style": "1", "color": "#90badd"},
            {"kind": "left", "style": "1", "color": "#90badd"},
            {"kind": "right", "style": "1", "color": "#90badd"},
            {"kind": "bottom", "style": "1", "color": "#90badd"}
        ]
        border_group = [{"kind": "bottom", "style": "5", "color": "#0070c0"}]

        # 主标题 row_1
        ec.append({
            "id": "1,0", "colspan": "9", "rowspan": "1", "etype": "1",
            "font": {"bold": "true", "font-size": "14pt", "font-family": "Microsoft YaHei",
                     "color": "#0070c0", "text-align": "center", "valign": "middle"},
            "eborder": [], "evalue": form_info["formname"]
        })

        # 按 layout['rows'] 顺序构建：分组标题 → 字段行 → 明细表入口
        # 预构建字段行 ec 映射（row_idx -> ec_elements）
        field_ec_map = {}
        for row_data in layout["field_rows"]:
            row_idx, f1, f2 = row_data[0], row_data[1], row_data[2]
            is_full = row_data[3] if len(row_data) > 3 else False
            elements = []

            if is_full:
                # 多行文本框独占一行：标签 col 2，值 col 3-6（colspan=4）
                elements.append({
                    "id": "%d,2" % row_idx, "colspan": "1", "rowspan": "1", "etype": "2",
                    "field": str(f1["id"]), "font": {"valign": "middle"},
                    "eborder": [], "evalue": f1["label"]
                })
                elements.append({
                    "id": "%d,3" % row_idx, "colspan": "4", "rowspan": "1", "etype": "3",
                    "field": str(f1["id"]), "fieldtype": f1["type"],
                    "font": {"font-size": "9pt", "font-family": "Microsoft YaHei",
                             "color": "#000", "valign": "middle"},
                    "eborder": border_bottom, "evalue": f1["label"]
                })
            elif not f2:
                # 落单的普通字段（非 textarea），正常显示
                elements.append({
                    "id": "%d,2" % row_idx, "colspan": "1", "rowspan": "1", "etype": "2",
                    "field": str(f1["id"]), "font": {"valign": "middle"},
                    "eborder": [], "evalue": f1["label"]
                })
                elements.append({
                    "id": "%d,3" % row_idx, "colspan": "1", "rowspan": "1", "etype": "3",
                    "field": str(f1["id"]), "fieldtype": f1["type"],
                    "font": {"font-size": "9pt", "font-family": "Microsoft YaHei",
                             "color": "#000", "valign": "middle"},
                    "eborder": border_bottom, "evalue": f1["label"]
                })
            else:
                for col, f in [(2, f1), (3, f1), (5, f2), (6, f2)]:
                    is_label = (col == 2 or col == 5)
                    el = {
                        "id": "%d,%d" % (row_idx, col), "colspan": "1", "rowspan": "1",
                        "etype": "2" if is_label else "3",
                        "field": str(f["id"]),
                        "font": {"valign": "middle"} if is_label else
                            {"font-size": "9pt", "font-family": "Microsoft YaHei",
                             "color": "#000", "valign": "middle"},
                        "eborder": [] if is_label else border_bottom,
                        "evalue": f["label"]
                    }
                    if not is_label:
                        el["fieldtype"] = f["type"]
                    elements.append(el)
            field_ec_map[row_idx] = elements

        # 预构建分组标题 ec 映射
        group_ec_map = {}
        for row_idx, gname in layout["group_rows"]:
            group_ec_map[row_idx] = {
                "id": "%d,1" % row_idx, "colspan": "7", "rowspan": "1", "etype": "1",
                "font": {"bold": "true", "font-size": "11pt", "font-family": "Microsoft YaHei",
                         "color": "#0070c0", "valign": "middle"},
                "eborder": border_group, "evalue": gname
            }

        # 按 rows 顺序添加到 ec
        for row_type, row_idx, data in layout["rows"]:
            if row_type == "group" and row_idx in group_ec_map:
                ec.append(group_ec_map[row_idx])
            elif row_type in ("field", "field_full") and row_idx in field_ec_map:
                ec.extend(field_ec_map[row_idx])

        # 明细表入口
        if has_detail and detail_entry_row is not None:
            ec.append({
                "id": "%d,2" % detail_entry_row, "colspan": "5", "rowspan": "1", "etype": "7",
                "detail": "detail_1",
                "font": {"color": "black", "valign": "middle"},
                "etxtindent": "0.5",
                "backgroundColor": "#e7f3fc",
                "eborder": border_full,
                "evalue": "明细表1"
            })

        # 主表
        emaintable = {"rowheads": rowheads, "colheads": colheads, "ec": ec}

        # 结果
        result = {
            "eformdesign": {
                "eattr": {
                    "formname": form_info["formname"],
                    "modeid": str(form_info["modeid"]) if form_info["modeid"] else "",
                    "formid": str(form_info["form_id"]),
                    "isbill": "1"
                },
                "etables": {}
            },
            "formula": {}
        }

        # 明细表
        if has_detail:
            detail_count = len(detail_fields)
            detail_col_count = detail_count + 2  # 全选 + 序号 + 字段

            d_colheads = {"col_0": "50", "col_1": "50"}
            d_colattrs = {"col_0": {"hide": "y"}}
            for i in range(detail_count):
                d_colheads["col_%d" % (i + 2)] = "150"

            d_rowheads = {"row_0": "30", "row_1": "30", "row_2": "30", "row_3": "30", "row_4": "30"}

            d_ec = []
            d_border_full = [
                {"kind": "top", "style": "1", "color": "#90badd"},
                {"kind": "left", "style": "1", "color": "#90badd"},
                {"kind": "right", "style": "1", "color": "#90badd"},
                {"kind": "bottom", "style": "1", "color": "#90badd"}
            ]
            d_border_tb = [
                {"kind": "top", "style": "1", "color": "#90badd"},
                {"kind": "bottom", "style": "1", "color": "#90badd"}
            ]

            def d_cell(row, col, etype, colspan="1", rowspan="1"):
                return {"id": "%d,%d" % (row, col), "colspan": colspan, "rowspan": rowspan, "etype": str(etype)}

            # row_0: 空白 + 新增行按钮
            c0 = d_cell(0, 0, 0)
            c0["font"] = {"valign": "top"}
            c0["eborder"] = d_border_tb
            c0["evalue"] = ""
            d_ec.append(c0)

            btn = d_cell(0, detail_col_count - 1, 10)
            btn["font"] = {"valign": "top"}
            btn["eborder"] = d_border_tb
            btn["evalue"] = ""
            d_ec.append(btn)

            # row_1: 表头
            c = d_cell(1, 0, 20)
            c["font"] = {"color": "black", "text-align": "center", "valign": "middle"}
            c["backgroundColor"] = "#e7f3fc"
            c["eborder"] = d_border_full
            c["evalue"] = "全选"
            d_ec.append(c)

            c = d_cell(1, 1, 1)
            c["font"] = {"color": "black", "text-align": "center", "valign": "middle"}
            c["backgroundColor"] = "#e7f3fc"
            c["eborder"] = d_border_full
            c["evalue"] = "序号"
            d_ec.append(c)

            for i, f in enumerate(detail_fields):
                c = d_cell(1, i + 2, 2)
                c["field"] = str(f["id"])
                c["font"] = {"color": "black", "text-align": "center", "valign": "middle"}
                c["backgroundColor"] = "#e7f3fc"
                c["eborder"] = d_border_full
                c["evalue"] = f["label"]
                d_ec.append(c)

            # row_2: 表头标识
            c = d_cell(2, 0, 8, colspan=str(detail_col_count))
            c["font"] = {"color": "black", "valign": "middle"}
            c["backgroundColor"] = "#eeeeee"
            c["eborder"] = []
            c["evalue"] = "表头标识"
            d_ec.append(c)

            # row_3: 数据行
            c = d_cell(3, 0, 21)
            c["font"] = {"color": "black", "text-align": "center", "valign": "middle"}
            c["eborder"] = d_border_full
            c["evalue"] = "选中"
            d_ec.append(c)

            c = d_cell(3, 1, 22)
            c["font"] = {"color": "black", "text-align": "center", "valign": "middle"}
            c["eborder"] = d_border_full
            c["evalue"] = "序号"
            d_ec.append(c)

            for i, f in enumerate(detail_fields):
                c = d_cell(3, i + 2, 3)
                c["field"] = str(f["id"])
                c["fieldtype"] = f["type"]
                c["font"] = {"font-size": "9pt", "font-family": "Microsoft YaHei",
                             "color": "black", "text-align": "center", "valign": "middle"}
                c["eborder"] = d_border_full
                c["evalue"] = f["label"]
                d_ec.append(c)

            # row_4: 表尾标识
            c = d_cell(4, 0, 9, colspan=str(detail_col_count))
            c["font"] = {"color": "black", "valign": "middle"}
            c["backgroundColor"] = "#eeeeee"
            c["eborder"] = []
            c["evalue"] = "表尾标识"
            d_ec.append(c)

            result["eformdesign"]["etables"]["detail_1"] = {
                "rowheads": d_rowheads,
                "colheads": d_colheads,
                "colattrs": d_colattrs,
                "ec": d_ec,
                "edtitleinrow": "2",
                "edtailinrow": "4",
                "edlockedcol": "-1",
                "seniorset": "1"
            }

        result["eformdesign"]["etables"]["emaintable"] = emaintable
        return result

    # ============================================================
    #  pluginjson 生成
    # ============================================================

    def _build_pluginjson(self, form_info: Dict, main_fields: List[Dict],
                          detail_fields: List[Dict], layout: Dict) -> Dict:
        """生成完整的 pluginjson"""
        has_detail = layout["has_detail"]
        detail_entry_row = layout["detail_entry_row"]

        result = {}

        # ---------- 明细表 sheet ----------
        if has_detail:
            detail_count = len(detail_fields)
            detail_col_count = detail_count + 2

            d_columns = [{"size": 50, "dirty": True}, {"size": 50, "dirty": True}]
            for _ in range(detail_count):
                d_columns.append({"size": 150, "dirty": True})

            d_spans = [
                {"row": 2, "rowCount": 1, "col": 0, "colCount": detail_col_count},
                {"row": 4, "rowCount": 1, "col": 0, "colCount": detail_col_count},
            ]

            d_data = {}

            # row_0
            row0 = {}
            row0["0"] = {"style": {"borderTop": {"color": "#90badd", "style": 1},
                                   "borderBottom": {"color": "#90badd", "style": 1}}}
            for c in range(1, detail_col_count - 1):
                row0[str(c)] = {"style": {"borderBottom": {"color": "#90badd", "style": 1}}}
            row0[str(detail_col_count - 1)] = {
                "style": {"backgroundImage": "/formmode/exceldesign/image/shortBtn/detail/de_btn_wev8.png",
                          "backgroundImageLayout": 3,
                          "borderTop": {"color": "#90badd", "style": 1},
                          "borderBottom": {"color": "#90badd", "style": 1}}}
            d_data["0"] = row0

            # row_1: 表头
            row1 = {}
            row1["0"] = {"value": "全选", "style": {
                "backgroundImage": "/formmode/exceldesign/image/shortBtn/detail/de_checkall_wev8.png",
                "backgroundImageLayout": 3, "backColor": "#e7f3fc",
                "borderTop": {"color": "#90badd", "style": 1},
                "borderBottom": {"color": "#90badd", "style": 1},
                "borderLeft": {"color": "#90badd", "style": 1},
                "borderRight": {"color": "#90badd", "style": 1},
                "hAlign": 1, "vAlign": 1, "foreColor": "black"}}
            row1["1"] = {"value": "序号", "style": {
                "backColor": "#e7f3fc",
                "borderTop": {"color": "#90badd", "style": 1},
                "borderBottom": {"color": "#90badd", "style": 1},
                "borderLeft": {"color": "#90badd", "style": 1},
                "borderRight": {"color": "#90badd", "style": 1},
                "hAlign": 1, "vAlign": 1, "foreColor": "black"}}
            for i, f in enumerate(detail_fields):
                row1[str(i + 2)] = {"value": f["label"], "style": {
                    "backColor": "#e7f3fc",
                    "borderTop": {"color": "#90badd", "style": 1},
                    "borderBottom": {"color": "#90badd", "style": 1},
                    "borderLeft": {"color": "#90badd", "style": 1},
                    "borderRight": {"color": "#90badd", "style": 1},
                    "hAlign": 1, "vAlign": 1, "foreColor": "black"}}
            d_data["1"] = row1

            # row_2: 表头标识
            row2 = {"0": {"value": "表头标识", "style": {"backColor": "#eeeeee", "foreColor": "black", "hAlign": 0, "vAlign": 1}}}
            for c in range(1, detail_col_count):
                row2[str(c)] = {}
            d_data["2"] = row2

            # row_3: 数据行
            row3 = {}
            row3["0"] = {"value": "选中", "style": {
                "backgroundImage": "/formmode/exceldesign/image/shortBtn/detail/de_checksingle_wev8.png",
                "backgroundImageLayout": 3,
                "borderTop": {"color": "#90badd", "style": 1},
                "borderBottom": {"color": "#90badd", "style": 1},
                "borderLeft": {"color": "#90badd", "style": 1},
                "borderRight": {"color": "#90badd", "style": 1},
                "hAlign": 1, "vAlign": 1, "foreColor": "black"}}
            row3["1"] = {"value": "序号", "style": {
                "backgroundImage": "/formmode/exceldesign/image/shortBtn/detail/de_serialnum_wev8.png",
                "backgroundImageLayout": 3,
                "borderTop": {"color": "#90badd", "style": 1},
                "borderBottom": {"color": "#90badd", "style": 1},
                "borderLeft": {"color": "#90badd", "style": 1},
                "borderRight": {"color": "#90badd", "style": 1},
                "hAlign": 1, "vAlign": 1, "foreColor": "black"}}
            for i, f in enumerate(detail_fields):
                is_req = bool(f.get("is_required", 0))
                bg = self._get_bg_image(f["type"], is_req)
                row3[str(i + 2)] = {"value": f["label"], "style": {
                    "backgroundImage": bg, "backgroundImageLayout": 3,
                    "backColor": "", "font": "9pt Microsoft YaHei",
                    "borderTop": {"color": "#90badd", "style": 1},
                    "borderBottom": {"color": "#90badd", "style": 1},
                    "borderLeft": {"color": "#90badd", "style": 1},
                    "borderRight": {"color": "#90badd", "style": 1},
                    "textIndent": 0, "wordWrap": True, "textDecoration": 0,
                    "foreColor": "black", "hAlign": 1, "vAlign": 1}}
            d_data["3"] = row3

            # row_4: 表尾标识
            row4 = {"0": {"value": "表尾标识", "style": {"backColor": "#eeeeee", "foreColor": "black", "hAlign": 0, "vAlign": 1}}}
            for c in range(1, detail_col_count):
                row4[str(c)] = {}
            d_data["4"] = row4

            result["detail_1_sheet"] = {
                "version": "2.0",
                "tabStripVisible": False,
                "canUserEditFormula": False,
                "allowUndo": False,
                "allowDragDrop": False,
                "allowDragFill": False,
                "backgroundImageLayout": 3,
                "grayAreaBackColor": "white",
                "sheets": {
                    "Sheet1": {
                        "name": "Sheet1",
                        "selections": {"0": {"row": 3, "rowCount": 1, "col": 2, "colCount": 1}},
                        "defaults": {"rowHeight": 30, "colWidth": 62, "rowHeaderColWidth": 40, "colHeaderRowHeight": 20},
                        "columns": d_columns,
                        "rowCount": 5,
                        "columnCount": detail_col_count,
                        "spans": d_spans,
                        "activeRow": 3,
                        "activeCol": 2,
                        "gridline": {"color": "#D0D7E5", "showVerticalGridline": True, "showHorizontalGridline": True},
                        "allowDragDrop": False,
                        "allowDragFill": False,
                        "rowHeaderData": {"rowCount": 5, "defaultDataNode": {"style": {"foreColor": "black"}}},
                        "colHeaderData": {"colCount": detail_col_count, "defaultDataNode": {"style": {"foreColor": "black"}}},
                        "data": {"rowCount": 5, "colCount": detail_col_count, "dataTable": d_data,
                                 "defaultDataNode": {"style": {"foreColor": "black"}}},
                        "rowRangeGroup": {"itemsCount": 5},
                        "colRangeGroup": {"itemsCount": detail_col_count}
                    }
                }
            }

        # ---------- 主表 sheet ----------
        # 构建 columns
        m_columns = [
            {"size": 76, "dirty": True}, {"size": 91, "dirty": True},
            {"size": 135, "dirty": True}, {"size": 198, "dirty": True},
            {"size": 114, "dirty": True}, {"size": 170, "dirty": True},
            {"size": 228, "dirty": True}, {"size": 108, "dirty": True},
            {"size": 100, "dirty": True}
        ]

        # 构建 rows
        m_rows = [
            {"size": "30", "dirty": True},  # row_0
            {"size": "30", "dirty": True},  # row_1
            {"size": "10", "dirty": True},  # row_2
        ]
        for row_type, row_idx, data in layout["rows"]:
            if row_type in ("group", "field", "field_full"):
                m_rows.append(None)  # 默认 30px
            elif row_type == "separator":
                m_rows.append({"size": "10", "dirty": True})
            elif row_type == "detail":
                m_rows.append({"size": 30, "dirty": True, "visible": True})
        m_rows.append({"size": "10", "dirty": True})  # 末尾分隔行

        # spans
        m_spans = [
            {"row": 1, "rowCount": 1, "col": 0, "colCount": 9},  # 主标题
        ]
        for row_idx, gname in layout["group_rows"]:
            m_spans.append({"row": row_idx, "rowCount": 1, "col": 1, "colCount": 7})
        # textarea 字段独占一行，值区域需要 colspan=4 span
        for row_data in layout["field_rows"]:
            is_full = row_data[3] if len(row_data) > 3 else False
            if is_full:
                row_idx = row_data[0]
                m_spans.append({"row": row_idx, "rowCount": 1, "col": 3, "colCount": 4})
        if has_detail and detail_entry_row is not None:
            m_spans.append({"row": detail_entry_row, "rowCount": 1, "col": 2, "colCount": 5})

        # 构建 dataTable
        m_data = {}

        # row_1: 主标题
        row1 = {"0": {"value": form_info["formname"], "style": {
            "font": "bold 14pt Microsoft YaHei", "formatter": "General",
            "wordWrap": True, "textDecoration": 0, "foreColor": "#0070c0",
            "hAlign": 1, "vAlign": 1}}}
        for c in range(1, 9):
            row1[str(c)] = {}
        m_data["1"] = row1

        # 分组标题行
        for row_idx, gname in layout["group_rows"]:
            rd = {}
            rd["1"] = {"value": gname, "style": {
                "font": "bold 11pt Microsoft YaHei", "formatter": "General",
                "borderBottom": {"color": "#0070c0", "style": 5},
                "wordWrap": True, "textDecoration": 0, "foreColor": "#0070c0",
                "hAlign": 0, "vAlign": 1}}
            for c in range(2, 8):
                rd[str(c)] = {"style": {"borderBottom": {"color": "#0070c0", "style": 5}}}
            m_data[str(row_idx)] = rd

        # 字段行
        for row_data in layout["field_rows"]:
            row_idx, f1, f2 = row_data[0], row_data[1], row_data[2]
            is_full = row_data[3] if len(row_data) > 3 else False
            rd = {}
            if is_full:
                # 多行文本框独占一行：标签 col 2，值 col 3-6（colspan=4）
                is_req = bool(f1.get("is_required", 0))
                bg = self._get_bg_image(f1["type"], is_req)
                rd["2"] = {"value": f1["label"], "style": {"vAlign": 1}}
                cell_style = {
                    "backgroundImage": bg, "backgroundImageLayout": 3,
                    "backColor": "", "font": "9pt Microsoft YaHei",
                    "borderBottom": {"color": "#90badd", "style": 1},
                    "textIndent": 2.5, "wordWrap": True, "textDecoration": 0,
                    "foreColor": "black", "hAlign": 0, "vAlign": 1}
                rd["3"] = {"value": f1["label"], "style": cell_style, "colSpan": 4}
                # 合并跨越的单元格也要带样式，否则边框不连贯
                for ck in ["4", "5", "6"]:
                    rd[ck] = {"style": cell_style}
            elif not f2:
                # 落单的普通字段（非 textarea），正常显示
                is_req = bool(f1.get("is_required", 0))
                bg = self._get_bg_image(f1["type"], is_req)
                rd["2"] = {"value": f1["label"], "style": {"vAlign": 1}}
                rd["3"] = {"value": f1["label"], "style": {
                    "backgroundImage": bg, "backgroundImageLayout": 3,
                    "backColor": "", "font": "9pt Microsoft YaHei",
                    "borderBottom": {"color": "#90badd", "style": 1},
                    "textIndent": 2.5, "wordWrap": True, "textDecoration": 0,
                    "foreColor": "black", "hAlign": 0, "vAlign": 1}}
            else:
                for col, f in [(2, f1), (3, f1), (5, f2), (6, f2)]:
                    is_label = (col == 2 or col == 5)
                    if is_label:
                        rd[str(col)] = {"value": f["label"], "style": {"vAlign": 1}}
                    else:
                        is_req = bool(f.get("is_required", 0))
                        bg = self._get_bg_image(f["type"], is_req)
                        rd[str(col)] = {"value": f["label"], "style": {
                            "backgroundImage": bg, "backgroundImageLayout": 3,
                            "backColor": "", "font": "9pt Microsoft YaHei",
                            "borderBottom": {"color": "#90badd", "style": 1},
                            "textIndent": 2.5, "wordWrap": True, "textDecoration": 0,
                            "foreColor": "black", "hAlign": 0, "vAlign": 1}}
            m_data[str(row_idx)] = rd

        # 明细表入口
        if has_detail and detail_entry_row is not None:
            rd = {}
            rd["2"] = {"value": "明细表1", "style": {
                "backgroundImage": "/formmode/exceldesign/image/shortBtn/detail/detailTable_wev8.png",
                "backgroundImageLayout": 3, "backColor": "#e7f3fc",
                "borderLeft": {"color": "#90badd", "style": 1},
                "borderTop": {"color": "#90badd", "style": 1},
                "borderRight": {"color": "#90badd", "style": 1},
                "borderBottom": {"color": "#90badd", "style": 1},
                "textIndent": 3, "foreColor": "black", "vAlign": 1}}
            for c in range(3, 7):
                rd[str(c)] = {"style": {
                    "borderTop": {"color": "#90badd", "style": 1},
                    "borderBottom": {"color": "#90badd", "style": 1}}}
            rd["6"] = {"style": {
                "borderTop": {"color": "#90badd", "style": 1},
                "borderRight": {"color": "#90badd", "style": 1},
                "borderBottom": {"color": "#90badd", "style": 1}}}
            m_data[str(detail_entry_row)] = rd

        total_rows = len(m_rows)

        result["main_sheet"] = {
            "version": "2.0",
            "tabStripVisible": False,
            "canUserEditFormula": False,
            "allowUndo": False,
            "allowDragDrop": False,
            "allowDragFill": False,
            "backgroundImageLayout": 3,
            "grayAreaBackColor": "white",
            "sheets": {
                "Sheet1": {
                    "name": "Sheet1",
                    "selections": {
                        "0": {
                            "row": detail_entry_row if (has_detail and detail_entry_row) else 11,
                            "rowCount": 1, "col": 2, "colCount": 5
                        }
                    },
                    "defaults": {"rowHeight": 30, "colWidth": 62, "rowHeaderColWidth": 40, "colHeaderRowHeight": 20},
                    "columns": m_columns,
                    "rows": m_rows,
                    "rowCount": total_rows,
                    "columnCount": 9,
                    "spans": m_spans,
                    "activeRow": detail_entry_row if (has_detail and detail_entry_row) else 11,
                    "activeCol": 2,
                    "gridline": {"color": "#D0D7E5", "showVerticalGridline": False, "showHorizontalGridline": False},
                    "rowHeaderColInfos": [{"size": 40, "dirty": True}],
                    "allowDragDrop": False,
                    "allowDragFill": False,
                    "rowHeaderData": {
                        "rowCount": total_rows,
                        "dataTable": {},
                        "defaultDataNode": {"style": {"foreColor": "black"}}
                    },
                    "colHeaderData": {
                        "colCount": 9,
                        "dataTable": {
                            "0": {
                                "0": {"value": "A (6%)"}, "1": {"value": "B (6%)"},
                                "2": {"value": "C (10%)"}, "3": {"value": "D (16%)"},
                                "4": {"value": "E (6%)"}, "5": {"value": "F (10%)"},
                                "6": {"value": "G (16%)"}, "7": {"value": "H (6%)"},
                                "8": {"value": "I (5%)"}
                            }
                        },
                        "defaultDataNode": {"style": {"foreColor": "black"}}
                    },
                    "data": {
                        "rowCount": total_rows,
                        "colCount": 9,
                        "dataTable": m_data,
                        "defaultDataNode": {"style": {"foreColor": "black"}}
                    },
                    "rowRangeGroup": {"itemsCount": total_rows},
                    "colRangeGroup": {"itemsCount": 9}
                }
            }
        }

        return result

    # ============================================================
    #  公开方法
    # ============================================================

    @expose(
        description="根据表单 ID 自动生成 datajson 和 pluginjson 布局配置。自动查询表单字段，可选分组配置或自动按业务类型分组。",
        examples=[
            {"form_id": -1003},
            {"form_id": -1003, "auto_group": True},
            {"form_id": -1003, "config": {"groups": [{"name": "基础信息", "fields": ["登记人", "登记日期"]}]}}
        ],
        read_only=True
    )
    def generate_layout_json(
        self,
        form_id: int,
        config: Optional[Dict] = None,
        auto_group: bool = False
    ) -> Dict:
        """
        生成布局 JSON（datajson + pluginjson）

        :param form_id: 表单 ID（必填，负数）。如 -1003
        :param config: 分组配置（选填）。格式：{"groups": [{"name": "组名", "fields": ["字段名1", "字段名2"]}]}
        :param auto_group: 自动按业务类型分组（选填）。开启后忽略 config，根据字段名称语义自动分组
        :return: {"datajson": {...}, "pluginjson": {...}}
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 1. 查询表单信息
            form_info = self._query_form_info(cursor, form_id)

            # 2. 查询字段
            main_fields, detail_fields = self._query_fields(cursor, form_info["form_id"])
            if not main_fields and not detail_fields:
                raise ValueError("表单 %d 没有任何字段" % form_info["form_id"])

            # 3. 分组处理：auto_group > config > 默认
            if auto_group:
                reordered_fields, groups_info = self._auto_group_by_business(main_fields)
            else:
                reordered_fields, groups_info = self._apply_config(main_fields, config)

            # 3.5 分组校验：必须分组，至少 1 组最多 4 组
            if not groups_info:
                raise ValueError("布局必须分组，请提供 config 或开启 auto_group")
            if len(groups_info) > 4:
                raise ValueError("分组数不能超过 4 组，当前 %d 组" % len(groups_info))

            # 4. 计算布局
            layout = self._compute_layout(reordered_fields, detail_fields, groups_info)

            # 5. 生成 JSON
            datajson = self._build_datajson(form_info, reordered_fields, detail_fields, layout)
            pluginjson = self._build_pluginjson(form_info, reordered_fields, detail_fields, layout)

            return {
                "datajson": datajson,
                "pluginjson": pluginjson,
                "form_info": form_info,
                "field_count": {
                    "main": len(reordered_fields),
                    "detail": len(detail_fields)
                },
                "layout_rows": layout["total_rows"]
            }

        finally:
            cursor.close()
            conn.close()

    # ============================================================
    #  数据库插入
    # ============================================================

    def _to_gbk_hex(self, s: str) -> str:
        """将字符串编码为 GBK，生成 CAST(0x... AS VARCHAR(MAX)) SQL"""
        return "CAST(0x%s AS VARCHAR(MAX))" % s.encode("gbk").hex()

    def _insert_single_layout(self, cursor, form_info: Dict, layout_type: int,
                               main_fields: List[Dict], detail_fields: List[Dict],
                               groups_info: Optional[List[Dict]], user_id: int = 2505) -> int:
        """
        插入单个布局（指定 type）
        返回 layout_id
        """
        modeid = form_info["modeid"]
        formid = form_info["form_id"]
        formname = form_info["formname"]

        # 1. 删除旧布局（同 modeid + formid + type）
        cursor.execute("""
            SELECT id FROM modehtmllayout
            WHERE modeid = %s AND formid = %s AND type = %s
        """, (modeid, formid, layout_type))
        old_ids = [int(r[0]) for r in cursor.fetchall()]
        if old_ids:
            # 先删子表，再删主表
            placeholders = ",".join(["%s"] * len(old_ids))
            cursor.execute("DELETE FROM modeformfield WHERE layoutid IN (%s)" % placeholders, tuple(old_ids))
            cursor.execute("DELETE FROM modeformgroup WHERE layoutid IN (%s)" % placeholders, tuple(old_ids))
            cursor.execute("DELETE FROM modehtmllayout WHERE id IN (%s)" % placeholders, tuple(old_ids))

        # 2. 计算布局并生成 JSON
        reordered_fields, _ = self._apply_config(main_fields, None)
        layout = self._compute_layout(reordered_fields, detail_fields, groups_info)
        datajson = self._build_datajson(form_info, reordered_fields, detail_fields, layout)
        pluginjson = self._build_pluginjson(form_info, reordered_fields, detail_fields, layout)

        # 3. 序列化
        datajson_str = json.dumps(datajson, ensure_ascii=False, separators=(",", ":"))
        pluginjson_str = json.dumps(pluginjson, ensure_ascii=False, separators=(",", ":"))

        # 4. 插入 modehtmllayout
        layout_names = {0: "查看布局", 1: "新建布局", 2: "编辑布局"}
        layout_name = "%s-%s" % (formname, layout_names.get(layout_type, "未知"))

        cursor.execute("""
            INSERT INTO modehtmllayout (
                modeid, formid, type, layoutname, syspath, colsperrow, cssfile,
                isdefault, version, operuser, opertime, datajson, pluginjson,
                scripts, scriptstr, stylestr, feaid, isecme, secondPassword,
                dsDesignerid, isquickedit, secondauth, doubleauth, authverifier, cubeuuid
            ) VALUES (
                %s, %s, %s, %s, '', 2, 0, 1, 2, %s, CONVERT(varchar(19), GETDATE(), 120),
                %s, %s, '', '', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NEWID()
            )
        """ % (
            modeid, formid, layout_type,
            self._to_gbk_hex(layout_name),
            user_id,
            self._to_gbk_hex(datajson_str),
            self._to_gbk_hex(pluginjson_str)
        ))

        # 5. 获取新 layoutid
        cursor.execute("""
            SELECT TOP 1 id FROM modehtmllayout
            WHERE modeid = %s AND formid = %s AND type = %s
            ORDER BY id DESC
        """, (modeid, formid, layout_type))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("插入布局失败，未获取到 layout_id")
        layout_id = int(row[0])

        # 6. 插入 modeformfield
        for i, f in enumerate(main_fields):
            isedit = 0 if layout_type == 0 else 1
            cursor.execute("""
                INSERT INTO modeformfield (modeid, type, fieldid, isview, isedit, ismandatory, orderid, layoutid, ishide, isarow)
                VALUES (%s, 1, %s, 1, %s, 0, %s, %s, 0, 0)
            """, (modeid, f["id"], isedit, i + 1, layout_id))

        for i, f in enumerate(detail_fields):
            isedit = 0 if layout_type == 0 else 1
            cursor.execute("""
                INSERT INTO modeformfield (modeid, type, fieldid, isview, isedit, ismandatory, orderid, layoutid, ishide, isarow)
                VALUES (%s, 2, %s, 1, %s, 0, %s, %s, 0, 0)
            """, (modeid, f["id"], isedit, i + 1, layout_id))

        # 7. 插入 modeformgroup（主表权限）
        cursor.execute("""
            INSERT INTO modeformgroup (modeid, formid, type, groupid, isadd, isedit, isdelete, ishidenull, Isneed, isdefault, layoutid, iscopy, isprintserial, allowscroll, isopensapmul, adddefaultrow, isPagination, detailPageSize, mergetype, mergefields)
            VALUES (%s, %s, 0, 0, 1, 1, 1, 0, 0, 0, %s, 1, '', '', 0, 0, '', '', 0, '')
        """, (modeid, formid, layout_id))

        # 8. 明细表权限（如有）
        if detail_fields:
            cursor.execute("""
                INSERT INTO modeformgroup (modeid, formid, type, groupid, isadd, isedit, isdelete, ishidenull, Isneed, isdefault, layoutid, iscopy, isprintserial, allowscroll, isopensapmul, adddefaultrow, isPagination, detailPageSize, mergetype, mergefields)
                VALUES (%s, %s, 1, 0, 1, 1, 1, 0, 0, 0, %s, 1, '', '', 0, 0, '', '', 0, '')
            """, (modeid, formid, layout_id))

        # 9. ASCII 验证
        cursor.execute("""
            SELECT id, layoutname,
                ASCII(SUBSTRING(datajson, 1, 1)) AS data_ascii,
                ASCII(SUBSTRING(pluginjson, 1, 1)) AS plugin_ascii
            FROM modehtmllayout WHERE id = %s
        """, (layout_id,))
        row = cursor.fetchone()
        data_ok = row[2] == 123 if row[2] else False
        plugin_ok = row[3] == 123 if row[3] else False
        ascii_valid = data_ok and plugin_ok

        return {
            "layout_id": layout_id,
            "layout_name": layout_name,
            "type": layout_type,
            "type_name": layout_names.get(layout_type, "未知"),
            "field_count": len(main_fields) + len(detail_fields),
            "ascii_valid": ascii_valid,
            "data_ascii": row[2] if row else None,
            "plugin_ascii": row[3] if row else None
        }

    @expose(
        description="将布局 JSON 插入数据库保存。默认创建三种布局（查看/新建/编辑），支持自动按业务类型分组。",
        examples=[
            {"form_id": -1003},
            {"form_id": -1003, "auto_group": True},
            {"form_id": -1003, "layout_type": 1},
            {"form_id": -1003, "config": {"groups": [{"name": "基础信息", "fields": ["登记人"]}]}}
        ]
    )
    def insert_layout(
        self,
        form_id: int,
        layout_type: Optional[int] = None,
        config: Optional[Dict] = None,
        user_id: int = 2505,
        modeid: Optional[int] = None,
        auto_group: bool = False
    ) -> Dict:
        """
        插入布局到数据库保存

        :param form_id: 表单 ID（必填）。如 -1003
        :param layout_type: 布局类型（选填）。0=查看，1=新建，2=编辑。不传则创建全部三种
        :param config: 分组配置（选填）。格式：{"groups": [{"name": "组名", "fields": ["字段名1"]}]}
        :param user_id: 操作用户 ID（选填，默认 2505）
        :param modeid: 模块 ID（选填）。一个表单关联多个模块时，指定具体模块
        :param auto_group: 自动按业务类型分组（选填）。开启后根据字段名称语义自动分组
        :return: 插入结果，包含 layout_id 和验证信息

        说明：
        - 自动查询表单字段
        - 自动生成 datajson 和 pluginjson
        - 自动插入 modehtmllayout、modeformfield、modeformgroup
        - 自动执行 ASCII 验证
        - 查看布局(type=0)的字段 isedit=0（只读），其他 isedit=1（可编辑）
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 查询表单信息
            form_info = self._query_form_info(cursor, form_id)

            # 覆盖 modeid（一个表单关联多个模块时）
            if modeid is not None:
                form_info["modeid"] = modeid

            # 查询字段
            main_fields, detail_fields = self._query_fields(cursor, form_info["form_id"])
            if not main_fields and not detail_fields:
                raise ValueError("表单 %d 没有任何字段" % form_info["form_id"])

            # 分组处理：auto_group > config > 默认
            if auto_group:
                reordered_fields, groups_info = self._auto_group_by_business(main_fields)
            else:
                reordered_fields, groups_info = self._apply_config(main_fields, config)

            # 确定要创建的布局类型
            if layout_type is not None:
                types_to_create = [layout_type]
            else:
                types_to_create = [0, 1, 2]

            # 逐个插入
            results = []
            for lt in types_to_create:
                result = self._insert_single_layout(
                    cursor, form_info, lt, reordered_fields, detail_fields, groups_info, user_id
                )
                results.append(result)

            conn.commit()

            return {
                "status": "success",
                "form_name": form_info["formname"],
                "modeid": form_info["modeid"],
                "form_id": form_info["form_id"],
                "layouts": results,
                "total_inserted": len(results)
            }

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
