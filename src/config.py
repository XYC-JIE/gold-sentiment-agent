"""配置加载：路径常量、信源配置、环境变量。"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CHARTS_DIR = ROOT_DIR / "charts"
SAMPLES_DIR = ROOT_DIR / "samples"
CONFIG_PATH = ROOT_DIR / "config" / "sources.yaml"


def load_sources() -> list[dict]:
    """读取 sources.yaml，返回信源配置列表。"""
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    sources = data.get("sources") or []
    if not sources:
        raise ValueError(f"未在 {CONFIG_PATH} 中找到任何信源配置")
    return sources


def get_secret(name: str) -> str:
    """读取密钥；缺失时抛出明确错误，避免带着 None 继续跑。"""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}，请检查 .env 或 GitHub Secrets")
    return value
