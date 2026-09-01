# {项目名称} - 开发设计文档

> 生成时间：{YYYY-MM-DD}
> 依据：`{项目名}/01-需求文档.md`
> 状态：待确认 / 已确认

---

## 一、需求映射

| 需求编号 | 功能模块 | 对应泛微能力 | 执行方式 | 备注 |
|---------|---------|------------|---------|------|
| F1 | {功能名} | {能力域} | {SDK/MCP/SQL/手动} | {说明} |
| F2 | {功能名} | {能力域} | {SDK/MCP/SQL/手动} | {说明} |

---

## 二、数据模型

> **本节直接引用 `01-数据结构设计.md` 中的表结构**，逻辑类型和类型参数必须与数据结构设计文档完全一致，不得省略、不得自行推断。执行步骤中的 fields 参数必须使用逻辑类型。

### 2.1 表结构

#### uf_xxx — {表中文名}

| 字段名 | 逻辑类型 | 类型参数 | 必填 | 说明 |
|--------|---------|---------|------|------|
| id | - | - | 是 | 主键（系统自动生成，不需要传入 SDK） |
| {field} | {逻辑类型} | {类型参数} | {是/否} | {说明} |

> **逻辑类型约束：**
> - 必须使用 SDK 逻辑类型（text、integer、float、dropdown、textarea、browser、date 等），禁止写物理类型（varchar、int、text 等）
> - 逻辑类型取值参考 `references/field-type-reference.md`
> - 每个字段必须写齐类型参数（text 带 length、dropdown 带 options、browser 带 browser_id/browser_name）
> - 日期字段必须用 date/datetime/time/year，禁止用 text 模拟

### 2.2 表间关联

| 主表 | 关联字段 | 从表 | 关联字段 | 说明 |
|------|---------|------|---------|------|
| uf_xxx | {field} | uf_yyy | {field} | {说明} |

---

## 三、执行步骤

> **关键约束：** 创建表单步骤的 fields 参数必须使用逻辑类型（text/integer/dropdown/textarea/browser/date 等），禁止写物理类型。每个字段 dict 必须包含：name、label、type，并根据类型补充必要参数（db_type、length、browser_id、browser_name、options 等）。逻辑类型和类型参数必须与 2.1 表结构逐字一致。
>
> **自定义浏览框字段处理：**
> - **非环形依赖**（浏览框数据源是其他表单）：执行步骤按依赖顺序排列，先创建数据源表单 → 创建浏览框 → 再创建引用浏览框的表单。字段参数使用 `"type": "browser", "browser_name": "xxx浏览框"`，SDK 通过名称精确匹配。
> - **环形依赖**（浏览框数据源是自身表单）：表单创建时先跳过该浏览框字段 → 创建浏览框 → 调用 `form_add_fields` 补加。跳过和补加步骤必须在执行步骤中明确写出。

### 步骤 1：{步骤名称}

- **对应功能：** F{编号}
- **执行方式：** SDK / MCP / SQL / 手动
- **具体操作：**
  ```
  {SDK tool 调用 + 参数 / SQL 语句 / 手动操作说明}
  ```
- **预期结果：** {操作成功后的状态}
- **验证方式：** {如何确认}

### 步骤 N：创建 {表单名} 表单 (uf_xxx)

- **执行方式：** SDK (`form_create_form`)
- **参数：**
  - form_name: "{表单中文名}"
  - app_id: {步骤1产出}
  - table_name: "uf_xxx"
  - fields:
    ```
    [
      {"name": "field1", "label": "字段标签1", "type": "text", "length": 200},
      {"name": "field2", "label": "字段标签2", "type": "integer"},
      {"name": "field3", "label": "字段标签3", "type": "browser", "browser_id": 1},
      {"name": "field4", "label": "字段标签4", "type": "browser", "browser_name": "项目浏览框"},
      {"name": "field5", "label": "字段标签5", "type": "float", "db_type": "decimal(15,2)"},
      {"name": "field6", "label": "字段标签6", "type": "dropdown", "options": ["选项1", "选项2"]},
      {"name": "field7", "label": "字段标签7", "type": "textarea"},
      {"name": "field8", "label": "字段标签8", "type": "date"},
      {"name": "field9", "label": "字段标签9", "type": "checkbox"}
    ]
    ```
  - **逻辑类型说明（参考 `references/field-type-reference.md`）：**
    - type 必须是 SDK 逻辑类型（text/integer/float/dropdown/textarea/browser/date/checkbox 等），禁止写物理类型
    - 系统浏览框：用 `"browser_id": 数字`（如人员=1，部门=4）
    - 自定义浏览框：用 `"browser_name": "xxx浏览框"`（必须在浏览框创建步骤之后执行）
    - 日期/时间字段：用 `"type": "date"` / `"datetime"` / `"time"` / `"year"`，禁止用 text 模拟
    - 选择框：用 `"type": "dropdown"`，必须带 `"options"` 参数
- **预期结果：** 返回 form_id < 0，物理表 uf_xxx 创建成功
- **验证方式：** 调用 `form_list_form_fields` 确认字段数量和类型与 2.1 表结构一致

---

## 四、前端效果展示

### 4.1 菜单配置

- **菜单位置：** {上级菜单} > {菜单名称}
- **图标：** {图标名称}
- **权限：** {哪些角色可见}

### 4.2 表单布局

> 用文字或 Mermaid 描述字段排列、分组、必填标记

### 4.3 查询页面

- **搜索条件：** {字段列表}
- **列表列：** {字段列表}
- **操作按钮：** {按钮列表}

### 4.4 流程节点（如有）

```mermaid
flowchart LR
    A[提交] -->|条件| B[一级审批]
    B -->|通过| C[二级审批]
    B -->|驳回| A
```

---

## 五、不支持的功能

| 需求编号 | 功能 | 原因 | 替代方案 |
|---------|------|------|---------|
| Fx | {功能名} | 泛微原生不支持 | {建议} |

---

## 六、验收标准覆盖表

> 逐条核对需求文档中的验收标准，确保每条都有对应设计。
> 状态说明：✓ 已覆盖 | ✗ 遗漏（需补充设计）| ⊘ 不支持（需说明原因）

| 需求编号 | 验收标准 | 对应设计点 | 状态 |
|---------|---------|-----------|------|
| F1-1 | {验收标准原文} | {表单/字段/浏览框/联动等} | ✓/✗/⊘ |
| F1-2 | {验收标准原文} | {设计点} | ✓/✗/⊘ |
| ... | ... | ... | ... |

**统计**：
- 总计：{N} 条验收标准
- 已覆盖：{n1} 条
- 遗漏已补充：{n2} 条
- 不支持：{n3} 条
