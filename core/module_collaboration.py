"""
任务#5: 多模块协同机制
Multi-Module Collaboration Mechanism

实现功能:
1. 模块间消息通信
2. 数据共享总线
3. 协同任务调度
4. 状态同步机制
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Set
from collections import defaultdict
from threading import Lock


class ModuleStatus(str, Enum):
    """模块状态"""
    INITIALIZING = "初始化中"
    READY = "就绪"
    RUNNING = "运行中"
    PAUSED = "暂停"
    ERROR = "错误"
    STOPPED = "已停止"


class MessageType(str, Enum):
    """消息类型"""
    DATA_REQUEST = "数据请求"
    DATA_RESPONSE = "数据响应"
    TASK_ASSIGN = "任务分配"
    TASK_COMPLETE = "任务完成"
    STATUS_UPDATE = "状态更新"
    ERROR_REPORT = "错误报告"
    HEARTBEAT = "心跳"


@dataclass
class ModuleMessage:
    """模块间消息"""
    sender: str
    receiver: str
    msg_type: MessageType
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: f"msg_{int(time.time() * 1000)}")
    correlation_id: Optional[str] = None


class ModuleRegistry:
    """模块注册中心"""

    def __init__(self):
        self._modules: Dict[str, ModuleInterface] = {}
        self._lock = Lock()

    def register(self, module: ModuleInterface):
        """注册模块"""
        with self._lock:
            self._modules[module.name] = module

    def unregister(self, module_name: str):
        """注销模块"""
        with self._lock:
            if module_name in self._modules:
                del self._modules[module_name]

    def get_module(self, module_name: str) -> Optional[ModuleInterface]:
        """获取模块"""
        return self._modules.get(module_name)

    def list_modules(self) -> List[str]:
        """列出所有模块"""
        return list(self._modules.keys())

    def get_module_status(self, module_name: str) -> Optional[ModuleStatus]:
        """获取模块状态"""
        module = self._modules.get(module_name)
        return module.status if module else None


class ModuleInterface:
    """模块接口基类"""

    def __init__(self, name: str):
        self.name = name
        self.status = ModuleStatus.INITIALIZING
        self.message_handlers: Dict[MessageType, Callable] = {}
        self._message_queue: List[ModuleMessage] = []
        self._lock = Lock()

    def register_handler(self, msg_type: MessageType, handler: Callable):
        """注册消息处理器"""
        self.message_handlers[msg_type] = handler

    async def handle_message(self, message: ModuleMessage):
        """处理消息"""
        handler = self.message_handlers.get(message.msg_type)
        if handler:
            await handler(message)
        else:
            print(f"[{self.name}] 未注册的消息类型: {message.msg_type}")

    async def send_message(
        self,
        receiver: str,
        msg_type: MessageType,
        payload: Dict[str, Any],
        registry: ModuleRegistry
    ):
        """发送消息"""
        message = ModuleMessage(
            sender=self.name,
            receiver=receiver,
            msg_type=msg_type,
            payload=payload
        )

        target_module = registry.get_module(receiver)
        if target_module:
            await target_module.handle_message(message)
        else:
            print(f"[{self.name}] 目标模块不存在: {receiver}")

    def start(self):
        """启动模块"""
        self.status = ModuleStatus.RUNNING

    def stop(self):
        """停止模块"""
        self.status = ModuleStatus.STOPPED


class DataBus:
    """数据共享总线"""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)
        self._lock = Lock()

    def publish(self, key: str, value: Any, publisher: str):
        """发布数据"""
        with self._lock:
            self._data[key] = {
                "value": value,
                "publisher": publisher,
                "timestamp": time.time()
            }

            # 通知订阅者
            if key in self._subscriptions:
                for subscriber in self._subscriptions[key]:
                    print(f"[DataBus] 通知订阅者 {subscriber}: {key} 已更新")

    def subscribe(self, key: str, subscriber: str):
        """订阅数据"""
        with self._lock:
            self._subscriptions[key].add(subscriber)

    def get(self, key: str) -> Optional[Any]:
        """获取数据"""
        with self._lock:
            if key in self._data:
                return self._data[key]["value"]
            return None

    def get_with_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """获取数据和元数据"""
        with self._lock:
            return self._data.get(key)


class CollaborationOrchestrator:
    """协同任务编排器"""

    def __init__(self):
        self.registry = ModuleRegistry()
        self.data_bus = DataBus()
        self._task_queue: List[Dict[str, Any]] = []
        self._lock = Lock()

    def register_module(self, module: ModuleInterface):
        """注册模块"""
        module.registry = self.registry
        module.data_bus = self.data_bus
        self.registry.register(module)
        print(f"[Orchestrator] 模块已注册: {module.name}")

    async def dispatch_task(
        self,
        task_name: str,
        target_modules: List[str],
        task_payload: Dict[str, Any]
    ):
        """分发任务"""
        print(f"\n[Orchestrator] 分发任务: {task_name}")
        print(f"  目标模块: {target_modules}")

        tasks = []
        for module_name in target_modules:
            module = self.registry.get_module(module_name)
            if module and module.status == ModuleStatus.RUNNING:
                msg = ModuleMessage(
                    sender="orchestrator",
                    receiver=module_name,
                    msg_type=MessageType.TASK_ASSIGN,
                    payload={"task_name": task_name, **task_payload}
                )
                tasks.append(module.handle_message(msg))

        if tasks:
            await asyncio.gather(*tasks)
            print(f"[Orchestrator] 任务 {task_name} 已分发")
        else:
            print(f"[Orchestrator] 警告: 没有可用的目标模块")

    async def broadcast_status(self):
        """广播状态"""
        status_summary = {}
        for module_name in self.registry.list_modules():
            status = self.registry.get_module_status(module_name)
            status_summary[module_name] = status.value if status else "未知"

        print(f"\n[Orchestrator] 系统状态:")
        for name, status in status_summary.items():
            print(f"  {name}: {status}")

        return status_summary

    async def health_check(self) -> Dict[str, bool]:
        """健康检查"""
        health = {}
        for module_name in self.registry.list_modules():
            module = self.registry.get_module(module_name)
            if module:
                # 简单检查：模块是否在运行
                health[module_name] = (module.status == ModuleStatus.RUNNING)

        return health


# 示例：财务分析模块
class FinancialAnalysisModule(ModuleInterface):
    """财务分析模块"""

    def __init__(self):
        super().__init__("financial_analyzer")
        self.registry: Optional[ModuleRegistry] = None
        self.data_bus: Optional[DataBus] = None

        # 注册消息处理器
        self.register_handler(MessageType.DATA_REQUEST, self._handle_data_request)
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task_assign)

    async def _handle_data_request(self, message: ModuleMessage):
        """处理数据请求"""
        print(f"[{self.name}] 收到数据请求: {message.payload}")

        # 模拟数据查询
        result = {"revenue": 1000000, "profit": 200000}

        # 发送响应
        if self.registry:
            await self.send_message(
                receiver=message.sender,
                msg_type=MessageType.DATA_RESPONSE,
                payload={"result": result, "correlation_id": message.message_id},
                registry=self.registry
            )

    async def _handle_task_assign(self, message: ModuleMessage):
        """处理任务分配"""
        print(f"[{self.name}] 收到任务: {message.payload.get('task_name')}")

        # 执行任务
        await asyncio.sleep(0.5)  # 模拟工作

        # 发布结果到数据总线
        if self.data_bus:
            self.data_bus.publish(
                key="financial_analysis_result",
                value={"status": "completed", "module": self.name},
                publisher=self.name
            )

        # 发送完成消息
        if self.registry:
            await self.send_message(
                receiver="orchestrator",
                msg_type=MessageType.TASK_COMPLETE,
                payload={"task": message.payload.get("task_name"), "status": "success"},
                registry=self.registry
            )


# 导出
__all__ = [
    "CollaborationOrchestrator",
    "ModuleRegistry",
    "ModuleInterface",
    "ModuleMessage",
    "DataBus",
    "ModuleStatus",
    "MessageType"
]
