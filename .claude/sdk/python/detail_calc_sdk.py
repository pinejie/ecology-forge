# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — 明细表计算规则

管理 workflow_formdetailinfo 中的三类计算规则：
- 行规则（rowcalstr）：同行字段间的算术运算（A = B + C）
- 列规则（colcalstr）：指定字段在所有行上求列合计
- 主表合计（maincalstr）：明细表某列的合计值写入主表字段

依赖：pip install pymssql

使用示例：
    from detail_calc_sdk import DetailCalcSDK

    sdk = DetailCalcSDK()

    # 设置规则（field_name 为字段英文名）
    sdk.set_calc_rules(
        form_id=-1196,
        row_rules=[
            {"target": "cs3", "left": "cs1", "op": "+", "right": "cs2"},
        ],
        col_fields=["cs1", "cs2"],
        main_rules=[
            {"main_field": "z1", "detail_field": "cs1"},
        ]
    )

    # 查询当前规则
    rules = sdk.get_calc_rules(-1196)

    # 清除所有规则
    sdk.clear_calc_rules(-1196)
"""

import pymssql
from typing import List, Dict, Optional

from mcp_register import expose
from db_config import load_db_config


# 可参与计算的数字类型：type 值 → 逻辑类型名
_NUMERIC_TYPES = {
    2: "integer",         # 整数
    3: "float",           # 浮点数
    4: "amount",          # 金额转换（中文大写）
    5: "amount-format",   # 金额千分位
}

# 行规则支持的运算符
_VALID_OPS = {"+", "-", "*", "/"}


class DetailCalcSDK:

    def _connect(self):
        cfg = load_db_config()
        return pymssql.connect(
            server=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            database=cfg["database"], charset="utf8"
        )

    def _encode(self, s):
        """Python Unicode → GBK bytes，适配 SQL Server varchar 列写入"""
        if s is None:
            return ""
        return str(s).encode("gbk")

    def _decode(self, val):
        """SQL Server varchar 列读取还原"""
        if val is None:
            return ""
        if isinstance(val, str):
            try:
                return val.encode("latin1").decode("gbk")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return val
        return str(val)

    # ------------------------------------------------------------------
    # 内部：查询字段信息
    # ------------------------------------------------------------------

    def _get_fields(self, cursor, form_id: int):
        """
        查询表单所有字段，按主表/明细表分组返回。

        返回：(main_fields, detail_fields)
            main_fields:    {fieldname: {"id", "fieldname", "label", "type", "fielddbtype"}}
            detail_fields:  {fieldname: {"id", "fieldname", "label", "type", "fielddbtype", "detailtable"}}
        """
        cursor.execute(
            "SELECT f.id, f.fieldname, f.viewtype, f.detailtable, f.type, f.fielddbtype, "
            "  (SELECT TOP 1 h.labelname FROM HtmlLabelInfo h "
            "   WHERE h.indexid = f.fieldlabel AND h.languageid = 7) AS labelname "
            "FROM workflow_billfield f "
            "WHERE f.billid = %s",
            (form_id,)
        )
        main_fields = {}
        detail_fields = {}
        for row in cursor.fetchall():
            info = {
                "id": row[0],
                "fieldname": str(row[1] or ""),
                "viewtype": row[2],
                "detailtable": str(row[3] or ""),
                "type": row[4],
                "fielddbtype": str(row[5] or ""),
                "label": self._decode(row[6]) if row[6] else str(row[1] or ""),
            }
            if info["detailtable"]:
                detail_fields[info["fieldname"]] = info
            else:
                main_fields[info["fieldname"]] = info
        return main_fields, detail_fields

    def _check_numeric(self, fieldname: str, field_info: dict, source_label: str):
        """校验字段是数字类型，否则抛异常。source_label 用于错误提示。"""
        if field_info["type"] not in _NUMERIC_TYPES:
            actual = _NUMERIC_TYPES.get(field_info["type"], f"type={field_info['type']}")
            raise ValueError(
                f"{source_label} 字段 '{fieldname}' 不是数字类型（当前={actual}）。"
                f"可参与计算的类型：integer、float、amount、amount-format"
            )

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    @expose(
        description=(
            "设置明细表计算规则（行规则、列规则、主表合计）。"
            "三个参数均为可选，传 None 表示不修改对应规则，传空列表表示清除该规则。"
            "前提：表单必须有明细表，参与计算的字段必须是数字类型"
            "（integer、float、amount、amount-format）。"
            "行规则运算符支持 +（加）、-（减）、*（乘）、/（除）。"
            "列规则和主表合计固定为求和（SUM），不支持其他运算符。"
        ),
        examples=[
            {
                "name": "账单明细自动计算",
                "form_id": -1196,
                "row_rules": [
                    {"target": "total", "left": "price", "op": "*", "right": "quantity"},
                ],
                "col_fields": ["total"],
                "main_rules": [
                    {"main_field": "bill_total", "detail_field": "total"},
                ],
            },
            {
                "name": "只设行规则，不动其他规则",
                "form_id": -1196,
                "row_rules": [
                    {"target": "c3", "left": "c1", "op": "+", "right": "c2"},
                ],
            },
            {
                "name": "清除所有规则",
                "form_id": -1196,
                "row_rules": [],
                "col_fields": [],
                "main_rules": [],
            },
        ],
        error_hints={
            "不是数字类型": "参与计算的字段必须是 integer/float/amount/amount-format 类型",
            "表单不存在": "请先确认 form_id 是否正确",
            "字段不存在": "field_name 必须是该表单中实际存在的字段英文名",
        }
    )
    def set_calc_rules(
        self,
        form_id: int,
        row_rules: Optional[List[Dict]] = None,
        col_fields: Optional[List[str]] = None,
        main_rules: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        设置明细表计算规则。

        :param form_id:     表单 ID（必填，负数）
        :param row_rules:   行规则列表，None=不修改，[]=清除。
            每条规则：{"target": 目标字段, "left": 左操作数字段, "op": 运算符, "right": 右操作数字段}
            含义：target = left op right，三个字段都必须是明细表数字字段
            op 支持：+（加）、-（减）、*（乘）、/（除）
        :param col_fields:  列规则字段名列表，None=不修改，[]=清除。
            列规则固定对所有行求和（SUM），不支持其他运算符。
            列出的字段在明细表底部显示该列的合计值，字段名必须是明细表数字字段
        :param main_rules:  主表合计规则，None=不修改，[]=清除。
            每条规则：{"main_field": 主表字段, "detail_field": 明细表字段}
            含义：主表字段 = 明细表列合计（SUM），不支持其他运算符。
            两个字段都必须是数字类型
        :return: {"form_id": int, "rowcalstr": str, "colcalstr": str, "maincalstr": str}
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            # 验证表单存在
            cursor.execute("SELECT id FROM workflow_bill WHERE id = %s", (form_id,))
            if not cursor.fetchone():
                raise ValueError(f"表单不存在，form_id={form_id}")

            # 查询字段
            main_fields, detail_fields = self._get_fields(cursor, form_id)

            # 三个都传 None 时，等于什么都没做
            if row_rules is None and col_fields is None and main_rules is None:
                raise ValueError(
                    "至少提供一个规则参数（row_rules / col_fields / main_rules）"
                )

            # ---- 构建 rowcalstr ----
            rowcalstr = None
            if row_rules is not None:
                parts = []
                for rule in row_rules:
                    tgt, left, op, right = rule["target"], rule["left"], rule["op"], rule["right"]
                    for name, src in [(tgt, "target"), (left, "left"), (right, "right")]:
                        if name not in detail_fields:
                            raise ValueError(f"行规则字段 '{name}'（{src}）不是明细表字段或不存在")
                        self._check_numeric(name, detail_fields[name], f"行规则 {src}")
                    if op not in _VALID_OPS:
                        raise ValueError(f"运算符 '{op}' 不合法，支持：+ - * /")
                    parts.append(
                        f"detailfield_{detail_fields[tgt]['id']}="
                        f"detailfield_{detail_fields[left]['id']}"
                        f"{op}"
                        f"detailfield_{detail_fields[right]['id']}"
                    )
                rowcalstr = ";".join(parts)

            # ---- 构建 colcalstr ----
            colcalstr = None
            if col_fields is not None:
                ids = []
                for name in col_fields:
                    if name not in detail_fields:
                        raise ValueError(f"列规则字段 '{name}' 不是明细表字段或不存在")
                    self._check_numeric(name, detail_fields[name], "列规则")
                    ids.append(f"detailfield_{detail_fields[name]['id']}")
                colcalstr = ";".join(ids)

            # ---- 构建 maincalstr ----
            maincalstr = None
            if main_rules is not None:
                parts = []
                for rule in main_rules:
                    mf = rule["main_field"]
                    df = rule["detail_field"]
                    if mf not in main_fields:
                        raise ValueError(f"主表合计字段 '{mf}' 不是主表字段或不存在")
                    self._check_numeric(mf, main_fields[mf], "主表合计 main_field")
                    if df not in detail_fields:
                        raise ValueError(f"主表合计字段 '{df}' 不是明细表字段或不存在")
                    self._check_numeric(df, detail_fields[df], "主表合计 detail_field")
                    parts.append(
                        f"mainfield_{main_fields[mf]['id']}"
                        f"=detailfield_{detail_fields[df]['id']}"
                    )
                maincalstr = ";".join(parts)

            # ---- 写入数据库 ----
            import uuid as uuid_mod
            cursor.execute(
                "SELECT formid FROM workflow_formdetailinfo WHERE formid = %s",
                (form_id,)
            )
            if cursor.fetchone():
                sets = []
                params = []
                if rowcalstr is not None:
                    sets.append("rowcalstr = %s"); params.append(self._encode(rowcalstr))
                if colcalstr is not None:
                    sets.append("colcalstr = %s"); params.append(self._encode(colcalstr))
                if maincalstr is not None:
                    sets.append("maincalstr = %s"); params.append(self._encode(maincalstr))
                if sets:
                    params.append(form_id)
                    cursor.execute(
                        f"UPDATE workflow_formdetailinfo SET {', '.join(sets)} WHERE formid = %s",
                        tuple(params)
                    )
            else:
                cursor.execute(
                    "INSERT INTO workflow_formdetailinfo "
                    "(formid, rowcalstr, colcalstr, maincalstr, uuid) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        form_id,
                        self._encode(rowcalstr or ""),
                        self._encode(colcalstr or ""),
                        self._encode(maincalstr or ""),
                        str(uuid_mod.uuid4()).upper(),
                    )
                )

            conn.commit()
            return {
                "form_id": form_id,
                "rowcalstr": rowcalstr or "",
                "colcalstr": colcalstr or "",
                "maincalstr": maincalstr or "",
            }

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @expose(
        description="查询表单的明细表计算规则（行规则、列规则、主表合计），返回人类可读格式。",
        examples=[{"form_id": -1196}],
        read_only=True,
    )
    def get_calc_rules(self, form_id: int) -> Dict:
        """
        查询表单的明细表计算规则。

        :param form_id: 表单 ID
        :return: {
            "rowcalstr": "原始字符串",
            "colcalstr": "原始字符串",
            "maincalstr": "原始字符串",
            "row_rules":     ["cs3 = cs1 + cs2", ...],
            "col_fields":    ["cs1", "cs2", ...],
            "main_rules":    ["z1 = cs1(列合计)", ...]
        }
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT rowcalstr, colcalstr, maincalstr "
                "FROM workflow_formdetailinfo WHERE formid = %s",
                (form_id,)
            )
            row = cursor.fetchone()
            if not row:
                return {"rowcalstr": "", "colcalstr": "", "maincalstr": "",
                        "row_rules": [], "col_fields": [], "main_rules": []}

            raw_rowcal = self._decode(row[0]) if row[0] else ""
            raw_colcal = self._decode(row[1]) if row[1] else ""
            raw_maincal  = self._decode(row[2]) if row[2] else ""

            # 查询字段 ID → fieldname/label 映射
            cursor.execute(
                "SELECT id, fieldname, detailtable, "
                "  (SELECT TOP 1 h.labelname FROM HtmlLabelInfo h "
                "   WHERE h.indexid = f.fieldlabel AND h.languageid = 7) AS labelname "
                "FROM workflow_billfield f WHERE f.billid = %s",
                (form_id,)
            )
            id_map = {}
            for r in cursor.fetchall():
                fid, fname, dtable, label = r[0], str(r[1]), str(r[2] or ""), r[3]
                display = self._decode(label) if label else fname
                prefix = "detailfield_" if dtable else "mainfield_"
                id_map[f"{prefix}{fid}"] = display

            # 解析 rowcalstr
            row_rules_readable = []
            if raw_rowcal:
                for part in raw_rowcal.split(";"):
                    if "=" not in part:
                        continue
                    left_full, right_full = part.split("=", 1)
                    for op in ("+", "-", "*", "/"):
                        if op in right_full:
                            r1, r2 = right_full.split(op, 1)
                            row_rules_readable.append(
                                f"{id_map.get(left_full, left_full)} = "
                                f"{id_map.get(r1, r1)} {op} {id_map.get(r2, r2)}"
                            )
                            break

            # 解析 colcalstr（raw_colcal 里的值已带 detailfield_ 前缀）
            col_fields_readable = []
            if raw_colcal:
                col_fields_readable = [
                    id_map.get(key, key)
                    for key in raw_colcal.split(";") if key
                ]

            # 解析 maincalstr
            main_rules_readable = []
            if raw_maincal:
                for part in raw_maincal.split(";"):
                    if "=" not in part:
                        continue
                    mf, df = part.split("=", 1)
                    main_rules_readable.append(
                        f"{id_map.get(mf, mf)} = {id_map.get(df, df)}(列合计)"
                    )

            return {
                "rowcalstr": raw_rowcal,
                "colcalstr": raw_colcal,
                "maincalstr": raw_maincal,
                "row_rules": row_rules_readable,
                "col_fields": col_fields_readable,
                "main_rules": main_rules_readable,
            }

        finally:
            conn.close()

    @expose(
        description="清除表单的所有明细表计算规则（从 workflow_formdetailinfo 物理删除记录）。",
        examples=[{"form_id": -1196}],
        destructive=True,
    )
    def clear_calc_rules(self, form_id: int) -> Dict:
        """
        清除表单的所有明细表计算规则。

        :param form_id: 表单 ID
        :return: {"form_id": int, "deleted": bool}
        """
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM workflow_formdetailinfo WHERE formid = %s",
                (form_id,)
            )
            conn.commit()
            return {"form_id": form_id, "deleted": cursor.rowcount > 0}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
