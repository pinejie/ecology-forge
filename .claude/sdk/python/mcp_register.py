# -*- coding: utf-8 -*-
"""
泛微二开 MCP 自动注册机制

SDK 开发者只需：
1. 在方法上加 @expose 装饰器
2. mcp_server.py 调用 auto_register(mcp) 即可自动注册

使用示例：
    # 在 SDK 文件中
    from mcp_register import expose

    class MySDK:
        @expose(
            description="创建应用",
            examples=[{"name": "测试"}]
        )
        def create_app(self, name: str, parent_id: int = 0) -> int:
            ...

    # 在 mcp_server.py 中
    from mcp_register import auto_register
    mcp = FastMCP("weaver_oa_mcp")
    auto_register(mcp)
"""

import importlib
import inspect
import json
import os
import pkgutil
from functools import wraps
from typing import Optional, List, Dict, Any, get_type_hints

from pydantic import BaseModel, Field, ConfigDict, create_model
from mcp.server.fastmcp import FastMCP

# 全局注册表：{method_name: {"sdk_class": cls, "method": fn, "meta": {...}}}
_REGISTRY = {}


def expose(
    description: str = "",
    examples: Optional[List[Dict]] = None,
    error_hints: Optional[Dict[str, str]] = None,
    read_only: bool = False,
    destructive: bool = False,
):
    """
    标记 SDK 方法为 MCP tool，供 auto_register 自动发现。

    :param description: tool 功能描述（用于 MCP tool description）
    :param examples: 使用示例列表，每个示例是一个参数字典
    :param error_hints: 错误提示映射 {错误关键词: 用户友好提示}
    :param read_only: 是否只读操作
    :param destructive: 是否破坏性操作
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        _REGISTRY[fn.__name__] = {
            "method": wrapper,
            "original": fn,
            "description": description,
            "examples": examples or [],
            "error_hints": error_hints or {},
            "read_only": read_only,
            "destructive": destructive,
        }
        return wrapper
    return decorator


def _build_input_model(fn, meta: Dict) -> type[BaseModel]:
    """
    从方法签名和 docstring 动态生成 Pydantic Input 模型。
    """
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    doc = inspect.getdoc(fn) or ""

    # 解析 docstring 中的 :param 行
    param_docs = {}
    for line in doc.split("\n"):
        line = line.strip()
        if line.startswith(":param "):
            # :param name: 描述
            parts = line[len(":param "):].split(":", 1)
            if len(parts) == 2:
                param_name = parts[0].strip()
                param_desc = parts[1].strip()
                param_docs[param_name] = param_desc

    fields = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue

        param_type = hints.get(name, Any)
        has_default = param.default != inspect.Parameter.empty
        default_val = param.default if has_default else ...

        # 从 :param doc 提取描述，否则用参数名
        desc = param_docs.get(name, f"{name} 参数")

        # 根据类型加约束
        field_kwargs = {"default": default_val, "description": desc}
        if param_type is int and has_default and isinstance(default_val, int):
            field_kwargs["ge"] = 0 if default_val >= 0 else None
        elif param_type is str and not has_default:
            field_kwargs["min_length"] = 1

        fields[name] = (param_type, Field(**{k: v for k, v in field_kwargs.items() if v is not None}))

    # 动态创建 Pydantic 模型
    model_name = f"{fn.__name__}_Input"
    return create_model(
        model_name,
        __config__=ConfigDict(str_strip_whitespace=True, validate_assignment=True),
        **fields
    )


def _build_tool_description(fn, meta: Dict) -> str:
    """生成 tool 的 description（给 AI 看的）。"""
    doc = inspect.getdoc(fn) or ""
    desc = meta.get("description", "")
    examples = meta.get("examples", [])

    parts = [desc] if desc else [doc.split("\n")[0] if doc else fn.__name__]

    # 添加参数说明
    sig = inspect.signature(fn)
    param_parts = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        has_default = param.default != inspect.Parameter.empty
        req = "必填" if not has_default else f"默认 {param.default}"
        param_parts.append(f"  - {name}: {req}")

    if param_parts:
        parts.append("参数：")
        parts.extend(param_parts)

    # 添加示例
    if examples:
        parts.append("示例：")
        for ex in examples:
            parts.append(f"  {json.dumps(ex, ensure_ascii=False)}")

    # 添加错误提示
    error_hints = meta.get("error_hints", {})
    if error_hints:
        parts.append("错误处理：")
        for condition, hint in error_hints.items():
            parts.append(f"  - {condition} → {hint}")

    return "\n".join(parts)


def _create_sdk_instances(sdk_classes: Dict[str, Any]) -> Dict[str, Any]:
    """
    延迟创建 SDK 实例——在 handler 被调用时才创建。
    这样 mcp_server.py 导入时不需要数据库密码。
    """
    from db_config import load_db_config

    try:
        defaults = load_db_config()
    except Exception:
        defaults = {}

    host = defaults.get("host")
    user = defaults.get("user")
    password = defaults.get("password")
    database = defaults.get("database")

    if not password:
        return {}  # 启动时不报错，调用时再检查

    instances = {}
    for class_name, cls in sdk_classes.items():
        try:
            instances[class_name] = cls(
                host=host, user=user, password=password, database=database
            )
        except Exception as e:
            print(f"[mcp_register] 警告: 创建 {class_name} 实例失败: {e}")

    return instances


def _get_sdk_classes():
    """
    扫描 SDK 模块，找到所有带 @expose 标记的类。
    """
    sdk_classes = {}
    sdk_dir = os.path.dirname(__file__)

    for importer, modname, ispkg in pkgutil.iter_modules([sdk_dir]):
        if modname in ("mcp_register", "mcp_server", "demo") or modname.startswith("_"):
            continue

        try:
            mod = importlib.import_module(modname)
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if inspect.isclass(attr):
                    # 检查这个类是否有带 @expose 的方法
                    has_exposed = False
                    for method_name in dir(attr):
                        if method_name.startswith("_"):
                            continue
                        method = getattr(attr, method_name)
                        if method_name in _REGISTRY:
                            reg = _REGISTRY[method_name]
                            # 检查是否是这个类的方法
                            if reg.get("original") and hasattr(attr, reg["original"].__name__):
                                has_exposed = True
                                break
                    if has_exposed:
                        sdk_classes[attr_name] = attr
        except Exception as e:
            print(f"[mcp_register] 警告: 加载模块 {modname} 失败: {e}")

    return sdk_classes


def auto_register(mcp: FastMCP):
    """
    自动扫描 SDK 模块，将所有 @expose 标记的方法注册为 MCP tool。
    在 mcp_server.py 中调用一次即可。
    """
    # 1. 找到所有 SDK 类
    sdk_classes = _get_sdk_classes()
    if not sdk_classes:
        print("[mcp_register] 未找到带 @expose 标记的 SDK 类")
        return

    # 2. 创建 SDK 实例（一次创建，多次复用）
    sdk_instances = _create_sdk_instances(sdk_classes)

    # 3. 注册每个 @expose 方法
    registered_count = 0
    for method_name, meta in _REGISTRY.items():
        original_fn = meta["original"]
        # 找到这个方法属于哪个 SDK 类
        owner_class = None
        for class_name, cls in sdk_classes.items():
            if hasattr(cls, original_fn.__name__):
                owner_class = cls
                break

        if owner_class is None:
            continue

        class_name = owner_class.__name__

        # 生成 tool 名（加类前缀避免冲突）
        prefix = class_name.replace("SDK", "").lower()
        full_tool_name = f"{prefix}_{method_name}"

        # 构建 Input 模型和 handler
        input_model = _build_input_model(original_fn, meta)
        description = _build_tool_description(original_fn, meta)

        # 生成 annotations
        annotations = {
            "title": meta.get("description", method_name),
            "readOnlyHint": meta["read_only"],
            "destructiveHint": meta["destructive"],
            "idempotentHint": not meta["destructive"],
            "openWorldHint": False
        }

        # 动态创建 handler（延迟创建 SDK 实例）
        def make_handler(class_name, method_name):
            async def handler(params: input_model) -> str:
                try:
                    # 延迟创建实例（调用时才创建）
                    instances = _create_sdk_instances(sdk_classes)
                    if class_name not in instances:
                        return json.dumps({
                            "status": "-1",
                            "message": "数据库连接未配置，请在 db-config.md 中配置"
                        }, ensure_ascii=False, indent=2)

                    instance = instances[class_name]
                    method = getattr(instance, method_name)
                    kwargs = params.model_dump()
                    result = method(**kwargs)
                    return json.dumps({
                        "status": "1",
                        "data": result if not isinstance(result, int) else {"id": result},
                        "message": "成功"
                    }, ensure_ascii=False, indent=2)
                except Exception as e:
                    return json.dumps({
                        "status": "-1",
                        "message": str(e)
                    }, ensure_ascii=False, indent=2)
            return handler

        handler = make_handler(class_name, original_fn.__name__)
        handler.__doc__ = description
        handler.__name__ = full_tool_name

        # 注册到 MCP
        mcp.tool(name=full_tool_name, annotations=annotations)(handler)
        registered_count += 1
        print(f"[mcp_register] 已注册 tool: {full_tool_name}")

    print(f"[mcp_register] 共注册 {registered_count} 个 tool")
