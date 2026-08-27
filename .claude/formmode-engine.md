# 建模引擎 (FormMode) 知识图谱

> 生成时间：2026-07-03
> 扫描范围：`classbean/weaver/formmode/` (501 class)、`classbean/com/api/formmode/` (277 class)、`formmode/` web 目录 (655 JSP)、11 个 MyBatis Mapper XML

---

## 一、引擎定位

建模引擎是泛微 e-cology 9 的**核心低代码引擎**，允许用户通过 UI 界面（无需编码）创建：

| 应用类型 | 说明 |
|---------|------|
| **建模表单** | 基于 `modeinfo` 注册，绑定 `workflow_bill` 表单，生成 `uf_*` 业务表 |
| **自定义查询** | 基于 `mode_customsearch` 注册，多表 SQL 查询，带搜索条件 |
| **数据报表** | 基于 `mode_report` 注册，数据聚合 + 图表展示 |
| **自定义浏览框** | 基于 `mode_custombrowser` 注册，数据选择器 |
| **树形导航** | 基于 `modeTreeField` 配置，层级数据展示 |
| **自定义页面** | 基于 `mode_custompage` / `cpt_custompage`，自由页面 |

---

## 二、整体架构（三层代码演进）

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: com.api.formmode.*  (277 classes, 现代层)              │
│  ┌───────────┬───────────┬──────────┬───────────┬───────────┐   │
│  │ MyBatis   │ page/     │ service/ │ web/      │ util/     │   │
│  │ bean/dao/ │ action/   │          │           │           │   │
│  │ mapper/   │ adapter/  │          │           │           │   │
│  │ xml       │ pages/    │          │           │           │   │
│  │           │ coms/     │          │           │           │   │
│  └───────────┴───────────┴──────────┴───────────┴───────────┘   │
│                                                                  │
│  Layer 2: com.engine.*  (间接调用)                                │
│  com.engine.kq / hrm / fna 等业务引擎通过 formmode 接口读写数据   │
│                                                                  │
│  Layer 1: weaver.formmode.*  (501 classes, 核心层)               │
│  ┌──────────┬───────────┬──────────┬──────────┬────────────┐    │
│  │ manager/ │ browser/  │ setup/   │ data/    │ exceldesign│    │
│  │ field/   │ interfaces│ task/    │ exttools │ expcard/   │    │
│  │ service/ │ search/   │ virtual  │ excel/   │ webservice │    │
│  │ dao/     │ cuspage/  │ custom   │ reply/   │ report/    │    │
│  └──────────┴───────────┴──────────┴──────────┴────────────┘    │
│                                                                  │
│  Layer 0: weaver.conn.RecordSet  (数据库)                         │
└──────────────────────────────────────────────────────────────────┘
```

**演进关系**：
- **Layer 1** (`weaver.formmode`) 是最早的 JSP+Servlet 实现，直接操作数据库
- **Layer 3** (`com.api.formmode`) 是重构后的 REST API 层，引入 MyBatis + 适配器模式
- 两者**共存**：管理后台用 Layer 1 的 JSP，前端展示用 Layer 3 的 REST API

---

## 三、数据模型（核心表）

### 3.1 表单定义层（与流程引擎共享）

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `workflow_bill` | 表单主表（建模+流程共享） | `id`, `billname`, `tablename` |
| `workflow_billfield` | 表单字段定义 | `id`, `billid`, `fieldname`, `fieldLabel`, `fieldHtmlType`, `fieldDbType`, `detailTable`, `type` |
| `workflow_billdetailtable` | 明细表定义 | `id`, `billid`, `tableName`, `title`, `orderId` |
| `workflow_selectItem` | 下拉选项 | `id`, `fieldId`, `selectName`, `selectValue` |

### 3.2 建模注册层

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `modeinfo` | 建模应用注册表 | `id`, `modename`, `formid`, `tablename` |
| `modeHtmlLayout` | HTML 布局定义 | `id`, `modeId`, `formId`, `type`, `layoutName`, `dataJSON`, `pluginJSON`, `scripts` |
| `modeFormField` | 表单字段-建模映射 | `fieldId`, `modeId`, `layoutId`, `isedit` |

### 3.3 功能扩展层

| 表名 | 说明 |
|------|------|
| `mode_CustomDspField` | 自定义浏览框显示字段 |
| `mode_customsearch` | 自定义查询定义 |
| `mode_customsearchButton` | 自定义查询按钮 |
| `mode_report` | 报表定义 |
| `mode_custombrowser` | 自定义浏览框定义 |
| `mode_custompage` / `cpt_custompage` | 自定义页面 |
| `modeTreeField` | 树形字段配置 |
| `mode_pageExpand` | 页面扩展按钮 |
| `mode_batchSet` | 批量操作设置 |
| `mode_batchmodifydetail` | 批量修改明细字段 |
| `modefieldauthorize` | 字段权限 |
| `mode_RemindJob` | 定时提醒任务 |

### 3.4 业务数据层

建模引擎创建的**业务数据表**以 `uf_` 前缀命名，一个建模应用 = 一张 `uf_xxx` 主表 + N 张 `uf_xxx_dtN` 明细表。

---

## 四、核心模块详解

### 4.1 Layer 1: weaver.formmode.* (核心层, 501 classes)

#### manager/ — 管理器（3 类）
| 类 | 作用 |
|---|------|
| `FieldAttrManager` | 字段属性管理 |
| `ModeFormFieldMainManager` | 建模主字段管理 |
| `ModeFormGroupManager` | 字段分组管理 |

#### browser/ — 浏览框引擎（7 类, ~74KB）
| 类 | 大小 | 作用 |
|---|------|------|
| `FormModeBrowserDataSource` | 16KB | 数据源解析 |
| `FormModeBrowserUtil` | 16KB | 浏览框工具 |
| `FormModeBrowserSqlwhere` | 11KB | SQL WHERE 条件构建 |
| `FormModeBrowserClause` | 2KB | 浏览框条件子句 |

#### setup/ — 建模配置（31 类）
| 类组 | 包含类 | 作用 |
|------|--------|------|
| 权限 | `ModeRightInfo`, `ModeRightInfoExtend`, `ModeRightForPage`, `ModeRightService`, `ModeRightInfoSingleThread`, `ModeRightInfoThread` | 数据权限控制（按人/部门/公司过滤） |
| 表达式 | `ShareExpressionBean/Expressions/RuleBusiness`, `ModeTriggerWorkflowExpressionBean/...`, `WorkflowToModeExpressionBean/...`, `ExpandBaseRightExpressionBean/...` | 表达式解析引擎（分享、触发流程、工作流转建模） |
| 工具 | `ModeSetUtil`, `ModeLayoutUtil`, `ModeLinkageInfo` | 建模工具、布局、联动 |
| 树 | `ModeTreeFieldManager`, `ModeTreeFieldComInfo` | 树形字段管理 |

#### data/ — 数据管理（12 类）
| 类 | 作用 |
|---|------|
| `ModeDataManager` | 34KB，建模数据 CRUD 核心 |
| `ModeDataApproval` | 数据审批 |
| `ModeDataBatchImport` | 批量导入 |
| `ModeDataIdUpdate` / `ModeDataIDUpdateSingle` | ID 更新 |
| `FormInfoDao` | 表单信息查询 |
| `BaseDao` | 基础 DAO |
| `WorkFlowInit` | 流程初始化 |

#### interfaces/ — 外部接口（49 类）
| 子包 | 类数 | 作用 |
|------|------|------|
| 根目录 | 16 | 导入导出转换、权限通用操作 |
| `action/` | 11 | 工作流→建模数据同步 (`WorkflowToMode`, `SapAction`, `WebServiceAction`) |
| `dmlaction/` | 10 | DML 操作（增删改 SQL 生成） |
| `impl/` | 5 | 客户定制按钮显示/导入转换实现 |
| `rebuilddata/` | 5 | 工作流→建模数据重建 |

#### exceldesign/ — Excel 布局设计（16 类）
| 类 | 作用 |
|---|------|
| `ParseLayoutToHtml` | Excel 布局 → HTML 转换 |
| `ParseExcelLayout` | Excel 布局解析 |
| `ExcelLayoutManager` | Excel 布局管理 |
| `ExcelNodeFieldManager` | Excel 节点字段管理 |
| `CreateBarCodeServlet` / `CreateQRCodeServlet` | 条码/二维码生成 |

#### 其他模块
| 模块 | 类数 | 作用 |
|------|------|------|
| `exttools/` | 60 | 外部工具（导入导出/数据同步） |
| `task/` | 34 | 定时任务 |
| `excel/` | 22 | Excel 处理 |
| `field/` | 23 | 字段定义/渲染 |
| `search/` | 15 | 搜索引擎 |
| `expcard/` | 21 | 导出卡片/报表 |
| `cuspage/` | 27 | 自定义页面 |
| `virtualform/` | 10 | 虚拟表单 |
| `webservice/` | 11 | Web Service 接口 |
| `customjavacode/` | 40 | 自定义 Java 代码扩展点 |
| `esb/` | 5 | ESB 集成 |

### 4.2 Layer 3: com.api.formmode.* (REST API 层, 277 classes)

```
com.api.formmode/
├── web/                          # REST 入口
│   ├── FormmodeFormAction        # 表单操作 (@Path: /api/formmode/form)
│   ├── FormmodeListAction        # 列表操作 (@Path: /api/formmode/list)
│   ├── FormmodeTreeAction        # 树形操作 (@Path: /api/formmode/tree)
│   └── page/                     # 页面路由
│       ├── Index                 # 首页
│       ├── App                   # 应用页
│       ├── Data                  # 数据页
│       ├── Set                   # 设置页
│       └── Base                  # 基类
│
├── mybatis/                      # ORM 层
│   ├── bean/                     # 数据模型 (18 Bean 类)
│   │   ├── ModeInfoBean          # 建模应用信息
│   │   ├── ModeLayoutBean        # HTML 布局定义
│   │   ├── FieldBean             # 字段信息
│   │   ├── FormFieldBean         # 表单字段
│   │   ├── DetailTableBean       # 明细表
│   │   ├── SelectItemBean        # 下拉选项
│   │   ├── ModeFieldSelectItemBean # 建模字段+下拉
│   │   ├── ModeRightInfoBean     # 权限信息
│   │   ├── CustomSearchBean      # 自定义查询
│   │   ├── CustomSearchButtonBean # 查询按钮
│   │   ├── CustomSearchBatchSetBean # 批量设置
│   │   ├── CustomPageBean        # 自定义页面
│   │   ├── TreeParams            # 树参数
│   │   ├── TreeNodeBean          # 树节点
│   │   ├── CardParams            # 卡片参数
│   │   ├── SplitPageParams       # 分页参数
│   │   ├── SplitPageResult       # 分页结果
│   │   ├── PrimaryKeyBean        # 主键
│   │   ├── SetBean               # 设置
│   │   ├── BatchSqlBean          # 批量 SQL
│   │   ├── CountBean             # 计数
│   │   ├── OrderByBean           # 排序
│   │   └── SqlWhereBean          # WHERE 条件
│   │
│   ├── dao/                      # 数据访问 (9 DAO 类)
│   │   ├── FormDao               # 表单 DAO
│   │   ├── CardDao               # 卡片视图 DAO
│   │   ├── CustomSearchDao       # 自定义查询 DAO
│   │   ├── CustomMenuDao         # 自定义菜单 DAO
│   │   ├── CustomPageDao         # 自定义页面 DAO
│   │   ├── CustomTreeDao         # 自定义树 DAO
│   │   ├── TreeDao               # 树 DAO
│   │   ├── EditableTableDao      # 可编辑表格 DAO
│   │   └── ModeMapper (via MyBatis)
│   │
│   ├── mapper/                   # MyBatis Mapper 接口 (11)
│   │   └── *.xml                 # 对应的 XML 映射文件 (11)
│   ├── param/                    # 参数类 (3)
│   └── util/                     # SQL 工具 (SqlProxyHandle, SqlUtil)
│
├── page/                         # 页面渲染层
│   ├── action/                   # 操作框架
│   │   ├── Action                # 操作接口
│   │   ├── impl/                 # 实现
│   │   │   ├── BatchEditAction   # 批量编辑
│   │   │   └── DeleteAction      # 删除
│   │   └── proxy/                # 代理
│   │       └── ActionProxyHandle # 操作代理句柄
│   │
│   ├── adapter/                  # 适配器 (80+ 类)
│   │   ├── card/                 # 卡片适配器 (18)
│   │   │   ├── FormBaseAdapter   # 表单基础
│   │   │   ├── ModeBaseAdapter   # 建模基础
│   │   │   ├── ModeBarCode       # 条形码
│   │   │   ├── ModeCodeAdapter   # 二维码
│   │   │   ├── ModeQRCodeAdapter # 二维码
│   │   │   ├── ModeReplayAdapter # 回复
│   │   │   ├── ModeTriggerBaseAdapter        # 触发器
│   │   │   ├── ModeWorkflowToModeBaseAdapter # 流程→建模
│   │   │   ├── BrowserBaseAdapter # 浏览框
│   │   │   ├── BrowserTypeBaseAdapter         # 浏览框类型
│   │   │   ├── PageBaseAdapter   # 页面
│   │   │   ├── ReportBaseAdapter # 报表
│   │   │   ├── ResourceBaseAdapter # 资源
│   │   │   ├── SearchBaseAdapter  # 搜索
│   │   │   ├── SearchButtonBaseAdapter # 搜索按钮
│   │   │   ├── TreeBaseAdapter   # 树
│   │   │   └── VirtualFormBaseAdapter # 虚拟表单
│   │   │
│   │   ├── grid/                 # 网格适配器
│   │   │   └── AppInfoGridAdapter
│   │   ├── menu/                 # 菜单适配器 (9)
│   │   │   └── BrowserSettingAdapter, FormSettingAdapter, ModeSettingAdapter...
│   │   ├── search/               # 搜索适配器
│   │   │   ├── CustomSearchAdapter
│   │   │   └── E8SearchAdapter
│   │   ├── simpletable/          # 简单表格适配器 (16)
│   │   │   └── ModeLayoutAdapter, ModeRightAdapter, ModeTriggerAdapter...
│   │   ├── tabpage/              # 标签页适配器 (9)
│   │   │   └── ModeInfoTabAdapter, FormInfoTabAdapter, BrowserInfoTabAdapter...
│   │   ├── tree/                 # 树适配器 (10)
│   │   │   └── AppTreeAdapter, BrowserAppTreeAdapter, FormAppTreeAdapter...
│   │   ├── steppage/             # 步骤页适配器
│   │   │   └── ModeAddAdapter
│   │   ├── transformpage/        # 转换页适配器
│   │   │   └── ModeTriggerAddAdapter
│   │   └── custom/               # 自定义适配器
│   │       └── WorkflowToModeSetAdapter
│   │
│   ├── bean/                     # 页面 Bean
│   │   └── ActionBean, ButtonBean, ColumnBean...
│   │
│   ├── coms/                     # UI 组件
│   │   ├── Component             # 组件基类
│   │   ├── impl/
│   │   │   ├── advanced/         # 高级组件 (Advanced, AdvancedGroup)
│   │   │   ├── field/            # 字段组件 (Field, BrowserField, CheckboxField, SelectField, TextInputField, NumberInputField)
│   │   │   ├── grid/             # 网格组件 (Panel, Group, IconCom, TimeLine)
│   │   │   ├── menu/             # 菜单 (Menu)
│   │   │   ├── row/              # 行组件 (Row, Col, Group)
│   │   │   ├── step/             # 步骤 (Step)
│   │   │   ├── table/            # 表格 (Table)
│   │   │   ├── tabs/             # 标签 (TabPane, QuickTab)
│   │   │   ├── top/              # 顶部 (Top, TopExtra, SmallTop)
│   │   │   └── tree/             # 树 (Tree)
│   │
│   ├── pages/                    # 页面实现 (12)
│   │   ├── Page                  # 页面基类
│   │   ├── impl/
│   │   │   ├── Card              # 卡片视图
│   │   │   ├── Grid              # 网格视图
│   │   │   ├── Search            # 搜索视图
│   │   │   ├── TabPage           # 标签页视图
│   │   │   ├── Tree              # 树视图
│   │   │   ├── SimpleTable       # 简单表格视图
│   │   │   ├── CarouselPage      # 轮播页
│   │   │   ├── StepPage          # 步骤页
│   │   │   ├── LeftRightLayout   # 左右布局
│   │   │   ├── ThreeSideLayout   # 三栏布局
│   │   │   ├── TransformPage     # 转换页
│   │   │   ├── Menu              # 菜单页
│   │   │   ├── ConfirmPage       # 确认页
│   │   │   └── NoFoundPage       # 404 页
│   │
│   └── util/                     # 页面工具
│       ├── CacheManager          # 缓存管理
│       ├── CubeTrans             # 多维转换
│       └── SplitUtil             # 分页工具
│
├── service/                      # 服务层 (18 类)
│   ├── AppInfoService            # 应用信息服务
│   ├── BrowserInfoService        # 浏览框信息服务
│   ├── FormInfoService           # 表单信息服务
│   ├── ModelInfoService          # 模型信息服务
│   ├── CustomSearchService       # 自定义查询服务
│   ├── CustomSearchButtService   # 查询按钮服务
│   ├── CustomtreeService         # 自定义树服务
│   ├── CustomPageService         # 自定义页面服务
│   ├── ReportInfoService         # 报表信息服务
│   ├── SelectItemPageService     # 选项页服务
│   ├── ExpCardExcelService       # 导出卡片 Excel 服务
│   ├── RemindJobService          # 定时提醒服务
│   ├── RepeatVerifyService       # 重复校验服务
│   ├── ExpandInfoService         # 扩展信息服务
│   ├── LogService                # 日志服务
│   ├── WorkFlowToModeLogService  # 流程→建模日志服务
│   └── CubeChartsService         # 多维图表服务
│
├── data/                         # 数据操作
│   ├── FieldInfo                 # 字段信息
│   ├── FormInfoDao               # 表单 DAO
│   └── ModeDataManager           # 建模数据管理器
│
├── excel/                        # Excel 处理
│   ├── ExcelImportServer         # Excel 导入服务
│   └── ImpExcelReader            # Excel 读取器
│
├── exceldesign/                  # Excel 布局设计
│   └── ParseLayoutToHtml         # Excel → HTML
│
├── cache/                        # 缓存 (20 类)
│   ├── ModeComInfo               # 建模缓存
│   ├── ModeFormComInfo           # 表单缓存
│   ├── ModeBrowserComInfo        # 浏览框缓存
│   ├── ModeRightComInfo          # 权限缓存
│   ├── ModeFieldComInfo          # 字段缓存
│   └── ...
│
├── interfaces/                   # 接口
│   └── ModeManageMenuApi         # 建模管理菜单 API
│
├── model/                        # 数据模型
│   ├── DetailTable               # 明细表模型
│   ├── FieldInfo                 # 字段模型
│   └── TableInfo                 # 表模型
│
├── tree/                         # 树操作
│   └── CustomTreeDataApi         # 自定义树数据 API
│
├── util/                         # 工具类
│   ├── FormmodeDbUtil            # 数据库工具
│   ├── FormmodeUtil              # 建模通用工具
│   └── ModeRightUtil             # 权限工具
│
├── view/                         # 视图
│   ├── ModeDetailImportApi       # 建模详情导入 API
│   └── ResolveFormMode           # 解析建模
│
└── apps/                         # 应用
    ├── cmgl/                     # 采购管理
    ├── lkdj/                     # 快递登记
    └── interfaces/               # 应用接口
```

---

## 五、请求处理流程

### 5.1 建模表单数据查看（列表页）

```
浏览器 → /api/formmode/list
    → FormmodeListAction
        → page/Data (页面路由)
            → impl/Grid 或 impl/SimpleTable (页面类型)
                → simpletable/ModeLayoutAdapter (布局适配)
                    → simpletable/FormFieldAdapter (字段适配)
                        → simpletable/ModeRightAdapter (权限适配)
                            → CardDao / FormDao (MyBatis DAO)
                                → SELECT * FROM uf_xxx WHERE ... (数据库)
                                    ← SplitPageResult (分页结果)
                                        ← JSON 响应
```

### 5.2 建模表单数据编辑（卡片页）

```
浏览器 → /api/formmode/form
    → FormmodeFormAction
        → page/App (页面路由)
            → impl/Card (卡片视图)
                → card/FormBaseAdapter (表单适配)
                    → card/ModeBaseAdapter (建模适配)
                        → CardDao (MyBatis)
                            → SELECT / INSERT / UPDATE uf_xxx
```

### 5.3 建模表单创建（新增）

```
浏览器 → 表单提交
    → FormmodeFormAction
        → page/action/Action
            → ActionProxyHandle (代理)
                → 字段验证 → 权限验证 → 数据插入
                    → FormMapper.addData() (MyBatis, 多数据库适配)
                        → INSERT INTO uf_xxx (columns) VALUES (values)
```

### 5.4 自定义查询

```
浏览器 → /api/formmode/search
    → page/Search (搜索视图)
        → search/CustomSearchAdapter
            → CustomSearchDao (MyBatis)
                → 动态 SQL (用户自定义)
                    → 任意表查询
```

---

## 六、权限体系

建模引擎的权限控制分为 **4 层**：

| 层级 | 类 | 说明 |
|------|-----|------|
| **应用级** | `ModeRightInfo` | 能否访问某个建模应用 |
| **数据级** | `ModeRightInfoExtend`, `ModeRightService` | 能看到哪些数据行（按人/部门/公司过滤） |
| **字段级** | `modefieldauthorize` 表 | 能否查看/编辑某个字段 |
| **按钮级** | `mode_pageExpand` 表 | 能否看到新增/删除/导出按钮 |

权限表达式引擎：
- `ShareExpressions` — 分享规则解析
- `ModeTriggerWorkflowExpressions` — 触发流程规则解析
- `WorkflowToModeExpressions` — 流程转建模规则解析
- `ExpandBaseRightExpressions` — 扩展基础权限解析

---

## 七、MyBatis Mapper SQL 全览

### 11 个 Mapper XML 及其核心查询

| Mapper | 核心方法 | 涉及表 |
|--------|---------|--------|
| `ModeMapper.xml` | `getModeByFormId`, `getLayouts`, `getModeFieldSelectItems` | `modeinfo`, `modeHtmlLayout`, `workflow_billfield`, `modeFormField`, `workflow_selectItem` |
| `FormMapper.xml` | `getDetailTables`, `getFieldSelects`, `addData`, `deleteData`, `getModeCount` | `workflow_billdetailtable`, `workflow_billfield`, `workflow_selectItem`, `modeinfo`, `uf_*` |
| `CardMapper.xml` | 卡片视图查询 | `uf_*` 业务表 |
| `SimpleTableMapper.xml` | 简单表格查询 | `uf_*` 业务表 |
| `CustomSearchMapper.xml` | 自定义查询 | 动态 SQL |
| `TreeMapper.xml` | 树形数据查询 | `uf_*` 业务表 |
| `CustomPageMapper.xml` | 自定义页面 | `mode_custompage`, `cpt_custompage` |
| `ModeRightInfoMapper.xml` | 权限查询 | `modefieldauthorize` |
| `ModeTreeFieldMapper.xml` | 树形字段 | `modeTreeField` |
| `ModeCodeMapper.xml` | 条码/二维码 | `modeinfo` |
| `SplitPageMapper.xml` | 通用分页 | 动态 SQL |

---

## 八、与流程引擎的集成

建模引擎与流程引擎通过 **WorkflowToMode** 机制打通：

```
流程审批通过 → ModeTriggerWorkflowExpressions
    → WorkflowToMode 表达式解析
        → WorkflowToModeAction (interfaces/action/)
            → 读取流程主表 + 明细表数据
                → 写入 uf_* 建模业务表
                    → 记录 WorkFlowToModeLogService
```

关键类：
- `WorkflowToMode` — 流程数据写入建模
- `WorkflowToModeAfter` — 流程审批后处理
- `MealsWorkflowToMode` — 餐饮流程定制
- `RebuildData4Wf2Mode` — 数据重建
- `ModeTriggerWorkflowExpressionBean/...` — 表达式解析

---

## 九、自定义 Java 代码扩展点

### 9.1 src/weaver/formmode/customjavacode/ (26 个 Java 文件)

| 扩展点 | 类 | 作用 |
|--------|-----|------|
| 自定义搜索模板 | `CustomSearchTemplate` | 搜索条件定制 |
| 建模展开动作 | `ModeExpandDWDB`, `ModeExpandYPC*`, `ModeExpandGZC*`... | 数据操作前后的自定义逻辑 |
| 提醒动作 | `MytestRemindAction` | 定时提醒触发 |

### 9.2 src/weaver/formmode/interfaces/impl/ (6 个 Java 文件)

| 接口 | 实现类 | 作用 |
|------|--------|------|
| 自定义按钮显示 | `CustomBtnShowOfCPHS`, `CustomBtnShowOfGZCBM`, `CustomBtnShowOfHYDCOrder`, `CustomBtnShowOfJM` | 控制按钮可见性 |
| 导入字段转换 | `ImportFieldTransOfpxjh` | Excel 导入时的字段转换 |
| 导入校验 | `ImportValidateOfpxjh` | Excel 导入时的数据校验 |

### 9.3 com.api.formmode/interfaces/impl/ (预编译 5 类)

| 类 | 作用 |
|---|------|
| `CustomBtnShowOfCPHS` | 车辆牌号为自定义按钮 |
| `CustomBtnShowOfGZCBM` | 工作餐部门自定义按钮 |
| `CustomBtnShowOfHYDCOrder` | 浩源订单自定义按钮 |
| `ImportFieldTransOfpxjh` | 培训计划导入字段转换 |
| `ImportValidateOfpxjh` | 培训计划导入校验 |

---

## 十、Web 页面结构 (formmode/ 目录, 655 JSP)

```
formmode/
├── setup/          (214 JSP) — 最大模块：建模配置页面
│   ├── ModeSettings.jsp      — 建模设置
│   ├── ModeManage.jsp        — 建模管理
│   ├── ModeRightSet.jsp      — 权限设置
│   ├── ModeBasic.jsp         — 基础配置
│   ├── RemindJobSettings.jsp — 定时任务配置
│   └── LayoutEdit.jsp        — 布局编辑
│
├── interfaces/     (65 JSP)  — 接口配置页面
├── menu/           (54 JSP)  — 菜单管理
├── exceldesign/    (54 JSP)  — Excel 布局设计页面
├── view/           (42 JSP)  — 视图页面
├── search/         (36 JSP)  — 搜索/查询页面
├── cuspage/        (29 JSP)  — 自定义页面
├── tree/           (28 JSP)  — 树形导航页面
├── apps/           (22 JSP)  — 应用页面 (ktree/Invitation)
├── browser/        (19 JSP)  — 浏览框/数据列表页面
├── exttools/       (15 JSP)  — 外部工具（导入导出）
├── report/         (13 JSP)  — 报表页面
├── template/       (9 JSP)   — 模板页面
├── batchoperate/   (6 JSP)   — 批量操作
├── charts/         (6 JSP)   — 图表页面
├── form/           (8 JSP)   — 表单渲染页面
├── import/         (5 JSP)   — 导入页面
├── custompage/     (5 JSP)   — 自定义页面视图
├── data/           (5 JSP)   — 数据页面
│
├── pub.jsp                    — 公共包含文件
├── pub_init.jsp               — 初始化公共文件
├── pub_detach.jsp             — 分离公共文件
└── pub_function.jsp           — 函数公共文件
```

---

## 十一、关键数字汇总

| 指标 | 数值 |
|------|------|
| weaver.formmode.* class 数 | 501 |
| com.api.formmode.* class 数 | 277 |
| 管理后台 JSP 数 | 655 |
| MyBatis Mapper XML 数 | 11 |
| MyBatis Bean 类数 | 23 |
| MyBatis DAO 类数 | 9 |
| 页面适配器类数 | 80+ |
| 页面组件类数 | 30+ |
| 页面实现类数 | 14 |
| 自定义 Java 扩展文件数 | 26 |
| 核心配置表数 | ~15 |
| 业务表前缀 | `uf_` |
| 缓存类数 | 20 |
| 服务类数 | 18 |
| Excel 布局设计类数 | 16 |
| 定时任务类数 | 34 |
| 外部接口类数 | 49 |
