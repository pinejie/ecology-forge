---
name: "oa-sdk-create"
description: "在泛微 e-cology OA 系统中创建二次开发 SDK。触发词：'创建 SDK'、'封装二开能力'、'建模引擎 SDK'、'MCP tool'、'新增 SDK'。当用户要求将泛微二开能力封装为 Python SDK 或 MCP tool 时使用。"
---

# 泛微二开 SDK 创建规范

在泛微 e-cology 9 中，建模引擎的二次开发能力（应用、模块、表单、查询、浏览框等）通过 Python SDK 封装，再由 MCP Server 暴露给 AI 调用。

本规范约束 AI 在编写 SDK 时的行为——**怎么写、放哪、怎么注册、怎么测试**。

---

## 一、前置条件：先读文档，再动手

写新 SDK 前，必须完成两件事：

### 1. 读项目文档

- `docs/PROJECT_OVERVIEW.md` — 系统架构、技术栈、开发模式
- `docs/modeling-engine/e9-spa-app-modeling.md` — 建模引擎 16 个子功能分析
- `docs/deep-dive/phase2-formmode-engine.md` — FormMode 建模引擎核心机制

### 2. 逆向追踪官方实现

**这是最关键的一步。** 不能只看数据库表结构就硬写 SDK。必须找到并阅读泛微官方代码，理解官方是怎么做这件事的。

---

## 代码深度追踪规则

> 核心原则：**追到底，不准停，边追边写，结论必须有出处。**

### 一、追踪流程（6 步）

**第 1 步：入口定位**
- 从 UI 页面或浏览器抓包拿到 API URL
- 通过 `struts-config.xml`、`@Path` 注解、或类名关键词找到对应的 Java class
- 在 rules 文档中记录：API URL → class 全限定名 → 入口方法

**第 2 步：执行流追踪**
- 从入口 class 的 `execute()` 方法开始逐行阅读
- **遇到方法调用就追** — 跳到被调用的方法继续读，不要在原处猜
- **遇到类引用就追** — 跳到被引用的类继续读（如 BrowserComInfo、FormManager、LabelComInfo）
- 持续追踪到最底层：SQL 语句、HTTP 请求、文件操作

**第 3 步：分支穷尽**
- 每个 `if` / `switch` / `try-catch` 分支都要展开
- 特别关注：
  - 数据库类型分支（Oracle / MySQL / SQL Server / PostgreSQL）
  - 字段类型分支（htmltype 1-8）
  - 权限校验分支（checkUserRight、checkBackRight）

**第 4 步：副作用识别**
- 找出所有 `executeSql()` / `execute()` / `executeUpdate()` 调用点
- 对每个调用点，提取完整的 SQL 语句格式（含拼接变量）
- 记录：SQL 类型（INSERT/UPDATE/DELETE/ALTER/CREATE）+ 触发条件 + 完整语句模板

**第 5 步：外部依赖识别**
- 识别所有 helper 类、工具类、manager 类的调用
- 对这些类执行同样的深度追踪（回到第 2 步）
- 直到判断：这个方法/逻辑**不影响** SDK 的调用方式、参数、顺序 → 才可以停止

**第 6 步：输出 rules 文档**
- 追踪完成后产出 rules 文档，包含：
  - 完整 SQL 清单（含触发条件、参数、数据库差异）
  - 完整参数表（参数名、类型、必填、默认值、来源）
  - 业务约束（ID 生成规则、表名规则、权限规则、关联关系）
  - 禁止事项（哪些操作不能做、哪些前缀不能用）
- **然后才能写 SDK**

### 二、判断标准（什么时候可以停）

**继续追的标准**（任一满足就继续）：
- 这个方法会影响 SDK 的调用顺序或参数
- 这个方法会写数据库 / 调外部接口 / 改文件
- 这个方法会做权限校验 / 数据校验 / 类型转换
- 这个方法里有 if/switch 分支还没展开

**可以停的标准**（全部满足才停）：
- 纯日志输出（log.info、log.debug）
- 纯工具方法（字符串格式化、空值判断）且已确认不影响业务逻辑
- 纯 UI 渲染（前端 HTML 拼接）且已确认不涉及后端逻辑
- 你自己判断：这块逻辑不会改变 SDK 的调用方式

### 三、禁止事项

- **禁止**仅凭 JSP / 前端页面推断后端逻辑，必须反编译 class 确认
- **禁止**看到主流程就停止，必须追踪所有 if/switch 分支
- **禁止**跳过 helper 类（BrowserComInfo、FormManager 等），必须反编译其完整逻辑
- **禁止**凭经验猜测字段类型映射、参数格式、表名规则，必须从代码中提取
- **禁止**在追踪中途开始写 SDK

### 四、必须事项

- 必须从入口 class 的 `execute()` 方法开始，追踪到最终 SQL 语句或外部调用
- 必须找出所有 `executeSql()` / `execute()` 调用点，列出完整 SQL
- 必须确认 4 种数据库的差异处理（Oracle / MySQL / SQL Server / PostgreSQL）
- 必须确认所有字段类型分支的映射关系（如 htmltype 1-8 对应什么 fielddbtype）
- 必须边追踪边记录，每条结论标注来源（`类名.class:字节码行号`）

### 五、验证标准

- rules 文档中每条结论都必须有对应的 `class:行号` 或 javap 输出引用
- 不能说"大概是"、"应该是"、"大概是这个意思"，必须是代码中明确找到的
- **反面例子**："浏览框 fielddbtype 见 BrowserComInfo" → 等于没结论，必须打开 BrowserComInfo 把具体映射扒出来
- **正面例子**："htmltype=3 时，BrowserComInfo.getBrowserdbtype() 返回：人员→integer, 部门→integer, 分部→integer" → 有具体值

---

具体步骤：
1. 用 `javap -c -p` 反编译相关的 Java class 文件
2. 从 `execute()` 方法开始，逐行阅读字节码
3. 总结出：官方分几步、操作了哪些表、有什么前置校验、清什么缓存、事务边界在哪
4. 把总结写在 `docs/sdk-references/{能力名}-rules.md` 中，作为 SDK 编写的依据

**已有的业务规则文档** 存放在 `docs/sdk-references/` 目录。写新 SDK 前先查找是否已有对应文档：
- 有 → 读它，按里面的规则写 SDK
- 没有 → 先逆向分析，写一份放进去，再写 SDK

---

## 二、SDK 代码规范

### 文件位置

- Python SDK：`sdk/python/{能力名}_sdk.py`
- 测试/demo 脚本：`sdk/python/demo_{能力名}.py`

### 代码结构

```python
# -*- coding: utf-8 -*-
"""
泛微 E9 OA 建模引擎 SDK — {能力名}

通过直连 SQL Server 数据库，封装建模引擎的 {能力名} 操作。

依赖：pip install pymssql

使用示例：
    from {能力名}_sdk import {能力名}SDK

    sdk = {能力名}SDK(host="...", user="...", password="...", database="ecology")
    result = sdk.create_{能力名}(...)
"""

import pymssql
import time
from typing import List, Dict, Optional


class {能力名}SDK:
    """建模引擎 {能力名} SDK"""

    def __init__(self, host: str = None, user: str = None, password: str = None, database: str = None):
        self.host = host
        self.user = user
        self.password = password
        self.database = database

    def _connect(self):
        """连接 SQL Server，不指定 charset，由手动编码处理"""
        return pymssql.connect(
            server=self.host, user=self.user,
            password=self.password, database=self.database
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
            return val.encode("latin1").decode("gbk")
        return str(val)

    # ============================================================
    #  {能力名} 操作
    # ============================================================

    def create_{能力名}(self, ...) -> int:
        """
        创建 {能力名}

        :param ...
        :return: 新建的 ID
        """
        # 1. 参数校验
        # 2. 前置检查（父记录存在性等）
        # 3. 执行 SQL（INSERT/UPDATE），字符串参数用 self._encode() 编码
        # 4. INSERT 后立即 SELECT COUNT(*) 验证写入成功
        # 5. 事务必须有 try/commit/rollback/finally
        # 6. 返回 ID
        pass
```

### 命名规范

| 项 | 规则 | 示例 |
|---|------|------|
| SDK 类名 | `{能力名}SDK` | `AppSDK`、`FormSDK`、`ModuleSDK` |
| SDK 文件名 | `{能力名}_sdk.py` | `app_sdk.py`、`form_sdk.py` |
| 方法名 | 动词_{能力名} | `create_app`、`list_forms`、`delete_module` |
| 测试脚本 | `demo_{能力名}.py` | `demo_app.py`、`demo_form.py` |

### 数据库操作约束

1. **必须用 pymssql**，禁止用原生 JDBC 或其他方式
2. **中文字段必须手动编码** — 写入用 `_encode(s)` 转为 GBK bytes，读取用 `_decode(val)` 还原。禁止依赖 `charset="utf8"` 或 `charset="cp936"`，pymssql 的 charset 参数对 varchar 列无效且会导致中文乱码
3. **先验证后操作** — INSERT 前必须 `SELECT` 确认父记录存在，DELETE 前确认目标存在
4. **INSERT 后必须验证** — 每条 INSERT 后执行 `SELECT COUNT(*)` 确认记录已写入，防止竞态条件导致空引用
5. **事务必须有 try/commit/rollback/finally** — 任何写操作都要包事务，所有步骤在一个事务中，最后统一 commit
6. **禁止操作 `classbean.jar` 里的预编译逻辑** — 只操作配置表，不改核心 class

### ID 生成规则

建模表单（workflow_bill）的 ID 必须为**负数**，与浏览器创建的表单保持一致：

```python
def _get_next_form_id(self, cursor) -> int:
    """生成 workflow_bill 的表单 ID（负数，与浏览器创建保持一致）"""
    cursor.execute("SELECT ISNULL(MIN(id), 0) - 1 FROM workflow_bill")
    row = cursor.fetchone()
    return int(row[0]) if row else -1
```

其他表的 ID 用 `MAX(id) + 1`，加冲突重试：

```python
def _get_next_id(self, cursor, table: str) -> int:
    """生成非自增表的下一个 ID（MAX(id)+1），加重试防并发冲突"""
    for attempt in range(5):
        cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM %s" % table)
        row = cursor.fetchone()
        next_id = int(row[0]) if row else 1
        # 验证该 ID 尚未被占用
        cursor.execute("SELECT COUNT(*) FROM %s WHERE id = %s" % (table, next_id))
        if int(cursor.fetchone()[0]) == 0:
            return next_id
        time.sleep(0.05 * (attempt + 1))
    raise RuntimeError("生成 ID 冲突：表 %s 连续 5 次获取的 ID 已被占用" % table)
```

### 标签创建规范（HtmlLabelIndex + HtmlLabelInfo）

建模表单/字段的名称通过多语言标签系统管理，每次创建标签需：

1. 先查是否已有同名标签：`SELECT indexid FROM HtmlLabelInfo WHERE labelname = %s AND languageid = 7`
2. 有则复用，无则新建
3. 新建时先 INSERT `HtmlLabelIndex`，再 INSERT 3 条 `HtmlLabelInfo`（languageid = 7, 8, 9 分别对应中文、英文、繁体）
4. **每条 INSERT 后必须 SELECT COUNT(*) 验证**，确保非原子 ID 生成不会留下空引用

### 浏览框字段处理

浏览框字段支持 `browser_id`（直接指定 ID）或 `browser_name`（按名称自动匹配）两种方式：

```python
# 传 ID（精确）
{"type": "browser", "browser_id": 3}

# 传名称（SDK 自动解析）
{"type": "browser", "browser_name": "人力资源"}
```

匹配逻辑分两步：
1. 先查 `wf_browser_config`（E9 新版浏览框）
2. 兜底查 `workflow_browserurl`（经典版浏览框，如"日期"、"人力资源"）

### 错误处理

- **参数校验失败** → 抛 `ValueError`，消息明确告诉用户缺了什么（如"应用名称不能为空"）
- **前置条件不满足** → 抛 `ValueError`，说明具体原因（如"上级应用不存在，ID=999"）
- **数据库操作失败** → 抛 `RuntimeError`，包含原始错误信息
- **禁止吞异常** — 每个方法要么成功返回，要么抛出有意义的异常

### 返回值规范

- **创建操作** → 返回 `{"form_id": int, "table_name": str}` 等结构化字典
- **查询操作** → 返回 `List[Dict]`，每个 dict 有统一字段
- **修改/删除操作** → 无返回值（void），失败抛异常
- **禁止返回 bool 或纯字符串**

---

## 三、MCP Server 自动注册

所有 SDK 方法统一注册到 `weaver-oa-mcp` MCP Server。

**新增 SDK 方法不需要手动注册 MCP tool，使用 `@expose` 装饰器即可自动暴露。**

### 注册方式

在 SDK 方法上加 `@expose` 装饰器，MCP Server 启动时自动扫描注册：

```python
from mcp_register import expose

class MySDK:
    @expose(
        description="功能描述（AI 能看懂）",
        examples=[{"param1": "值1"}, {"param1": "值2"}],
        error_hints={"错误关键词": "用户友好的解决建议"},
        read_only=True,       # 只读操作（默认 False）
        destructive=True      # 破坏性操作（默认 False）
    )
    def my_method(self, name: str, count: int = 0) -> int:
        """
        方法描述

        :param name: 参数描述（必填）
        :param count: 参数描述（选填）
        :return: 返回值描述
        """
        pass
```

`@expose` 装饰器会自动：
1. 从方法签名提取参数名、类型、默认值
2. 从 docstring 的 `:param` 行提取参数描述
3. 生成 Pydantic Input 模型
4. 注册为 MCP tool，tool 名为 `{类名小写}_{方法名}`

### MCP Server 结构

```
MCP Server: weaver-oa-mcp
├── modeling_create_app       (name, parent_id, description, show_order)
├── modeling_rename_app       (app_id, new_name)
├── modeling_delete_app       (app_id)
├── modeling_list_apps        (parent_id)
├── modeling_move_app         (app_id, new_parent_id)
├── ... 后续能力（自动注册，无需改 mcp_server.py）
└── oa_clear_cache            ()
```

### mcp_server.py（入口文件，无需修改）

```python
from mcp.server.fastmcp import FastMCP
from mcp_register import auto_register

mcp = FastMCP("weaver_oa_mcp")
auto_register(mcp)  # 一行搞定，后续新增 SDK 方法自动注册
```

### 返回值格式

MCP tool 调用结果必须是结构化 JSON：

```json
// 成功
{"status": "1", "data": {"id": 1066}, "message": "成功"}

// 失败
{"status": "-1", "message": "上级应用不存在，ID=999"}
```

## 四、测试规范

每个 SDK 方法必须有对应的测试脚本，测试脚本放在 `sdk/python/demo_{能力名}.py`。

测试脚本必须跑通三步：
1. **创建** — 调用创建方法
2. **验证** — 查询确认数据已写入
3. **清理** — 删除测试数据（软删除）

测试前需要确认 `pymssql` 已安装（`pip install pymssql`）。

---

## 五、禁止事项

### 技术红线

- **禁止浏览器自动化** — Playwright/Playwright 方案已验证不可行（权限问题 + SPA session 隔离）
- **禁止绕过 SDK 直接调 JSP** — 不通过 JSP 页面操作二开能力
- **禁止操作 `formtable_main_` 前缀的表** — 那是流程表单，建模引擎用 `uf_` 开头
- **禁止修改 `classbean.jar`** — 只操作配置表，不改预编译 class
- **禁止依赖 pymssql charset 参数处理中文** — 必须用 `_encode`/`_decode` 手动处理 GBK 编码

### 安全红线

- **数据库密码不硬编码** — 从环境变量或配置文件读取
- **所有中文数据必须手动编码** — 通过 `_encode()` 方法转为 GBK bytes

---

## 六、能力扩展流程

当需要新增一个二开能力（比如"创建表单"）时，按以下流程：

1. **逆向分析** — 找到泛微官方代码（Java/JSP），理解官方实现
2. **写业务规则文档** — 保存到 `docs/sdk-references/{能力名}-rules.md`
3. **写 SDK 代码** — `sdk/python/{能力名}_sdk.py`，遵循本规范
4. **写测试脚本** — `sdk/python/demo_{能力名}.py`，跑通创建→验证→清理
5. **自动注册** — `@expose` 装饰器自动注册到 `weaver-oa-mcp`，无需改 `mcp_server.py`
6. **验证** — 运行测试脚本确认功能正常

---

## 七、现有能力清单

| 能力 | SDK 文件 | 状态 |
|------|---------|------|
| 应用（App） | `sdk/python/modeling_sdk.py` | 已完成 |
| 表单（Form） | `sdk/python/form_sdk.py` | 已完成 |
| 模块（Module） | — | 待开发 |
| 查询（Query） | — | 待开发 |
| 浏览框（Browser） | — | 待开发 |
| 缓存清理 | — | 待开发 |
