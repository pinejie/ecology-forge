# 泛微字段类型参考

> 设计阶段判断字段类型时，查本文档。物理类型由 SDK 自动转换，设计师不需要关心。

---

## 第一部分：基础逻辑类型（18 种）

> 来源：SDK `form_sdk.py` 的 `type_map`，是唯一权威。传了不在清单里的类型，SDK 直接报错。

| 逻辑类型 | 物理存储 | 适用场景 | 必填参数 | 备注 |
|---------|---------|---------|---------|------|
| text | varchar(N) | 单行短文本（姓名、编码、电话、地址等） | length（默认 100） | 电话建议 length=20，地址建议 length=200 |
| integer | int | 整数（数量、次数、人数等） | - | - |
| float | decimal(38,2) | 浮点数 | - | 需特定精度时用 db_type 覆盖，如 db_type="decimal(15,2)" |
| amount | decimal(15,2) | 金额（带中文大写转换） | - | - |
| amount-format | varchar(30) | 金额千分位显示（2 位小数） | - | - |
| textarea | text | 多行文本（备注、描述、说明、内容等） | - | 可选 html_editor=true 切富文本 |
| browser | int/varchar | 浏览框选择（系统或自定义） | browser_id 或 browser_name | 见第二部分浏览框详解 |
| checkbox | char(1) | 是否勾选（是/否、有无、同意等） | - | 存 0/1 |
| dropdown | int | 下拉选择（固定选项列表） | options（必传） | 选项以整数索引存储 |
| radio | int | 单选按钮 | options（必传） | 选项以整数索引存储 |
| multiselect | text | 多选（固定选项列表） | options（必传） | - |
| file | text | 附件/图片上传 | - | 可选 image=true 切图片模式 |
| date | char(10) | 日期选择器 | - | SDK 自动转 browser(id=2) |
| datetime | varchar(20) | 日期时间选择器 | - | SDK 自动转 browser(id=290) |
| time | char(5) | 时间选择器（HH:mm） | - | SDK 自动转 browser(id=19) |
| year | int | 年份选择器 | - | SDK 自动转 browser(id=178) |
| special | varchar(4000) | 特殊字段 | - | 一般不用 |
| pubchoice | integer | 公共选择 | - | 一般不用 |

> **注意**：date/datetime/time/year 本质是系统浏览框的语法糖，SDK 运行时自动转为对应的 browser 类型。设计阶段直接用逻辑类型即可。

---

## 第二部分：浏览框

### 2.1 系统浏览框（常用清单）

> 完整清单通过 SQL 查询：
> ```sql
> SELECT b.labelname, a.id, a.fielddbtype
> FROM workflow_browserurl a
> LEFT JOIN HtmlLabelInfo b ON a.labelid=b.indexid AND b.languageid=7
> ORDER BY a.id
> ```

| browser_id | 中文名 | 物理类型 | 说明 |
|-----------|--------|---------|------|
| 1 | 人力资源 | int | 人员单选 |
| 2 | 日期 | char(10) | 日期选择器（对应逻辑类型 date） |
| 4 | 部门 | int | 部门单选 |
| 17 | 多人力资源 | text | 人员多选 |
| 19 | 时间 | char(5) | 时间选择器（对应逻辑类型 time） |
| 57 | 多部门 | text | 部门多选 |
| 164 | 分部 | int | 分部单选 |
| 178 | 年份 | int | 年份选择器（对应逻辑类型 year） |
| 194 | 多分部 | text | 分部多选 |
| 290 | 日期时间 | varchar(100) | 日期时间选择器（对应逻辑类型 datetime） |
| 403 | 年月 | varchar(7) | 年月选择器 |

### 2.2 自定义浏览框（项目级）

每个项目按需规划，设计阶段在数据结构设计文档的"浏览框规划"章节定义。

**规则：**
- 设计时除非用户明确要求，否则只用本次开发中规划的自定义浏览框
- 自定义浏览框的物理类型固定为 varchar(1000)，SDK 自动处理
- 自定义浏览框字段在创建表单时需跳过，等浏览框创建后补加

### 2.3 自定义树形浏览框

> 暂不讨论，后续补充。

---

## 业务场景 → 逻辑类型速查

| 业务关键词 | 逻辑类型 | 补充参数 |
|-----------|---------|---------|
| 姓名、编码、编号、标题 | text | length（按实际需要） |
| 电话、手机、传真 | text | length=20 |
| 邮箱 | text | length=100 |
| 地址 | text | length=200 |
| 备注、说明、描述、内容、详情、意见 | textarea | - |
| 数量、个数、次数、天数、人数 | integer | - |
| 金额、价格、单价、总价、预算、成本 | float 或 amount | db_type 可覆盖精度 |
| 是否、有无、同意、完成 | checkbox | - |
| 分类、状态等固定选项 | dropdown | options（必传） |
| 文件、附件、图片上传 | file | - |
| 选人员/负责人/审核人/创建人 | browser | browser_id=1 |
| 选部门 | browser | browser_id=4 |
| 选日期 | date | - |
| 选日期时间 | datetime | - |
| 选时间 | time | - |
| 选年份 | year | - |
| 选自定义数据（菜品、子公司等） | browser | browser_name="xxx浏览框" |
