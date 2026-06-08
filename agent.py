import os, json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ---------- 工具：就是普通函数 ----------
def get_weather(city: str) -> str:
    return f"{city} 今天 25°C，晴"   # 先写死，练习用

def get_weather_batch(cities: list[str]) -> str:
    """批量查询多个城市的天气

    支持一次传入多个城市；某个城市查询失败不影响其他城市。
    返回结构化结果，便于 LLM 后续推理。
    """
    if not cities:
        return "错误：未提供任何城市"

    results = []
    for city in cities:
        try:
            results.append(f"{city} 今天 25°C，晴")
        except Exception as e:
            # 单城市失败不抛出，标记错误后继续
            results.append(f"{city}：查询失败（{e}）")

    return "\n".join(results)



def calculator(expression: str) -> str:
    return str(eval(expression))      # 练习用，生产环境禁止 eval



# ---------- 工具的"说明书"：给 LLM 看的 ----------
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询城市天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_batch",
            "description": "批量查询城市天气",
            "parameters": {
                "type": "object",
                "properties": {"cities": {"type": "array", "description": "城市名"}},
                "required": ["cities"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算一个数学表达式",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "如 2+2*3"}},
                "required": ["expression"],
            },
        },
    },
]




def execute_tool(name, args: dict) -> str:
    if name == "get_weather":
        return get_weather(**args)
    if name == "calculator":
        return calculator(**args)

    if name == "get_weather_batch":
        return get_weather_batch(**args)
    return f"未知工具: {name}"

# ---------- Agent Loop：核心循环 ----------
def run_agent(user_input, max_turns=10):
    messages = [{"role": "user", "content": user_input}]
    for turn in range(max_turns):                      # 终止条件1：最大轮数
        resp = client.chat.completions.create(
            model="deepseek-chat", messages=messages, tools=tools,
        )
        msg = resp.choices[0].message
        messages.append(msg)                           # assistant 这轮原样塞回

        if not msg.tool_calls:                         # 终止条件2：LLM 不再要工具
            print(f"\n✅  最终回答: {msg.content}")
            return msg.content

        for call in msg.tool_calls:                    # LLM 要调工具：逐个执行
            name = call.function.name
            args = json.loads(call.function.arguments) # 字符串→字典
            print(f"  🔧 调用 {name}({args})")
            result = execute_tool(name, args)
            print(f"  ↩️  结果: {result}")
            messages.append({                          # 结果回填给 LLM
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

if __name__ == "__main__":
    run_agent("分别调用北京和上海的天气怎么样，然后算一下 25 加 18")