#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
系统配置文件
"""

import os
from pathlib import Path
from typing import Dict, Any
import warnings

class Settings:
    """系统配置类"""

    def __init__(self):
        """初始化配置"""
        # --- 服务器配置 ---
        self.host = os.environ.get("HOSPITAL_HOST", "127.0.0.1") # 默认改为 127.0.0.1，更安全
        self.port = int(os.environ.get("HOSPITAL_PORT", "5000")) # Flask 默认端口 5000
        self.debug_mode = os.environ.get("HOSPITAL_DEBUG", "true").lower() == "true"

        # --- Flask Web 应用配置 ---
        # !!! 警告: 生产环境中必须设置一个强随机的 FLASK_SECRET_KEY 环境变量 !!!
        self.flask_secret_key = os.environ.get("FLASK_SECRET_KEY")
        if not self.flask_secret_key and self.debug_mode:
            warnings.warn("FLASK_SECRET_KEY 未设置，在调试模式下将使用临时密钥。请在生产环境中设置此环境变量！")
            self.flask_secret_key = "temp-debug-secret-key-replace-me" # 仅用于调试
        elif not self.flask_secret_key and not self.debug_mode:
             raise ValueError("错误：生产环境中必须设置 FLASK_SECRET_KEY 环境变量！")

        # --- 项目路径 ---
        self.base_dir = Path(__file__).resolve().parent.parent # 使用 resolve() 更可靠
        self.data_dir = self.base_dir / "data"
        self.log_dir = self.base_dir / "logs" # 建议将日志放在单独目录

        # --- 创建必要的目录 ---
        self._create_directories()

        # --- 日志配置 ---
        self.log_level = os.environ.get("HOSPITAL_LOG_LEVEL", "INFO").upper()
        self.web_log_file = self.log_dir / "hospital_system_web.log"
        self.core_log_file = self.log_dir / "hospital_system_core.log" # 为核心逻辑使用不同日志

        # --- Azure OpenAI配置 ---
        self.llm_config = {
            "api_key": os.environ.get("AZURE_OPENAI_API_KEY", ""),
            "endpoint": self._ensure_url_protocol(os.environ.get("AZURE_OPENAI_ENDPOINT", "")),
            "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"), # 提供一个更新的默认版本
            "deployment_name": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", ""),
        }

        # --- 智能体配置 (可以保持不变) ---
        self.agent_config = {
            "receptionist": {
                "name": os.environ.get("RECEPTIONIST_NAME", "李接待"),
            },
            "doctor": {
                "name": os.environ.get("DOCTOR_NAME", "王医生"),
                "specialty": os.environ.get("DOCTOR_SPECIALTY", "内科"), # 默认改为内科
            },
            "pharmacist": {
                "name": os.environ.get("PHARMACIST_NAME", "张药师"),
            },
            "scheduler": {
                "name": os.environ.get("SCHEDULER_NAME", "调度器"),
            }
        }

        # --- 医疗流程配置 (可以保持不变) ---
        self.medical_workflows = {
            "consultation": [
                "reception",
                "vitals_check", # 这个步骤当前未实现
                "doctor_diagnosis",
                "prescription_review", # 调整流程名称以匹配
                "pharmacy", # 这个步骤当前未实现
                "checkout" # 这个步骤当前未实现
            ]
        }

        # --- 系统其他配置 (可以保持不变) ---
        self.max_consultations_per_day = int(os.environ.get("MAX_CONSULTATIONS", "100"))
        self.consultation_timeout = int(os.environ.get("CONSULTATION_TIMEOUT", "1800"))  # 秒

    def _create_directories(self):
        """创建必要的目录"""
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

    def get_agent_config(self, agent_type: str) -> Dict[str, Any]:
        """获取特定智能体的配置"""
        return self.agent_config.get(agent_type, {})

    def validate_llm_config(self) -> bool:
        """验证LLM配置是否有效"""
        # api_version 不是严格必须的，因为库可能有默认值，但推荐配置
        required_fields = ["api_key", "endpoint", "deployment_name"]
        missing = [field for field in required_fields if not self.llm_config.get(field)]
        if missing:
             warnings.warn(f"LLM 配置缺失以下字段: {', '.join(missing)}")
             return False
        return True

    def _ensure_url_protocol(self, url: str) -> str:
        """确保URL包含http/https协议前缀"""
        if not url:
            return ""
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            warnings.warn(f"URL '{url}' 缺少协议前缀，将默认添加 'https://'")
            # 检查常见错误，如多了斜杠
            if url.startswith("//"):
                 url = url[2:]
            return "https://" + url
        return url

    # 添加一个 get 方法以便像字典一样安全地获取配置
    def get(self, key: str, default: Any = None) -> Any:
        """安全地获取配置项"""
        return getattr(self, key, default)

# 创建一个全局的配置实例供其他模块使用
SETTINGS = Settings()