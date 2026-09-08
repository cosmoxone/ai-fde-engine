"""
RPA 测试执行集成（卖点 4：自动化测试/验收执行）

本项目产出 Benchmark 测试集（卖点 2），执行由外部 RPA 项目承接：
- 配置 RPA_WEBHOOK_URL 后，Benchmark 用例可派发给 RPA 项目执行（UI/E2E）
- 未配置时返回明确的「待接入」状态（编排位就绪，执行按需接入）

接口契约（RPA 项目需实现）：
  POST {RPA_WEBHOOK_URL}/jobs   body: {"cases": [...], "callback": "..."}
      → {"job_id": "..."}
  GET  {RPA_WEBHOOK_URL}/jobs/{job_id}
      → {"status": "running|completed", "results": [{"case_id", "passed", "actual"}]}
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional


class RpaRunner(ABC):
    """RPA 测试执行器抽象（卖点 4 编排位）"""

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def dispatch(self, cases: list[dict]) -> dict:
        """派发测试用例，返回 {status, job_id?, message}"""

    @abstractmethod
    def status(self, job_id: str) -> dict: ...


class ExternalRpaRunner(RpaRunner):
    """通过 webhook 对接外部 RPA 项目"""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = (webhook_url or os.environ.get("RPA_WEBHOOK_URL", "")).rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        url = f"{self.webhook_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def dispatch(self, cases: list[dict]) -> dict:
        if not self.is_configured():
            return {
                "status": "pending_integration",
                "message": "未配置 RPA_WEBHOOK_URL。Benchmark 用例已就绪，接入外部 RPA 项目即可执行（接口契约见 src/integrations/rpa_runner.py 模块注释）",
                "case_count": len(cases),
            }
        try:
            result = self._request("POST", "/jobs", {"cases": cases})
            return {"status": "dispatched", "job_id": result.get("job_id"), "case_count": len(cases)}
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            return {"status": "error", "message": f"RPA 派发失败: {e}"}

    def status(self, job_id: str) -> dict:
        if not self.is_configured():
            return {"status": "pending_integration", "message": "未配置 RPA_WEBHOOK_URL"}
        try:
            return self._request("GET", f"/jobs/{job_id}")
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            return {"status": "error", "message": str(e)}


_runner: Optional[RpaRunner] = None


def get_rpa_runner() -> RpaRunner:
    global _runner
    if _runner is None:
        _runner = ExternalRpaRunner()
    return _runner
