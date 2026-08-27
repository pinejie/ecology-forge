# e-cology 9 OA 系统知识图谱

> 生成时间：2026-07-03
> 扫描范围：`classbean/` (35,990 个 class)、`src/` (195 个 java)、`WEB-INF/web.xml`
> 系统版本：泛微 e-cology 9

---

## 一、系统架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        浏览器 / 移动端                        │
└──────────────┬──────────────────────────────┬────────────────┘
               │                              │
┌──────────────▼──────────────────────────────▼────────────────┐
│                    Resin 应用服务器                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Filter 链 (15+ 个过滤器)                                │  │
│  │  Encoding → SecurityTrans → Sensitive → SSO →          │  │
│  │  SessionCloud → Security → Compress → Spring →         │  │
│  │  IECompatible → ConnFast → MultiLang → Dialog →        │  │
│  │  Static → LN → Init → FileNaming → DateFormat          │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ Jersey REST  │ │ Struts 1 │ │  DWR     │ │ 自定义     │  │
│  │ /api/*       │ │ /upload  │ │ /dwr/*   │ │ Servlets   │  │
│  │ (com.sun.)   │ │ (Struts) │ │ (uk.ltd) │ │ (20+ 个)   │  │
│  └──────┬───────┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘  │
│         │              │            │             │          │
│  ┌──────▼──────────────▼────────────▼─────────────▼──────┐  │
│  │           业务逻辑层 (weaver.* / com.api.* /           │  │
│  │            com.engine.* / classbean.jar)               │  │
│  └──────────────────────────┬────────────────────────────┘  │
│                             │                               │
│  ┌──────────────────────────▼────────────────────────────┐  │
│  │         数据访问层 (weaver.conn.RecordSet / Proxool)   │  │
│  └──────────────────────────┬────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │ Oracle / SQL Server│
                    └───────────────────┘
```

## 二、三层代码分层

e-cology 9 后端代码分为 **三层包**，层层递进：

| 层 | 包前缀 | 作用 | class 占比 |
|----|--------|------|-----------|
| **核心框架层** | `weaver.*` | 底层基础设施，含所有业务模块的核心实现 | ~60% |
| **业务引擎层** | `com.engine.*` | 二次封装的业务引擎，提供标准 biz/cmd/service/web | ~25% |
| **API 暴露层** | `com.api.*` | REST API 入口，JAX-RS 路由，调用引擎层 | ~10% |
| **定制开发层** | `src/` 下的 Java | 客户定制代码，覆盖上述三层 | 自定义 |

### 请求流转路径

```
HTTP 请求 → Filter 链 → Jersey (/api/*) → com.api.xxx.web.XxxAction
                                              → com.engine.xxx.biz.XxxService
                                                  → com.engine.xxx.cmd.XxxCmd
                                                      → weaver.xxx.* (核心实现)
                                                          → weaver.conn.RecordSet (数据库)
```

## 三、应用模块全景

### 3.1 核心业务模块 (weaver.* 层，按 class 数量排序)

| 模块 | 包名 | Class 数 | 子包(功能域) | Web 目录 |
|------|------|----------|-------------|---------|
| **工作流** | `weaver.workflow` | 755 | action/ agent/ bean/ browser/ design/ exceldesign/ form/ imports/ job/ layout/ mode/ monitor/ msg/ node/ qiyuesuo/ | `workflow/` |
| **人力资源** | `weaver.hrm` | 731 | attendance/ authority/ career/ chart/ contract/ definedfield/ excelimport/ finance/ group/ job/ loginstrategy/ mapper/ online/ orggroup/ | `hrm/` |
| **前端页面** | `weaver.page` | 529 | interfaces/ element/ wgd/ workflow/ | — |
| **财务管理** | `weaver.fna` | 507 | bankEnterpriseConnect/ budget/ costStandard/ encrypt/ elements/ exceldesign/ fnaVoucher/ interfaces/ invoice/ maintenance/ report/ | `fna/` |
| **表单引擎** | `weaver.formmode` | 501 | apps/ browser/ charts/ cuspage/ customjavacode/ data/ datainput/ esb/ excel/ expcard/ interfaces/ manager/ modesetdelete/ quartz/ report/ search/ setup/ | `formmode/` |
| **安全框架** | `weaver.security` | 361 | access/ agentRules/ boot/ classLoader/ core/ encryptedtrans/ encryption_alg/ esapi/ filter/ ip2region/ rsa/ rules/ sensitive/ validators/ | `security/` |
| **集成平台** | `weaver.integration` | 323 | — | `integration/` |
| **接口中心** | `weaver.interfaces` | 283 | — | `interface/` |
| **移动端** | `weaver.mobile` | 252 | ding/ plugin/ rong/ sign/ webservices/ | `mobile/` |
| **通用基础** | `weaver.general` | 240 | — | — |
| **文档管理** | `weaver.docs` | 239 | bookmark/ category/ change/ convert/ docmark/ docpile/ docpreview/ mail/ mould/ networkdisk/ news/ office/ pdf/ recycle/ report/ search/ senddoc/ share/ transfer/ | `docs/` |
| **合同管理** | `weaver.contractmanagement` | 189 | action/ annotation/ browser/ dao/ entity/ image/ ooxml/ service/ servlet/ | `contractmanagement/` |
| **邮件系统** | `weaver.email` | 148 | domain/ externalmail/ mime/ po/ search/ sequence/ service/ timer/ webservice/ | `email/` |
| **模板检查** | `weaver.templetecheck` | 143 | — | `templetecheck/` |
| **开放平台** | `weaver.ofs` | 123 | — | — |
| **会议管理** | `weaver.meeting` | 109 | action/ defined/ middlePlatform/ organization/ qrcode/ remind/ search/ service/ sync/ video/ webservices/ | `meeting/` |
| **过滤器** | `weaver.filter` | 105 | — | — |
| **备份** | `weaver.backup` | 103 | — | — |
| **组件** | `weaver.cpt` | 101 | barcode/ capital/ car/ job/ maintenance/ report/ search/ util/ wfactions/ | `cpt/` |
| **WPS** | `weaver.wps` | 100 | — | — |
| **SOA** | `weaver.soa` | 98 | — | — |
| **工作计划** | `weaver.WorkPlan` | 95 | — | — |
| **数据库连接** | `weaver.conn` | 89 | — | — |
| **系统** | `weaver.system` | 83 | — | `system/` |
| **文件** | `weaver.file` | 81 | — | — |
| **微信** | `weaver.wechat` | 77 | — | `wechat/` |
| **CRM** | `weaver.crm` | 76 | customer/ sellchance/ investigate/ report/ search/ Maint/ ExcelToDB/ card/ util/ | `CRM/` |
| **短信** | `weaver.sms` | 68 | — | `sms/` |
| **系统信息** | `weaver.systeminfo` | 62 | databasemanage/ role/ setting/ sysadmin/ systemright/ workflowbill/ | `systeminfo/` |
| **监控** | `weaver.monitor` | 62 | — | `monitorX-flag/` |
| **社交** | `weaver.social` | 61 | — | `social/` |
| **项目管理** | `weaver.proj` | 59 | — | `proj/` |
| **通用** | `weaver.common` | 58 | — | `common/` |
| **首页** | `weaver.homepage` | 51 | — | `homepage/` |
| **会话** | `weaver.session` | 45 | — | — |
| **门户** | `weaver.portal` | 44 | bean/ cache/ checking/ entity/ init/ job/ mapper/ | `portal/` |
| **全文搜索** | `weaver.fullsearch` | 38 | base/ bean/ common/ dao/ filter/ interfaces/ model/ util/ | `fullsearch/` |

### 3.2 业务引擎模块 (com.engine.* 层)

| 引擎模块 | 子模块(biz层) | 说明 |
|---------|--------------|------|
| `com.engine.core` | cfg/ context/ interceptor/ util/ | 核心引擎上下文、拦截器 |
| `com.engine.esb` | bean/ browser/ cmd/ service/ util/ | 企业服务总线，集成外部系统 |
| `com.engine.workflow` | biz/ cmd/ job/ service/ web/ | 工作流引擎封装 |
| `com.engine.kq` | bean/ biz/ cmd/ entity/ enums/ service/ timer/ wfset/ web/ | 考勤引擎 |
| `com.engine.hrm` | biz/ browser/ cmd/ entity/ enums/ service/ util/ web/ | 人力资源引擎 |
| `com.engine.fna` | biz/ cmd/ entity/ service/ systemBill/ util/ web/ | 财务引擎 |
| `com.engine.crm` | biz/ cmd/ dao/ entity/ job/ manage/ service/ thread/ util/ web/ | CRM 引擎 |
| `com.engine.edc` | biz/ cmd/ common/ dao/ entity/ job/ service/ util/ web/ | 电子数据采集引擎 |
| `com.engine.portal` | biz/ cmd/ entity/ service/ util/ web/ | 门户引擎 |

### 3.3 REST API 模块 (com.api.* 层)

| API 模块 | 路径前缀 | 控制器数 | 说明 |
|---------|---------|---------|------|
| `com.api.hrm` | `/api/hrm/` | 5 | 人力资源 API |
| `com.api.gzc` | `/api/gzc/` | 1 | 工作餐 API |
| `com.api.cw` | `/api/cw/` | 3 | 财务 API |
| `com.api.hydc` | `/api/hydc/` | 1 | 浩源地产定制 API |
| `com.api.kq` | `/api/kq/` | 2 | 考勤 API |
| `com.api.px` | `/api/px/` | 3 | 培训 API |
| `com.api.ss` | `/api/ss/` | 2 | 宿舍后勤 API |
| `com.api.workflow` | `/api/workflow/` | 1 | 工作流 API |
| `com.api.mw` | `/api/mw/` | 1 | 微工作流 API |
| `com.api.browser` | `/api/browser/` | — | 浏览器数据浏览 |
| `com.api.cache` | `/api/cache/` | 1 | 缓存管理 |
| `com.api.login` | — | — | 登录工具 |

### 3.4 其他重要模块

| 模块 | 包名 | 说明 |
|------|------|------|
| 云商店 | `com.cloudstore` | 应用市场、ecode 编码、移动端插件 |
| 定制化 | `com.customization` | 客户定制代码 (cube/esb/meeting/workflow) |
| 第三方集成 | `com.engine.interfaces` | 外部系统对接 (中达/新中大/滴滴等) |
| 薪资 | `com.engine.payroll` | 薪资计算引擎 |
| 个人所得税 | `com.engine.personalIncomeTax` | 个税计算 |
| 报表 | `com.engine.report` | 统一报表引擎 |
| 投票 | `com.engine.voting` | 投票系统 |
| 消息中心 | `com.engine.msgcenter` | 消息推送中心 |
| 加密 | `com.engine.encrypt` | 数据加密引擎 |
| License | `com.engine.license` | 许可证管理 |
| 安全敏感 | `com.engine.sensitive` | 敏感词检测 |
| 文档交换 | `com.engine.odoc` | 公文交换 |

## 四、请求处理链路详解

### 4.1 Filter 执行顺序

```
1. EncodingFilterWeaver     — GBK 编码过滤
2. SecurityTransFilter      — 安全传输加密
3. CheckSensitiveFilter     — 敏感词检测
4. WeaSsoIocComponentFilter — SSO + IOC 组件 (/api/*, *.jsp, *.html)
5. EMFilter                 — 移动设备过滤
6. SessionCloudFilter       — 会话验证 (/api/*)
7. SecurityFilter           — 安全检查
8. Compress (WGzipFilter)   — 响应压缩 (.js/.css/.jsp)
9. encodingFilter (Spring)  — UTF-8 编码
10. IECompatibleFilter      — IE 兼容
11. ConnFastFilter          — 连接池快速通道
12. MultiLangFilter         — 多语言
13. DialogHandleFilter      — 弹窗处理
14. WStatic                 — 静态资源缓存
15. resin-ln (LNFilter)     — Resin 日志
```

### 4.2 Servlet 路由映射

| 路由 | Servlet | 说明 |
|------|---------|------|
| `/api/*` | `restservlet` (Jersey) | REST API，扫描 `com.cloudstore;com.api` 包 |
| `/dwr/*` | `dwr-invoker` (DWRServlet) | 远程 JavaScript 调用 |
| `/services/*` | `XFireServlet` | Web Services (XFire) |
| `/rest/*` | `RestDispatcherServlet` | 旧版 REST |
| `/weaver/*` | 20+ 自定义 Servlet | 文件下载、验证码、条码等 |
| `/mobilemode/api/*` | `MobilemodeApiServlet` | 移动端 API |
| `/edc/formview/*` | `EdcFormViewServlet` | EDC 表单视图 |
| `/HeartBeat` | `HeartBeat` | 心跳检测 |

### 4.3 启动初始化

| 初始化组件 | load-on-startup | 说明 |
|-----------|-----------------|------|
| `InitServer` | 1 | 系统启动初始化，serverName=ecology |
| `WeaIocInitServlet` | 1 | IOC 容器初始化 |
| `dwr-invoker` | 1 | DWR 初始化 |
| `CloudStoreInit` | 3 | 云商店初始化 |
| `EcodeInit` | 1 | 编码系统初始化 |

## 五、模块间依赖关系

```
com.api.* (REST Controllers)
    │
    ├── calls → com.engine.* (Business Engine)
    │              │
    │              ├── calls → weaver.* (Core Framework)
    │              │              │
    │              │              ├── weaver.conn (Database)
    │              │              ├── weaver.general (Utils)
    │              │              ├── weaver.hrm (User/Permission)
    │              │              └── weaver.security (Security)
    │              │
    │              └── calls → com.engine.interfaces (External Integration)
    │
    └── calls → weaver.* directly (for core operations)

com.engine.interfaces (Integration Layer)
    ├── 中达 (zhongda) — 财务/考勤/会议同步
    ├── 新中大 (xzz) — 滴滴出行集成
    └── 外部系统通过 SAP/ESB 集成
```

## 六、自定义开发代码 (src/)

| 包 | Java 文件数 | 说明 |
|----|-----------|------|
| `com.api.hrm` | 44 | 人力资源定制 (组织/职位/字典/提醒/培训) |
| `com.api.gzc` | 35 | 工作餐管理 (含导出) |
| `com.api.cw` | 34 | 财务定制 (发票/报销/资金) |
| `com.api.kq` | 30 | 考勤定制 (报表/加班) |
| `com.api.hydc` | 23 | 浩源地产定制 |
| `com.api.px` | 9 | 培训管理 (含签到/二维码) |
| `com.api.ss` | 9 | 宿舍后勤 |
| `com.api.workflow` | 5 | 工作流定制 |
| `com.api.mw` | 5 | 微工作流 |
| `com.engine.kq` | — | 考勤引擎扩展 |
| `com.engine.workflow` | — | 工作流引擎扩展 |
| `com.engine.hr m` | — | 人力资源引擎扩展 |
| `com.engine.interfaces` | — | 外部系统接口定制 |
| `com.engine.fna` | — | 财务引擎扩展 |
| `weaver.formmode` | — | 表单引擎定制代码 |
| `weaver.hrm.pm` | — | 项目管理扩展 |
| `weaver.page` | — | 页面接口定制 |

## 七、关键技术组件

| 技术 | 包/类 | 用途 |
|------|-------|------|
| **JAX-RS (Jersey)** | `com.sun.jersey.*` | REST API 路由 |
| **Struts 1.x** | `org.apache.struts.*` | MVC 框架 (仅升级用) |
| **DWR** | `uk.ltd.getahead.dwr.*` | 前端远程调用 |
| **XFire** | `org.codehaus.xfire.*` | Web Services |
| **FastJSON** | `com.alibaba.fastjson.*` | JSON 序列化 |
| **Proxool** | `org.logicalcobwebs.proxool.*` | 数据库连接池 |
| **Quartz** | `org.quartz.*` | 定时任务 |
| **ESAPI** | `org.owasp.esapi.*` | 安全框架 |
| **Log4j** | `org.apache.log4j.*` | 日志 |
| **Resin** | `com.caucho.*` | 应用服务器 |

## 八、数据库访问

| 组件 | 类 | 说明 |
|------|-----|------|
| 连接池 | `weaver.conn.ConnectionInfo` | Proxool 连接管理 |
| 执行器 | `weaver.conn.RecordSet` | SQL 执行、结果集遍历 |
| 事务 | `weaver.conn.RecordSetTrans` | 事务控制 |
| SQL 升级 | `sqlupgrade/` | 数据库版本升级脚本 |

## 九、外部系统集成

| 集成对象 | 实现方式 | 代码位置 |
|---------|---------|---------|
| SAP | Web Services + ESB | `com.engine.esb.*`, `com.engine.interfaces.sj.zhongda.*` |
| 中达财务 | 定时任务 + 数据同步 | `com.engine.interfaces.sj.zhongda.*` |
| 新中大 | HTTP + 数据推送 | `com.engine.interfaces.xzz.zhongda.*` |
| 滴滴出行 | Job 定时同步 | `com.engine.interfaces.xzz.zhongda.didi.*` |
| RTX | 即时通讯 | `weaver.rtx.*`, `RTX/` 目录 |
| 企微/钉钉 | 移动端插件 | `weaver.mobile.ding.*`, `weaver.weixin.*` |
| 阿里云 OSS | 文件存储 | `weaver.alioss.*` |
| 七牛/金山 | 云存储 | `com.engine.*` |
| 合同锁(契约锁) | Webhook + Servlet | `weaver.workflow.qiyuesuo.*` |
| Office 插件 | DBstep/金格 | `DBstep.*`, `com.goldgrid.*` |
