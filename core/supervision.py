"""Process supervision primitives for the Wu Dehou quality gate."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SupervisionEvent:
    """A structured supervision checkpoint or quality intervention."""

    stage: str
    agent_id: str
    agent_name: str
    event_type: str
    message: str
    severity: str = "INFO"
    attempt: int = 0
    violations: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "event_type": self.event_type,
            "message": self.message,
            "severity": self.severity,
            "attempt": self.attempt,
            "violations": list(self.violations),
            "created_at": self.created_at,
        }


class WuDehouSupervisor:
    """Turns Wu Dehou from role flavor into a process-level supervisor."""

    CHECKPOINTS: tuple[tuple[int, str], ...] = (
        (0, "开工了，别等我点名。先把证据链搭起来。"),
        (25, "四分之一过去了，谁还在原地打转，自己心里有数。"),
        (50, "中场检查。没有来源、没有结论、没有风险线索的，现在补。"),
        (75, "收口阶段。把未获取和数据冲突标出来，别拿漂亮话糊弄。"),
        (100, "交卷。先过铁律，再谈文采。"),
    )

    def checkpoint(
        self,
        *,
        stage: str,
        progress: int,
        active_agents: list[Any],
    ) -> SupervisionEvent:
        message = self._checkpoint_message(progress)
        names = ", ".join(str(getattr(agent, "name", agent)) for agent in active_agents[:5])
        if names:
            message = f"{message} 当前盯着: {names}。"
        return SupervisionEvent(
            stage=stage,
            agent_id="wu-de-hou",
            agent_name="吴德厚",
            event_type="checkpoint",
            message=message,
            severity="INFO",
        )

    def review_result(
        self,
        *,
        stage: str,
        agent_id: str,
        agent_name: str,
        passed: bool,
        attempt: int,
        violations: list[Any],
    ) -> SupervisionEvent:
        if passed:
            return SupervisionEvent(
                stage=stage,
                agent_id=agent_id,
                agent_name=agent_name,
                event_type="quality_pass",
                message=f"{agent_name} 这次过了。别飘，证据链继续保持。",
                severity="INFO",
                attempt=attempt,
            )

        rules = tuple(str(getattr(item, "rule", item)) for item in violations)
        severity = "ERROR" if any(getattr(item, "severity", "") == "ERROR" for item in violations) else "WARN"
        return SupervisionEvent(
            stage=stage,
            agent_id=agent_id,
            agent_name=agent_name,
            event_type="quality_reject",
            message=self.feedback(agent_name=agent_name, attempt=attempt, violations=violations),
            severity=severity,
            attempt=attempt,
            violations=rules,
        )

    def retry_notice(
        self,
        *,
        stage: str,
        agent_id: str,
        agent_name: str,
        attempt: int,
        error: str,
    ) -> SupervisionEvent:
        return SupervisionEvent(
            stage=stage,
            agent_id=agent_id,
            agent_name=agent_name,
            event_type="retry",
            message=(
                f"{agent_name} 遇到瞬时故障，第 {attempt} 次重试。"
                f"别停，等中转站缓过来继续干。原因: {error}"
            ),
            severity="WARN",
            attempt=attempt,
            violations=("transient_failure",),
        )

    def degrade_notice(
        self,
        *,
        stage: str,
        agent_id: str,
        agent_name: str,
        attempt: int,
        reason: str,
    ) -> SupervisionEvent:
        return SupervisionEvent(
            stage=stage,
            agent_id=agent_id,
            agent_name=agent_name,
            event_type="degraded",
            message=(
                f"{agent_name} 已降级处理。不是让流程停摆，是把缺口标出来继续推进。"
                f"原因: {reason}"
            ),
            severity="ERROR",
            attempt=attempt,
            violations=("degraded",),
        )

    def feedback(self, *, agent_name: str, attempt: int, violations: list[Any]) -> str:
        issues = "; ".join(
            f"{getattr(item, 'rule', 'issue')}: {getattr(item, 'detail', item)}"
            for item in violations[:4]
        ) or "质量不达标"
        if attempt <= 1:
            return f"{agent_name}，别急着交差。问题摆这儿: {issues}。改完再来。"
        if attempt == 2:
            return (
                f"第二次了，{agent_name}。别把低质量当努力。"
                f"问题: {issues}。最后一轮，拿证据说话。"
            )
        return (
            f"{agent_name}，三次不过就降级。不是我难说话，是证据链不认人。"
            f"问题: {issues}。"
        )

    def _checkpoint_message(self, progress: int) -> str:
        chosen = self.CHECKPOINTS[0][1]
        for threshold, message in self.CHECKPOINTS:
            if progress >= threshold:
                chosen = message
        return chosen
