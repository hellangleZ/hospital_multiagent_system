#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
医院多智能体系统Web应用
"""

import os
import logging
import json
import uuid
from flask import Flask, render_template, request, jsonify, session as flask_session # 导入 flask_session 用于会话管理
from datetime import datetime, timedelta

# 导入必要的类
try:
    from agents.receptionist import ReceptionistAgent
    from agents.doctor import DoctorAgent
    from agents.pharmacist import PharmacistAgent
    from utils.orchestrator import Orchestrator
    from utils.memory_system import MemorySystem
    from utils.llm_service import LLMService # LLMService 可能由 MemorySystem 或 Agents 初始化时需要
    from config.settings import SETTINGS
except ImportError as e:
    logging.critical(f"Web App 无法导入核心组件: {e}", exc_info=True)
    # 致命错误，无法启动
    raise SystemExit(f"Web App 启动失败: {e}")


# 配置日志
logging.basicConfig(
    level=logging.INFO, # 可以根据 SETTINGS.debug_mode 调整
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("hospital_system_web.log")
    ]
)
logger = logging.getLogger("Hospital-MultiAgent-System-Web")

app = Flask(__name__)
# 配置 Flask session 密钥，用于加密会话数据
# !!! 生产环境中必须使用强随机密钥，并从配置或环境变量读取 !!!
app.secret_key = SETTINGS.get("FLASK_SECRET_KEY", os.urandom(24))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2) # 设置会话超时时间

# --- 初始化核心系统 ---
hospital_system = {} # 全局变量存储系统实例

def init_hospital_system():
    """初始化医院系统的所有组件"""
    global hospital_system
    try:
        logger.info("开始初始化医院核心系统...")
        # 确保 LLM 配置有效
        if not SETTINGS.validate_llm_config():
             logger.warning("LLM 配置不完整，功能可能受限。")
             # 可以选择是否继续，或者抛出错误
             # raise ValueError("LLM 配置无效，无法启动系统。")

        llm_service_instance = LLMService(settings=SETTINGS) # 创建实例
        memory_system_instance = MemorySystem(
            persistence_path=SETTINGS.data_dir / "hospital_memory_web.json", # 为web应用使用单独的内存文件
            llm_service=llm_service_instance # 传递给 MemorySystem 用于归纳
        )
        receptionist_instance = ReceptionistAgent(memory_system=memory_system_instance, llm_service=llm_service_instance)
        doctor_instance = DoctorAgent(memory_system=memory_system_instance, llm_service=llm_service_instance)
        pharmacist_instance = PharmacistAgent(memory_system=memory_system_instance, llm_service=llm_service_instance)
        # scheduler 实例按需添加
        orchestrator_instance = Orchestrator(
            receptionist=receptionist_instance,
            doctor=doctor_instance,
            pharmacist=pharmacist_instance,
            memory_system=memory_system_instance
        )

        hospital_system = {
            "receptionist": receptionist_instance,
            "doctor": doctor_instance,
            "pharmacist": pharmacist_instance,
            "orchestrator": orchestrator_instance,
            "memory_system": memory_system_instance,
            "llm_service": llm_service_instance
        }
        logger.info("医院核心系统初始化成功。")
        return True
    except Exception as e:
        logger.critical(f"初始化医院核心系统失败: {str(e)}", exc_info=True)
        hospital_system = {} # 清空以表示失败
        return False

# 在应用启动时执行初始化
if not init_hospital_system():
     logger.critical("无法初始化核心系统，Web 应用可能无法正常工作。")
     # 可以选择退出应用或让其以受限模式运行
     # raise SystemExit("核心系统初始化失败，Web 应用无法启动。")


@app.route('/')
def index():
    """渲染主页"""
    # 可以在这里清理旧的会话数据（如果需要）
    # flask_session.clear()
    return render_template('index.html')

@app.route('/api/start_consultation', methods=['POST'])
def start_consultation():
    """开始新的咨询会话（由前端调用）"""
    if not hospital_system:
        return jsonify({"status": "error", "message": "系统未初始化，请稍后重试。"}), 503

    try:
        # 调用 Orchestrator 获取初始信息
        orchestrator = hospital_system.get("orchestrator")
        if not orchestrator:
             return jsonify({"status": "error", "message": "编排器服务不可用。"}), 503

        consultation_id, initial_message = orchestrator.start_new_web_consultation()

        # 将 consultation_id 存储在 Flask session 中
        flask_session['consultation_id'] = consultation_id
        flask_session.permanent = True # 使用配置的超时时间
        logger.info(f"为新 Web 会话 {request.remote_addr} 启动咨询，ID: {consultation_id}")

        return jsonify({
            "status": "success",
            "consultation_id": consultation_id, # 返回 ID 给前端（虽然前端可能不再直接使用它）
            "initial_message": { # 返回初始消息让前端显示
                 "agent_type": "receptionist",
                 "message": initial_message
            }
        })

    except Exception as e:
        logger.error(f"开始 Web 咨询失败: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "开始咨询时发生服务器内部错误。"
        }), 500

@app.route('/api/conversation', methods=['POST'])
def handle_conversation():
    """处理来自前端的对话消息"""
    if not hospital_system:
        return jsonify({"status": "error", "message": "系统未初始化，请稍后重试。"}), 503

    try:
        data = request.get_json()
        user_message = data.get('message')
        # 优先从 Flask session 获取 consultation_id
        consultation_id = flask_session.get('consultation_id')
        # 如果 session 中没有，尝试从请求中获取（作为后备或调试）
        if not consultation_id:
             consultation_id = data.get('consultation_id')
             logger.warning(f"无法从 session 获取 consultation_id，尝试从请求体获取: {consultation_id}")

        if not consultation_id:
            return jsonify({"status": "error", "message": "会话ID丢失，请刷新页面开始新的咨询。"}), 400
        if not user_message:
            return jsonify({"status": "error", "message": "发送的消息不能为空。"}), 400

        # 获取 Orchestrator 实例
        orchestrator = hospital_system.get("orchestrator")
        if not orchestrator:
             return jsonify({"status": "error", "message": "编排器服务不可用。"}), 503

        # 调用 Orchestrator 处理消息
        response_data = orchestrator.handle_web_message(consultation_id, user_message)

        # 如果 Orchestrator 返回错误状态，直接返回
        if response_data.get("status") == "error":
             return jsonify(response_data), 500 # 或根据错误类型返回不同状态码

        # 可以在这里根据需要更新 Flask session 中的状态，但不建议存储过多数据
        # flask_session['last_agent'] = response_data.get('agent_type')

        # 检查是否问诊结束，如果结束则清理会话
        final_status = ["completed_diagnosis", "completed_prescription", "error_prescription_rejected"] # 定义结束状态
        if response_data.get("status") in final_status:
             logger.info(f"Web 咨询 {consultation_id} 已达到结束状态: {response_data.get('status')}")
             flask_session.pop('consultation_id', None) # 清理会话中的ID

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"处理 Web 对话失败 (Session Consult ID: {flask_session.get('consultation_id')}): {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "处理您的消息时发生服务器内部错误。"
        }), 500

# 添加路由以查看所有交互日志文件
@app.route('/api/interaction_logs', methods=['GET'])
def list_interaction_logs():
    """返回所有可用的交互日志文件列表"""
    try:
        logs_dir = "logs"
        if not os.path.exists(logs_dir):
            return jsonify({"status": "success", "logs": []})
        
        log_files = []
        for filename in os.listdir(logs_dir):
            if filename.startswith("interaction_log_") and filename.endswith(".json"):
                consultation_id = filename.replace("interaction_log_", "").replace(".json", "")
                file_path = os.path.join(logs_dir, filename)
                file_stats = os.stat(file_path)
                log_files.append({
                    "consultation_id": consultation_id,
                    "filename": filename,
                    "size": file_stats.st_size,
                    "modified_time": datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                })
        
        # 按修改时间排序，最新的在前面
        log_files.sort(key=lambda x: x["modified_time"], reverse=True)
        
        return jsonify({"status": "success", "logs": log_files})
    except Exception as e:
        logger.error(f"获取交互日志列表时出错: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"获取日志列表时出错: {str(e)}"}), 500

# 添加路由以获取特定交互日志的内容
@app.route('/api/interaction_logs/<consultation_id>', methods=['GET'])
def get_interaction_log(consultation_id):
    """返回特定咨询ID的交互日志"""
    try:
        log_filename = f"interaction_log_{consultation_id}.json"
        log_path = os.path.join("logs", log_filename)
        
        if not os.path.exists(log_path):
            return jsonify({"status": "error", "message": "找不到指定的交互日志"}), 404
        
        with open(log_path, 'r', encoding='utf-8') as f:
            log_data = json.load(f)
            
        return jsonify({"status": "success", "consultation_id": consultation_id, "logs": log_data})
    except Exception as e:
        logger.error(f"获取交互日志 {consultation_id} 时出错: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"获取日志内容时出错: {str(e)}"}), 500

@app.route('/logs')
def view_logs():
    """渲染日志查看页面"""
    return render_template('logs.html')

if __name__ == '__main__':
    # 从 SETTINGS 获取主机和端口
    host = SETTINGS.host
    port = SETTINGS.port
    debug_mode = SETTINGS.debug_mode
    logger.info(f"启动 Flask Web 应用，地址: http://{host}:{port}，调试模式: {debug_mode}")
    # 注意：生产环境不应使用 debug=True
    app.run(host=host, port=port, debug=debug_mode)