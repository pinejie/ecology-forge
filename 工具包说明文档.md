# 泛微二次开发工具包说明文档

> 本文档描述工具包的文件组成、各文件功能说明、以及如何在新的 Claude Code 环境中使用。

---

## 一、工具包概述

**工具包用途**：为泛微 OA 二次开发提供完整的 AI 自动化流程，包含 4 阶段流水线（需求分析→方案设计→开发执行→测试验收）、SKILL 技能文件、规则体系、以及 SDK 工具代码。

**适用环境**：Claude Code（需要 MCP Server 支持）+ 泛微 OA 数据库

**核心设计**：AI 负责思考，SDK 负责执行。人工只在需求确认阶段参与，其余阶段全程自动。

---

## 二、文件结构总览

```
泛微二开工具包/
├── CLAUDE.md                          # 项目总入口
├── .claude/
│   ├── rules/
│   │   └── modeling-rules.md          # 建模引擎通用规范
│   ├── skills/
│   │   ├── oa-analyze-requirement/    # ① 需求分析
│   │   ├── oa-generate-design/        # ② 方案设计
│   │   ├── oa-execute-dev/            #  开发执行
│   │   ├── oa-test-verify/            # ④ 测试验收
│   │   └── oa-sdk-create/             # SDK 开发指南
│   └── sdk/
│       ├── db-config.md               # 数据库连接配置（需自行创建，不提交）
│       ├── db-config.example.md       # 数据库配置模板
│       ├── switch-env.sh              # 环境切换脚本（本地使用，不提交）
│       └── python/                    # Python SDK 源码
├── ecology/
│   ├── modeCacheRefresh.jsp           # 刷新建模引擎缓存（SDK 执行完毕后调用）
│   ├── cacheRefresh.jsp               # 刷新 Label 缓存（创建表单后调用）
│   └── clearMenuCache.jsp             # 清除菜单缓存（创建/修改菜单后调用）
└── 本文档
```

---

## 三、文件详细说明

### 3.1 项目总入口

| 文件 | 功能 |
|------|------|
| `CLAUDE.md` | 定义 4 阶段流水线触发时机、操作优先级（SDK→数据库→其它）、建模要素完整性要求、注意事项 |

---

### 3.2 规则文件

| 文件 | 功能 |
|------|------|
| `.claude/rules/modeling-rules.md` | 建模引擎通用规范：执行前阻断检查（浏览框依赖/布局分组/查询排序/快捷搜索/浏览框字段必须输出分析）、依赖排序规则、环形依赖处理策略、建模要素完整性校验 |

---

### 3.3 SKILL 技能文件（4 阶段）

#### ① oa-analyze-requirement — 需求分析

| 文件 | 功能 |
|------|------|
| `SKILL.md` | 核心逻辑：自我理解（拆语义/识别场景/找缺口）→ 对话追问（一次问一个，最多 5-8 轮）→ 出方案草案 → 确认后生成需求文档 |
| `template.md` | 需求文档模板，7 章结构：原始需求 / 功能清单 / 角色与权限 / 业务流程 / 边界用例 / 待定项 / 调研参考 |

**触发词**：`"分析需求"`、`"做个XX系统"`、`"需求拆解"`、`"帮我理一下XX"`、`"我想做个XX"`

**输出**：`{项目名}/01-需求文档.md`

---

#### ② oa-generate-design — 方案设计

| 文件 | 功能 |
|------|------|
| `SKILL.md` | 核心逻辑：场景定位 → 能力推导（逆向推导依赖链）→ 依赖分析+步骤设计 → 填充 SDK 参数 → 标注不支持项 → 生成三份文档（一次出齐，不卡确认） |
| `template-data-structure.md` | 数据结构设计文档模板：表结构/字段清单/浏览框规划/依赖分析/建模要素对照表 |
| `template-dev-design.md` | 开发设计文档模板：需求映射/数据模型/执行步骤（含 SDK 参数）/前端效果展示/不支持功能 |
| `template-test.md` | 测试文档模板：正常流程/异常流程/边界用例/权限测试 |
| `references/capability-map.md` | 能力地图：10 大能力（应用/表单/浏览框/模块/布局/查询/快捷搜索/菜单/字段联动/缓存）+ 依赖链 + 正向执行顺序 + 数据库操作工具 |
| `references/derivation-rules.md` | 逆向推导规则：从终点倒推依赖链（我要做X→X需要Y→Y需要Z），倒推结果反过来就是正向执行顺序 |
| `references/modeling-sdk-reference.md` | SDK 参数参考：每个 tool 的完整参数定义（类型/必填/取值范围）+ 思考点（调用前必须输出的分析内容） |
| `references/scenario-classification.md` | 场景分类：4 大能力域（建模引擎/流程引擎/移动建模/定时任务）的识别规则和关键词匹配 |

**触发词**：`"出方案"`、`"写开发设计"`、`"做技术方案"`、`"第二步"`

**输出**：`{项目名}/01-数据结构设计.md` + `02-开发设计.md` + `03-测试文档.md`

---

#### ③ oa-execute-dev — 开发执行

| 文件 | 功能 |
|------|------|
| `SKILL.md` | 核心逻辑：前置检查 → 逐步执行（一步一验证）→ 失败自排（先自己分析修正）→ 缓存刷新 → 执行记录 |
| `template-execution-record.md` | 执行记录模板：每步记录调了什么/什么参数/返回什么/成功失败/耗时 |
| `references/dirty-data-cleanup.md` | 脏数据清理规则：测试数据隔离标记、清理时机、清理方式 |

**核心原则**：
- 严格按步骤顺序，不能跳步
- 每步做完必验证
- 出错了先自己排，修好了再继续
- 一路执行到底，不卡确认

**触发词**：`"开始执行"`、`"按方案干"`、`"第三步"`、`"照着做"`

**输出**：`{项目名}/04-执行记录.md`

---

#### ④ oa-test-verify — 测试验收

| 文件 | 功能 |
|------|------|
| `SKILL.md` | 核心逻辑：逐条跑用例 → 失败分类处理（工具异常不动手/数据异常自动修正）→ 生成测试报告 |
| `template-test-report.md` | 测试报告模板：每条用例详情（对应需求/测试方式/预期/实际/状态）+ 汇总通过率 |
| `references/dirty-data-cleanup.md` | 脏数据清理规则：测试数据加 `_test` 标记，测完清理 |

**核心原则**：
- 工具异常 → 标注"疑似工具异常"，绝对不改工具代码
- 数据/配置错误 → 自动修正后重跑
- 表层（页面）底层（SQL）都要验

**触发词**：`"测试"`、`"验收"`、`"第五步"`、`"跑测试用例"`

**输出**：`{项目名}/05-测试报告.md`

---

### ⑤ oa-sdk-create — SDK 开发指南

| 文件 | 功能 |
|------|------|
| `SKILL.md` | 在泛微 e-cology OA 系统中创建二次开发 SDK 的完整指南，指导如何将二开能力封装为 Python SDK 或 MCP tool |

**触发词**：`"创建 SDK"`、`"封装二开能力"`、`"建模引擎 SDK"`、`"MCP tool"`、`"新增 SDK"`

---

### 3.4 SDK Python 源码

SDK 位于 `.claude/sdk/python/` 目录，按功能域分为 14 个模块：

#### 建模引擎核心

| 文件 | 功能 | 主要方法 |
|------|------|---------|
| `modeling_sdk.py` | 应用管理 | `create_app`、`list_apps`、`rename_app`、`delete_app`、`move_app` |
| `form_sdk.py` | 表单管理 | `create_form`、`add_fields`、`auto_add_fields`、`list_forms`、`list_form_fields`、`delete_form`、`list_browsers`、`search_browser` |
| `module_sdk.py` | 模块管理 | `create_module`、`list_modules`、`update_module`、`delete_module`、`get_module_detail` |
| `list_sdk.py` | 查询列表 | `create_query`、`list_queries`、`update_query`、`delete_query`、`save_formfields`、`get_formfields` |
| `browser_sdk.py` | 浏览框 | `create_browser`、`list_browsers`、`delete_browser`、`add_browser_button`、`get_form_fields` |
| `layout_sdk.py` | 布局配置 | `generate_layout_json`、`insert_layout` |
| `quicksearch_sdk.py` | 快捷搜索 | `create_quicksearch_setting`、`add_quicksearch_condition`、`list_quicksearch_conditions`、`update_quicksearch_condition`、`delete_quicksearch_condition`、`delete_all_quicksearch_conditions` |
| `menu_sdk.py` | 菜单管理 | `create_menu`、`create_sub_menus`、`get_menu_tree`、`get_menu_detail`、`update_menu`、`delete_menu`、`set_menu_visibility`、`clear_menu_cache` |
| `field_linkage_sdk.py` | 字段联动 | `create_linkage`、`list_linkages`、`delete_linkage`、`toggle_enabled` |
| `cache_sdk.py` | 缓存管理 | `refresh_label_cache` |

#### 基础设施

| 文件 | 功能 |
|------|------|
| `db_config.py` | 数据库连接配置（泛微 OA 数据库地址、账号、密码） |
| `mcp_server.py` | MCP 服务器入口，将 SDK 方法暴露为 MCP 工具 |
| `mcp_register.py` | MCP 工具注册逻辑 |
| `search_sdk.py` | SDK 方法搜索工具，支持按中文描述模糊匹配 SDK 方法 |

---

## 四、使用方法

### 4.1 环境准备

1. **安装 Python 依赖**

SDK 需要 `pymssql` 来连接 SQL Server 数据库：

```bash
pip install pymssql
```

2. **安装数据库 MCP Server**

SDK 通过 MCP Server 与数据库交互，需先安装并启动 `mcp-mssql-server`：

```bash
npm install -g mcp-mssql-server
```

然后在 Claude Code 中配置 MCP Server（或在 `settings.json` 中添加）：

```json
{
  "mcpServers": {
    "mssql-ecology": {
      "command": "mcp-mssql-server",
      "args": ["-c", "server=你的数据库地址;port=11433;user=sa;password=Weaver@2001;database=ecology"]
    }
  }
}
```

> 参数与 `.claude/sdk/db-config.md` 保持一致即可。

3. **配置数据库连接**

复制模板文件并填入实际配置：

```bash
cp .claude/sdk/db-config.example.md .claude/sdk/db-config.md
```

编辑 `.claude/sdk/db-config.md`，填入泛微 OA 数据库信息：

```markdown
# 数据库连接配置

- **host**: 你的数据库地址（如 127.0.0.1 或内网 IP）
- **port**: 1433（SQL Server 默认端口，按实际情况修改）
- **user**: sa
- **password**: 你的密码
- **database**: ecology
```

> `db_config.py` 会自动从 `db-config.md` 读取配置，不需要改代码文件。

4. **确保 Claude Code 可以访问 `.claude/` 目录**

CLAUDE.md 中已配置 SKILL 路径，Claude Code 会自动识别。

---

### 4.2 部署缓存刷新 JSP 文件

三个 JSP 文件供 SDK 调用，用于清除泛微 OA 的内存缓存，使配置变更立即生效。**必须部署后才能正常使用 SDK。**

| 文件 | 功能 | 调用时机 |
|------|------|---------|
| `modeCacheRefresh.jsp` | 刷新建模引擎缓存（ModeComInfo、WorkflowBillComInfo） | SDK 执行完毕后必须调用 |
| `cacheRefresh.jsp` | 刷新 Label 缓存（LabelComInfo） | 创建/修改表单后调用 |
| `clearMenuCache.jsp` | 清除菜单缓存 | 创建/修改菜单后调用 |

**部署方式**：
将三个文件放到泛微 OA 的 `ecology` 根目录下（与 `login.jsp` 同级）。SDK 通过 HTTP GET 请求调用：

```
http://你的 OA 地址/modeCacheRefresh.jsp
http://你的 OA 地址/cacheRefresh.jsp
http://你的 OA 地址/clearMenuCache.jsp
```

---

### 4.3 使用流程

#### 方式一：自然语言触发（推荐）

直接用日常对话触发各阶段，AI 会自动识别并调用对应 SKILL：

```
第1步：你说"我想做个宿舍管理系统"
        → AI 自动触发 oa-analyze-requirement，开始需求分析

第2步：需求确认后你说"出方案"
        → AI 自动触发 oa-generate-design，生成三份文档

第3步：你说"开始执行"
        → AI 自动触发 oa-execute-dev，逐步执行配置

第4步：AI 自动触发 oa-test-verify，完成测试验收
```

#### 方式二：手动调用 SKILL

在 Claude Code 中直接输入斜杠命令：

```
/oa-analyze-requirement
/oa-generate-design
/oa-execute-dev
/oa-test-verify
```

---

### 4.4 项目产出目录结构

执行完成后，项目目录下会生成以下文档：

```
{项目名}/
├── 01-需求文档.md          ← 需求分析产出
├── 01-数据结构设计.md      ← 方案设计产出（表结构+字段+浏览框+依赖）
├── 02-开发设计.md          ← 方案设计产出（执行步骤+SDK参数）
├── 03-测试文档.md          ← 方案设计产出（测试用例）
├── 04-执行记录.md          ← 开发执行产出（每步调用记录）
└── 05-测试报告.md          ← 测试验收产出（通过率+结论）
```

---

### 4.5 操作优先级（重要）

当涉及泛微 OA 二开操作时，**严格按以下顺序**：

1. **先查 SDK**：`search_sdk.py` 按中文描述搜索匹配方法 → 调用对应 SDK
2. **再查数据库**：SDK 无法满足时，通过 MCP Server 直接查数据库
3. **最后查其它**：以上都找不到时，再翻 Java 源码/查文档

**禁止跳过 SDK 直接操作数据库。**

---

### 4.6 常见问题

**Q：新环境怎么激活 SKILL？**

A：确保 `.claude/skills/` 目录结构与 CLAUDE.md 中的配置一致，Claude Code 启动时会自动识别。SKILL.md 中的 frontmatter `description` 字段包含触发词，匹配到会自动激活。

**Q：SDK 调用失败怎么办？**

A：先检查 `.claude/sdk/db-config.md` 数据库配置是否正确；再检查 MCP Server 是否正常运行；最后对照 `modeling-sdk-reference.md` 确认参数格式。

**Q：流程引擎/定时任务等未实现模块怎么办？**

A：这些模块目前在能力地图中标记为"手动操作"，会在开发设计文档中标注"不支持"并给出替代方案建议。后续会逐步完善 SDK 覆盖。

---

## 五、版本信息

- 工具包版本：v1.1
- 更新时间：2026-08-27
- 适用版本：泛微 e-cology 9
- 依赖：Python 3.10+、Claude Code、MCP Server
