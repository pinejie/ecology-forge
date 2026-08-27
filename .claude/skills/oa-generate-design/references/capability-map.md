# 泛微二开能力地图

> 最后更新：2026-08-17
> 本文件定义泛微二开的能力层级和依赖关系。具体 SDK 参数格式见 `modeling-sdk-reference.md`。

---

## 能力层级关系

```
建模引擎能力：
├── 菜单（左侧门户入口）
├── 应用（功能分组容器）
├── 表单（数据骨架，定义字段和物理表）
├── 模块（卡片页载体：新建/编辑/查看单条数据）
│     ├── 布局配置（字段分组、排序、显示状态）
│     └── 字段联动（选 A 自动带出 B、C）
├── 查询（列表页载体：浏览/筛选/排序多条数据）
│     └── 快捷搜索（查询顶部的即时搜索栏）
└── 浏览框（选择器：从已有数据中选择记录）
```

---

## 依赖链条

```
菜单（指向查询ID）
  → 查询（属于某个模块）
    → 模块（关联某个表单）
      → 表单（定义字段和表结构）
        → 浏览框（引用某个表单作为数据源）
```

**核心规则**：
- **菜单** — 用户打开 OA 左侧门户看到的第一级入口，点击后跳转到查询页面
- **应用** — 功能分组容器，模块、查询、浏览框都必须属于某个应用
- **表单** — 数据骨架，定义字段和物理存储表
- **模块** — 卡片页载体，用户点"新增/编辑/查看"时看到的单条数据页面
- **查询** — 列表页载体，用户打开菜单第一眼看到的表格
- **浏览框** — 数据选择器，表单中的选值型字段

**默认规则**：每个表单都必须至少有一个模块和一个查询。除非明确说"仅通过流程使用"，否则不允许漏配。

---

## 正向执行顺序

| 步骤 | 动作 | 产出 | 下游谁需要 |
|------|------|------|-----------|
| 1 | 确认/创建应用 | 应用 ID | 模块、查询、浏览框 |
| 2 | 创建表单 + 字段 | 表单 ID + 字段列表 | 模块、查询、浏览框、布局、联动 |
| 3 | 刷新缓存 | — | 让 label 生效 |
| 4 | 创建自定义浏览框 | 浏览框配置 | 表单字段 |
| 5 | 补加跳过字段 | 字段列表 | — |
| 6 | 创建模块 | 模块 ID | 查询、布局、联动 |
| 7 | 创建查询列表 | 查询配置 | 菜单、快捷搜索 |
| 8 | 配置布局/联动 | 布局 JSON + 联动规则 | — |
| 9 | 配置快捷搜索 | 快捷搜索条件 | — |
| 10 | 创建菜单 | 菜单项 | — |

**按需裁剪**：不是每一步都要做，根据需求提取步骤子集。

---

## 各能力域概览

### 1. 应用（App）

功能分组容器。模块、查询、浏览框都必须属于某个应用。应用本身不是用户可见的页面。

| 能力 | MCP Tool |
|------|----------|
| 创建应用 | `modeling_create_app` |
| 列出应用 | `modeling_list_apps` |
| 重命名应用 | `modeling_rename_app` |
| 删除应用 | `modeling_delete_app` |
| 移动应用 | `modeling_move_app` |

### 2. 表单（Form）

数据骨架，定义字段的名称、类型、默认值，自动创建物理表。

| 能力 | MCP Tool |
|------|----------|
| 创建表单 | `form_create_form` |
| 智能添加字段 | `form_auto_add_fields` |
| 批量添加字段 | `form_add_fields` |
| 列出表单 | `form_list_forms` |
| 获取表单字段 | `form_list_form_fields` |
| 删除表单 | `form_delete_form` |

### 3. 浏览框（Browser）

数据选择器。分系统浏览框（内置）和自定义浏览框（基于自定义表单创建）。

**系统浏览框**：人员=1、多人力资源=17、部门=3、多部门=18

| 能力 | MCP Tool |
|------|----------|
| 创建自定义浏览框 | `browser_create_browser` |
| 获取表单字段（浏览框用） | `browser_get_form_fields` |
| 列出浏览框 | `browser_list_browsers` |
| 列出系统浏览框 | `form_list_browsers` |
| 搜索浏览框 | `form_search_browser` |
| 删除浏览框 | `browser_delete_browser` |

### 4. 模块（Module）

卡片页载体。创建时自动产生三种布局（查看/新建/编辑）+ 9 条默认权限。

| 能力 | MCP Tool |
|------|----------|
| 创建模块 | `module_create_module` |
| 列出模块 | `module_list_modules` |
| 获取模块详情 | `module_get_module_detail` |
| 修改模块 | `module_update_module` |
| 软删除模块 | `module_delete_module` |
| 物理删除模块 | `module_physical_delete_module` |

### 5. 布局配置（Layout）

控制模块中新建/编辑/查看页面的字段分组、排序和显示状态。

| 能力 | MCP Tool |
|------|----------|
| 生成布局配置 | `layout_generate_layout_json` |
| 插入布局 | `layout_insert_layout` |

### 6. 查询（Query）

列表页载体。定义显示列、筛选条件、排序规则、点击跳转。

| 能力 | MCP Tool |
|------|----------|
| 创建查询列表 | `list_create_query` |
| 列出查询列表 | `list_list_queries` |
| 修改查询列表 | `list_update_query` |
| 删除查询列表 | `list_delete_query` |
| 保存显示字段 | `list_save_formfields` |
| 获取显示字段 | `list_get_formfields` |

### 7. 快捷搜索（QuickSearch）

查询列表顶部的单行即时搜索栏。每个查询应至少配置一个快捷搜索条件。

| 能力 | MCP Tool |
|------|----------|
| 创建快捷搜索 | `quicksearch_create_quicksearch_setting` |
| 添加搜索条件 | `quicksearch_add_quicksearch_condition` |
| 列出搜索条件 | `quicksearch_list_quicksearch_conditions` |
| 修改搜索条件 | `quicksearch_update_quicksearch_condition` |
| 删除搜索条件 | `quicksearch_delete_quicksearch_condition` |
| 清空所有条件 | `quicksearch_delete_all_quicksearch_conditions` |

### 8. 菜单（Menu）

OA 左侧门户菜单树。末级菜单必须指向一个查询 ID。

| 能力 | MCP Tool |
|------|----------|
| 创建菜单 | `menu_create_menu` |
| 批量创建子菜单 | `menu_create_sub_menus` |
| 查询菜单树 | `menu_get_menu_tree` |
| 查询菜单详情 | `menu_get_menu_detail` |
| 编辑菜单 | `menu_update_menu` |
| 删除菜单 | `menu_delete_menu` |
| 设置菜单可见性 | `menu_set_menu_visibility` |
| 清除菜单缓存 | `menu_clear_menu_cache` |

### 9. 字段联动（Field Linkage）

当某个字段的值变化时，自动从数据库查询数据并填充到其他字段。

| 能力 | MCP Tool |
|------|----------|
| 创建联动规则 | `fieldlinkage_create_linkage` |
| 列出联动规则 | `fieldlinkage_list_linkages` |
| 删除联动规则 | `fieldlinkage_delete_linkage` |
| 切换启用状态 | `fieldlinkage_toggle_enabled` |

### 10. 缓存管理

清除建模引擎缓存，使配置变更立即生效。

| 能力 | MCP Tool |
|------|----------|
| 刷新 Label 缓存 | `cache_refresh_label_cache` |

---

## 数据库操作

| 能力 | MCP Tool | 说明 |
|------|----------|------|
| 列出表 | `mcp__mssql-ecology__list_tables` | 查看数据库表 |
| 查询数据 | `mcp__mssql-ecology__read_query` | SELECT 查询 |
| 写入数据 | `mcp__mssql-ecology__write_query` | INSERT/UPDATE/DELETE |
| 创建表 | `mcp__mssql-ecology__create_table` | CREATE TABLE |
| 查看表结构 | `mcp__mssql-ecology__describe_table` | 查看表字段 |
| 修改表 | `mcp__mssql-ecology__alter_table` | 修改表结构 |
| 导出查询 | `mcp__mssql-ecology__export_query` | 导出为 CSV/JSON |

---

## 手动步骤（非自动化）

### 流程引擎

| 能力 | 操作位置 | 说明 |
|------|---------|------|
| 创建审批流程 | OA 管理后台 > 流程引擎 > 流程设置 | 节点配置、审批人、流转条件 |
| 配置签字意见 | OA 管理后台 > 流程引擎 > 签字设置 | 签字格式、必填项 |
| 配置流程权限 | OA 管理后台 > 流程引擎 > 权限设置 | 谁能发起、谁能审批 |

### 角色权限

| 能力 | 操作位置 | 说明 |
|------|---------|------|
| 角色权限 | OA 管理后台 > 权限管理 | 谁能看到菜单、能做什么 |

---

## 不支持的能力

| 需求类型 | 原因 | 替代方案 |
|---------|------|---------|
| 移动端原生 App | 泛微只有 H5 移动端 | 用 H5 页面适配 |
| 复杂报表导出 | 泛微报表功能有限 | 导出到 Excel 后处理 |
| 实时推送通知 | 泛微无 WebSocket 推送 | 用定时任务轮询 |

---

*注：此文件是活的，能力变化时同步更新。SDK 参数细节见 `modeling-sdk-reference.md`。*
