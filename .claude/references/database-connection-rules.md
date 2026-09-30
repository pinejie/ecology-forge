# 数据库连接规范

> 泛微 e-cology 二次开发中数据库操作的通用规范。  
> 适用于：流程钩子、定时任务、接口开发等所有需要数据库操作的场景。

---

## 1. RecordSet（标准连接）

**用途**：连接 ecology 默认数据库，执行查询和更新操作。

```java
import weaver.conn.RecordSet;

RecordSet rs = new RecordSet();

// 查询
rs.executeQuery("SELECT * FROM uf_xxx WHERE id=?", id);
while (rs.next()) {
    String value = rs.getString("fieldName");
    int count = rs.getInt("countField");
}

// 更新/插入/删除
rs.executeUpdate("UPDATE uf_xxx SET field1=? WHERE id=?", value, id);
rs.executeUpdate("INSERT INTO uf_xxx (field1, field2) VALUES (?, ?)", value1, value2);
rs.executeUpdate("DELETE FROM uf_xxx WHERE id=?", id);
```

**注意事项**：
- 必须使用参数化查询（`?` 占位符），禁止字符串拼接
- 查询后必须调用 `rs.next()` 判断是否有数据
- 使用完毕后无需手动关闭，由系统自动管理

---

## 2. RecordSetTrans（事务连接）

**用途**：需要事务控制时使用，支持手动提交和回滚。

```java
import weaver.conn.RecordSetTrans;

RecordSetTrans rs = new RecordSetTrans();
try {
    // 业务逻辑
    rs.executeUpdate("INSERT INTO uf_xxx ...");
    rs.executeUpdate("UPDATE uf_yyy ...");
    
    rs.commit();  // 成功后提交
    
} catch (Exception e) {
    rs.rollback();  // 异常时回滚
    log.error("操作失败", e);
    throw e;
}
```

**关键规则**：
- 成功必须调用 `commit()`
- 异常必须调用 `rollback()`
- 必须在 try-catch 块中使用

---

## 3. RecordSetDataSource（多数据源连接）

**用途**：连接非默认数据源（如外部数据库、其他系统数据库）。

**重要差异**：RecordSetDataSource 使用 `executeSql()` 方法，不是 `executeQuery()`！

```java
import weaver.conn.RecordSetDataSource;

// 连接外部数据源（注意：使用 executeSql，不是 executeQuery）
RecordSetDataSource rs = new RecordSetDataSource("datasourceName");
rs.executeSql("SELECT * FROM external_table");

while (rs.next()) {
    String value = rs.getString("fieldName");
}
```

**数据源配置**：
- 在 ecology 后台配置数据源：后端维护中心 → 接口管理 → 数据源管理
- 数据源名称在代码中通过字符串引用
- 支持连接 SQL Server、Oracle、MySQL 等

**典型场景**：
- 从外部系统同步数据到 ecology
- 向外部系统推送 ecology 数据
- 跨系统数据查询

---

## 4. 建模引擎表单插入规范

往建模引擎创建的表单（`uf_` 开头的表）插入数据时，**必须动态查询 formmodeid**，禁止硬编码。

### 4.1 查询 formmodeid

```sql
-- 方式1：查询现有记录
SELECT DISTINCT formmodeid FROM uf_xxx WHERE formmodeid > 0

-- 方式2：通过 modeinfo 表查询
SELECT id, modename FROM modeinfo WHERE id IN (
    SELECT DISTINCT formmodeid FROM uf_xxx WHERE formmodeid > 0
)
```

### 4.2 插入时必须包含 formmodeid

**正确示例**：

```java
RecordSet rs = new RecordSet();

// 1. 动态查询 formmodeid
rs.executeQuery("SELECT DISTINCT formmodeid FROM uf_lzryxxb WHERE formmodeid > 0");
int formmodeid = 0;
if (rs.next()) {
    formmodeid = rs.getInt("formmodeid");
}

// 2. 插入时包含 formmodeid
String insertSql = "INSERT INTO uf_lzryxxb (field1, field2, formmodeid) VALUES (?, ?, ?)";
rs.executeUpdate(insertSql, value1, value2, formmodeid);
```

**错误示例**：

```java
// 禁止硬编码 formmodeid！
String insertSql = "INSERT INTO uf_lzryxxb (field1, field2, formmodeid) VALUES (?, ?, 1152)";
rs.executeUpdate(insertSql, value1, value2);
```

**原因**：
- formmodeid 在不同环境（测试/生产）中可能不同
- 硬编码会导致数据迁移后出错
- 动态查询确保环境无关性

---

## 5. 批量操作优化

### 5.1 避免循环中单条操作

**错误示例**：

```java
// 性能差：每条记录单独执行 SQL
for (DataItem item : list) {
    rs.executeUpdate("INSERT INTO uf_xxx (...) VALUES (?, ?, ?)", 
        item.getField1(), item.getField2(), item.getField3());
}
```

**正确示例**：

```java
// 性能好：批量处理
int batchSize = 0;
for (DataItem item : list) {
    rs.executeUpdate("INSERT INTO uf_xxx (...) VALUES (?, ?, ?)", 
        item.getField1(), item.getField2(), item.getField3());
    batchSize++;
    
    // 每 1000 条记录一次日志
    if (batchSize >= 1000) {
        log.info("已处理 " + batchSize + " 条记录");
        batchSize = 0;
    }
}
```

### 5.2 大数据量分批处理

```java
// 分批查询
int pageSize = 1000;
int pageNum = 0;

while (true) {
    String sql = "SELECT * FROM uf_xxx WHERE status=0 ORDER BY id " +
                 "OFFSET " + (pageNum * pageSize) + " ROWS FETCH NEXT " + pageSize + " ROWS ONLY";
    
    rs.executeQuery(sql);
    int count = 0;
    
    while (rs.next()) {
        // 处理数据
        count++;
    }
    
    if (count < pageSize) {
        break;  // 最后一页
    }
    
    pageNum++;
}
```

---

## 6. SQL 规范

### 6.1 参数化查询

**必须使用**：

```java
// 正确：参数化查询
rs.executeQuery("SELECT * FROM uf_xxx WHERE id=? AND name=?", id, name);
```

**禁止使用**：

```java
// 错误：字符串拼接（有 SQL 注入风险）
rs.executeQuery("SELECT * FROM uf_xxx WHERE id=" + id + " AND name='" + name + "'");
```

### 6.2 空值处理

```java
// 查询结果必须判空
rs.executeQuery("SELECT field1 FROM uf_xxx WHERE id=?", id);
if (rs.next()) {
    String value = rs.getString("field1");
    if (value != null && !value.isEmpty()) {
        // 使用 value
    }
}

// 插入时处理 null
String value = (sourceValue == null) ? "" : sourceValue;
rs.executeUpdate("INSERT INTO uf_xxx (field1) VALUES (?)", value);
```

### 6.3 特殊字符处理

```java
// 处理包含特殊字符的字符串
String name = "O'Brien";  // 包含单引号
rs.executeUpdate("INSERT INTO uf_xxx (name) VALUES (?)", name);  // 参数化查询自动处理
```

---

## 7. 强制规则

### 7.1 必须遵守

- ✅ 使用参数化查询（`?` 占位符）
- ✅ 查询结果必须判空
- ✅ 建模引擎表单必须动态查询 formmodeid
- ✅ 事务操作必须 try-catch + rollback
- ✅ 批量操作必须记录进度日志

### 7.2 禁止行为

- ❌ 字符串拼接 SQL（SQL 注入风险）
- ❌ 硬编码 formmodeid
- ❌ 循环中大量单条 SQL（性能问题）
- ❌ 忽略异常处理
- ❌ 忘记事务回滚

---

## 8. 常见问题

### 8.1 连接外部数据库

**问题**：如何连接非 ecology 的数据库？  
**解决**：使用 `RecordSetDataSource`，需在 ecology 后台配置数据源。

### 8.2 formmodeid 查询失败

**问题**：`SELECT DISTINCT formmodeid FROM uf_xxx` 返回空？  
**原因**：表中还没有数据，或者 formmodeid 都是 0。  
**解决**：
1. 先插入一条测试数据，手动指定 formmodeid
2. 或者查询 modeinfo 表获取正确的 formmodeid

### 8.3 事务提交失败

**问题**：`rs.commit()` 报错？  
**原因**：可能是连接已关闭或之前有异常。  
**解决**：确保在 try-catch 块中使用，异常时调用 `rollback()`。

---

**文档版本**：v1.0  
**最后更新**：2026-09-28  
**适用范围**：所有泛微 e-cology 二次开发场景
