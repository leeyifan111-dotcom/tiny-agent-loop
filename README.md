# tiny-agent-loop

从零手写的最小 AI Agent 循环，约 60 行 Python，跑通「LLM 决策 → 调用工具 → 结果回填 → 再决策 → 直到完成」的完整闭环。

基于 DeepSeek API（OpenAI 兼容协议）实现。

## 它做了什么

给定一个问题（如 _「北京天气怎么样，然后算一下 25 加 18」_），Agent 会：

1. LLM 判断需要调用哪些工具（天气查询、计算器）
2. 本地代码执行工具，拿到真实结果
3. 结果回填给 LLM
4. LLM 综合所有结果，给出最终答案

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux/Mac

# 2. 安装依赖
pip install openai python-dotenv

# 3. 配置 API Key
# 新建 .env 文件，写入：
# DEEPSEEK_API_KEY=sk-xxx

# 4. 运行
python agent.py
```

## 核心概念

- **Agent Loop**：让 LLM 在「思考 → 调工具 → 看结果 → 再思考」的循环中自主推进任务
- **Function Calling**：LLM 决定调用哪个工具、传什么参数；真正执行函数的是本地代码
- **Tool Schema**：用 JSON 描述工具的名字、用途、参数，让 LLM「看得懂」可用工具

## 文件说明

| 文件       | 作用                             |
| ---------- | -------------------------------- |
| `agent.py` | Agent 主循环 + 工具定义 + Schema |
| `.env`     | API key（不入库）                |

## 后续计划

- [ ] Day 3：加错误处理、结构化日志、接入真实天气 API
- [ ] 流式输出（latency 优化）
- [ ] 扩展为 tiny-rag（下一个练习）
