# 流程钩子编码规范

> 规范泛微 e-cology 流程引擎钩子函数（Action）的编写。

---

## 1. 类结构规范

### 1.1 继承与包名

```java
package com.engine.interfaces.sj.zhongda.action.aiauto;

import com.engine.interfaces.sj.zhongda.action.ZDAbstractAction;
import weaver.soa.workflow.request.RequestInfo;

public class XxxAction extends ZDAbstractAction {

    @Override
    public String execute(RequestInfo requestInfo) {
        // 成功返回 "1"，失败返回 "0"
    }
}
```

| 要素 | 规范 |
|------|------|
| 基类 | `com.engine.interfaces.sj.zhongda.action.ZDAbstractAction` |
| 包名 | `com.engine.interfaces.sj.zhongda.action.aiauto`（固定） |
| 实现方法 | `String execute(RequestInfo requestInfo)` |
| 返回值 | `"1"` 成功，`"0"` 失败 |

### 1.2 ZDAbstractAction 封装方法

| 方法 | 用途 | 示例 |
|------|------|------|
| `getOaMainMap(MainTableInfo)` | 主表数据转 Map | `Map<String, String> mainMap = getOaMainMap(requestInfo.getMainTableInfo());` |
| `getDetailList(RequestInfo, int index)` | 明细表转 List<Map>（index 从 1 开始） | `List<Map<String, String>> detailList = getDetailList(requestInfo, 1);` |
| `handleException(Map<String, Object> result)` | 统一异常处理（status="1" 成功，否则抛异常） | `handleException(result);` |

---

## 2. RequestInfo 常用方法

| 方法 | 用途 |
|------|------|
| `getRequestid()` | 流程实例 ID |
| `getWorkflowid()` | 流程定义 ID |
| `getMainTableInfo()` | 主表信息 |
| `getDetailTableInfo()` | 明细表信息 |
| `getRequestManager().setMessagecontent(msg)` | 设置错误消息（失败时必须调用） |
| `getCreatorid()` | 创建人 ID |
| `getLastoperator()` | 最后操作人 |

---

## 3. 流程数据取值

### 3.1 主表取值

```java
MainTableInfo mainTableInfo = requestInfo.getMainTableInfo();
Map<String, String> mainMap = getOaMainMap(mainTableInfo);
String xm = mainMap.get("xm");      // 姓名
String ssdjId = mainMap.get("ssdj"); // 宿舍登记（存的是关联记录 ID）
```

### 3.2 明细表取值

```java
List<Map<String, String>> detailList = getDetailList(requestInfo, 1); // index 从 1 开始
for (Map<String, String> row : detailList) {
    String field1 = row.get("field1");
    String field2 = row.get("field2");
}
```

### 3.3 流程表名查询

用户通常提供流程名称，需要先查出 formid 再拼接表名：

```java
// 1. 根据流程名称模糊查询
RecordSet rs = new RecordSet();
rs.executeQuery("SELECT id, formid FROM workflow_base WHERE workflowname LIKE '%凭票%' AND isvalid=1");

if (rs.next()) {
    String workflowId = rs.getString("id");
    int formid = Math.abs(rs.getInt("formid")); // 注意：formid 可能是负数，取绝对值

    // 2. 拼接表名
    String mainTable = "formtable_main_" + formid;        // 主表
    String detailTable1 = mainTable + "_dt1";             // 明细表1
    String detailTable2 = mainTable + "_dt2";             // 明细表2
}
```

### 3.4 流程元数据查询

流程相关表结构：

| 表名 | 用途 |
|------|------|
| `workflow_base` | 流程基本信息（workflowname, formid, isvalid 等） |
| `workflow_bill` | 流程表单信息（tablename, namelabel 等） |
| `workflow_billfield` | 表单字段信息（fieldname, fieldlabel, fielddbtype 等） |
| `HtmlLabelInfo` | 多语言标签（indexid, labelname, languageid） |

**查询流程表单字段名称和标签**：

```sql
SELECT f.fieldname, l.labelname
FROM workflow_billfield f
JOIN HtmlLabelInfo l ON f.fieldlabel = l.indexid
JOIN workflow_bill b ON f.billid = b.id
WHERE b.tablename = 'formtable_main_273'
AND l.languageid = 7  -- 7=中文
```

**查询流程名称和表单表名**：

```sql
SELECT w.workflowname, b.tablename
FROM workflow_base w
JOIN workflow_bill b ON w.formid = b.id * -1  -- formid 通常是负数
WHERE w.workflowname LIKE '%录用%'
AND w.isvalid = 1
```

---

## 4. 数据库操作

### 4.1 RecordSet（常用）

```java
RecordSet rs = new RecordSet();

// 查询
rs.executeQuery("SELECT * FROM uf_xxx WHERE id=?", id);
if (rs.next()) {
    String value = rs.getString("fieldName");
    int count = rs.getInt("countField");
}

// 更新/插入/删除
rs.executeUpdate("UPDATE uf_xxx SET field1=? WHERE id=?", value, id);
```

### 4.2 RecordSetTrans（事务）

```java
RecordSetTrans rs = new RecordSetTrans();
try {
    // 业务逻辑
    rs.executeUpdate("INSERT INTO uf_xxx ...");
    rs.executeUpdate("UPDATE uf_yyy ...");
    rs.commit();  // 成功后提交
    return "1";
} catch (Exception e) {
    rs.rollback();  // 异常时回滚
    requestInfo.getRequestManager().setMessagecontent("错误: " + e.getMessage());
    log.error("操作失败", e);
    return "0";
}
```

### 4.3 RecordSetDataSource（其它数据源）

```java
// 连接非默认数据源
RecordSetDataSource rs = new RecordSetDataSource("datasourceName");
rs.executeQuery("SELECT * FROM table_name");
```

### 4.4 建模引擎表单插入规范

往建模引擎创建的表单（`uf_` 开头的表）插入数据时，**必须查询正确的 formmodeid**，禁止硬编码。

**查询 formmodeid**：

```sql
-- 根据表名查询 formmodeid
SELECT id, modename FROM modeinfo WHERE id IN (
    SELECT DISTINCT formmodeid FROM uf_xxx WHERE formmodeid > 0
)

-- 或者直接查现有记录
SELECT DISTINCT formmodeid FROM uf_xxx WHERE formmodeid > 0
```

**插入时必须包含 formmodeid**：

```java
// 正确：动态查询 formmodeid
rs.executeQuery("SELECT DISTINCT formmodeid FROM uf_lzryxxb WHERE formmodeid > 0");
int formmodeid = 0;
if (rs.next()) {
    formmodeid = rs.getInt("formmodeid");
}

String insertSql = "INSERT INTO uf_lzryxxb (..., formmodeid, ...) VALUES (..., ?, ...)";
rs.executeUpdate(insertSql, ..., formmodeid, ...);

// 错误：硬编码 formmodeid
String insertSql = "INSERT INTO uf_lzryxxb (...) VALUES (..., 1152, ...)";  // 禁止！
```

---

## 5. 异常处理

### 5.1 标准模式

```java
@Override
public String execute(RequestInfo requestInfo) {
    RecordSet rs = new RecordSet();

    try {
        // 业务逻辑
        MainTableInfo mainTableInfo = requestInfo.getMainTableInfo();
        Map<String, String> mainMap = getOaMainMap(mainTableInfo);

        // ... 处理逻辑

        log.info("操作成功 - requestId=" + requestInfo.getRequestid());
        return "1";

    } catch (Exception e) {
        String errorMsg = "操作失败: " + e.getMessage();
        log.error(errorMsg, e);
        requestInfo.getRequestManager().setMessagecontent(errorMsg);
        return "0";
    }
}
```

### 5.2 关键规则

| 规则 | 说明 |
|------|------|
| 失败必须返回 `"0"` | 流程引擎据此判断钩子执行结果 |
| 失败必须设置错误消息 | `requestInfo.getRequestManager().setMessagecontent(msg)` |
| 必须记录日志 | 使用 `log.error()` 记录异常堆栈 |
| 事务必须回滚 | 使用 RecordSetTrans 时，异常分支必须 `rollback()` |

---

## 6. 日志规范

```java
import weaver.integration.logging.Logger;
import weaver.integration.logging.LoggerFactory;

public class XxxAction extends ZDAbstractAction {
    private static final Logger log = LoggerFactory.getLogger(XxxAction.class);

    // 使用
    log.info("信息日志");
    log.warn("警告日志");
    log.error("错误日志", exception);
}
```

---

## 7. 强制规则

### 7.1 数据库查询

**查询流程/表结构信息时，必须通过 MCP Server 连接数据库，禁止其他方式。**

### 7.2 SQL 规范

- 优先使用参数化查询（`?` 占位符）
- 字符串拼接时必须处理 null 和特殊字符
- 禁止在循环中执行大量单条 SQL（考虑批量操作）

### 7.3 代码规范

- 必须记录关键操作日志
- 必须进行空值检查
- 必须进行异常处理
- 事务操作必须 try-catch-finally

---

## 8. 完整示例

```java
package com.engine.interfaces.sj.zhongda.action.aiauto;

import com.engine.interfaces.sj.zhongda.action.ZDAbstractAction;
import weaver.conn.RecordSet;
import weaver.integration.logging.Logger;
import weaver.integration.logging.LoggerFactory;
import weaver.soa.workflow.request.MainTableInfo;
import weaver.soa.workflow.request.RequestInfo;

import java.util.Map;

/**
 * 示例钩子：流程归档前同步数据
 */
public class SampleSyncAction extends ZDAbstractAction {

    private static final Logger log = LoggerFactory.getLogger(SampleSyncAction.class);

    @Override
    public String execute(RequestInfo requestInfo) {
        RecordSet rs = new RecordSet();

        try {
            // 1. 获取主表数据
            MainTableInfo mainTableInfo = requestInfo.getMainTableInfo();
            Map<String, String> mainMap = getOaMainMap(mainTableInfo);
            String requestId = requestInfo.getRequestid();

            // 2. 获取流程字段
            String xm = mainMap.get("xm");      // 姓名
            String bm = mainMap.get("bm");      // 部门

            if (xm == null || xm.trim().isEmpty()) {
                log.warn("姓名为空，requestId=" + requestId);
                return "0";
            }

            // 3. 业务逻辑
            rs.executeUpdate("INSERT INTO uf_sync_log (requestId, xm, bm, syncTime) VALUES (?, ?, ?, GETDATE())",
                    requestId, xm, bm);

            log.info("同步成功 - requestId=" + requestId + ", xm=" + xm);
            return "1";

        } catch (Exception e) {
            String errorMsg = "同步失败: " + e.getMessage();
            log.error(errorMsg, e);
            requestInfo.getRequestManager().setMessagecontent(errorMsg);
            return "0";
        }
    }
}
```
