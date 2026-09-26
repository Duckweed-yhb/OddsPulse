"""OddsPulse 全局配置：从环境变量读取，不在代码里写死密钥。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# 项目根目录（本文件所在目录的上一级）
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("ODDSPULSE_DB", str(ROOT_DIR / "data" / "odspulse.db")))


@dataclass
class Config:
    """运行配置。所有敏感信息只从环境变量读取。"""
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    default_limit: int = int(os.getenv("ODDSPULSE_LIMIT", "100"))
    db_path: Path = DB_PATH

    @property
    def has_llm_key(self) -> bool:
        return bool(self.openai_api_key)
