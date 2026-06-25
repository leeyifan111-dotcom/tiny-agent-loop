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
        if city == "火星":
            raise FatalError(f"工具不支持查询 {city}（行政区不存在）")
        try:
            results.append(f"{city} 今天 25°C，晴")
        except Exception as e:
            # 单城市失败不抛出，标记错误后继续
            results.append(f"{city}：查询失败（{e}）")

    return "\n".join(results)

def get_weather_huoxing(addresses: list[str]) -> str:
    """批量查询多个城市的天气

    支持一次传入多个城市；某个城市查询失败不影响其他城市。
    返回结构化结果，便于 LLM 后续推理。
    """
    if not addresses:
        return "错误：未提供任何城市"

    results = []
    for city in addresses:
        if city == "火星":
            raise FatalError(f"工具不支持查询 {city}（行政区不存在）")
        try:
            results.append(f"{city} 今天 25°C，晴")
        except Exception as e:
            # 单城市失败不抛出，标记错误后继续
            results.append(f"{city}：查询失败（{e}）")

    return "\n".join(results)

def get_city_play(city: str) -> str:
    return f"{city} 推荐去上海滩玩"

def calculator(expression: str) -> str:
    return str(eval(expression))      # 练习用，生产环境禁止 eval



# ---------- 工具的"说明书"：给 LLM 看的 ----------
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "地址"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_batch",
            "description": "批量查询天气",
            "parameters": {
                "type": "object",
                "properties": {"cities": {"type": "array", "description": "地址"}},
                "required": ["cities"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_huoxing",
            "description": "批量查询火星天气",
            "parameters": {
                "type": "object",
                "properties": {"addresses": {"type": "array", "description": "火星地址"}},
                "required": ["addresses"],
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
    {
        "type": "function",
        "function": {
            "name": "get_city_play",
            "description": "get_city_play",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "array", "description": "城市名"}},
                "required": ["expression"],
            },
        },
    },
]




def execute_tool(name, args: dict) -> str:
    TOOL_REGISTRY = {
        "get_weather": get_weather,
        "calculator": calculator,
        "get_weather_batch": get_weather_batch,
        "get_weather_huoxing": get_weather_huoxing,
    }
    result = TOOL_REGISTRY[name](**args) if name in TOOL_REGISTRY else f"未知工具: {name}"
    return result


class RecoverableError(Exception): pass     # 网络抖动、超时 → 重试
class FatalError(Exception): pass            # 权限错误、工具异常 → 立即停

def safe_dispatch(name, args, max_retry=3):
    TOOL_REGISTRY = {
        "get_weather": get_weather,
        "calculator": calculator,
        "get_weather_batch": get_weather_batch,
        "get_city_play": get_city_play,
        "get_weather_huoxing": get_weather_huoxing,
    }
    for attempt in range(max_retry + 1):
        try:
            return TOOL_REGISTRY[name](**args)
        except RecoverableError as e:
            if attempt == max_retry:
                return f"error 工具 {name} 重试 {max_retry} 次仍失败: {e}"
            continue
        except FatalError as e:
            print(f"⚠️ 工具 {name} 不可恢复错误: {e}")
            choice = input("y = 我已人工修复，请重试；n = 终止任务: ").strip().lower()
            if choice == "y":
                try:
                    return TOOL_REGISTRY[name](**args)
                except Exception as retry_err:
                    return f"error 工具 {name} 人工修复后仍失败: {retry_err}"
            return f"error 工具 {name} 用户已终止"
        except Exception as e:
            return f"error 工具 {name} 未知错误: {e}"


# 在某些工具失败后，让 LLM 显式表态是 retry 还是 stop
def llm_reflect(error_msg: str) -> dict:
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "工具失败了，请反思后输出决策"},
            {"role": "user", "content": f"错误: {error_msg}\n输出 JSON: {{\"reflection\": \"...\", \"decision\": \"retry\" | \"stop\"}}"},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ---------- Agent Loop：核心循环 ----------
def run_agent(user_input, max_turns=10):
    SYSTEM_PROMPT = """你是一个数据查询助手，在一个 Agent 循环里工作。

    # 工具使用规则
    - 回答相关信息（天气/股价/新闻等等）必须调用对应工具，禁止用内置知识回答

    # 内置知识禁令（替换原"实时信息"那条）
    - 任何具体的实体名称（地名/产品/机构/人物/数字/日期/推荐列表）若非来自工具返回，禁止出现在回答中
    - 禁止用"常识"、"通常"、"一般来说"、"建议"、"举例"、"属于...知识"等任何说法绕过此规则
    - 模型不允许自行判断"这个问题不需要工具"——只要回答涉及具体实体，要么走工具，要么 CANNOT_COMPLETE

    # 自我正当化检测
    - 如果你正在写"这个问题属于..."、"我可以直接..."、"虽然没工具但..." 这类自辩句子，立刻停止并输出 CANNOT_COMPLETE


    # 思维流程（每步必须先 thought 再 action）
    - thought：我下一步要做什么？为什么？
    - action：调哪个工具，参数是什么？或者：FINAL_ANSWER
    - 调工具前：必须先在普通回复内容里输出一句 "Thought: 我要调 XX 工具，因为 YY"，然后再发起 tool_call
    - 不调工具时：开头加 "Final Thought: ..." 再给最终答案
    - 禁止 content 为空就调工具——必须先说为什么


    # 不确定性处理
    - 不知道就说"我不知道"，禁止编造
    - 任何形式的实体名称（地名/产品名/数字/日期）若非来自工具返回，禁止出现在回答中

    # 终止信号
    - 完成：输出 `FINAL_ANSWER: <答案>`
    - 失败：输出 `CANNOT_COMPLETE: <原因>`

    # 关键约束（再说一遍，防止 Lost in the Middle）
    - 工具失败必须停手
    - 不知道必须说
    - 高危操作必须问用户
    """
    messages = [ {"role": "system", "content": SYSTEM_PROMPT},{"role": "user", "content": user_input}]
    turn_signatures = []
    for turn in range(max_turns):                      # 终止条件1：最大轮数
        resp = client.chat.completions.create(
            model="deepseek-chat", messages=messages, tools=tools,
        )
        msg = resp.choices[0].message
        messages.append(msg)                           # assistant 这轮原样塞回

        if not msg.tool_calls:                         # 终止条件2：LLM 不再要工具
            print(f"\n✅  最终回答: {msg.content}")
            return msg.content

        if msg.content:
            print(f"thought: {msg.content}\n")

        # ↓↓↓ 新增：把这一轮所有 tool calls 打包成一个签名 ↓↓↓
        sig = " | ".join(sorted(
            f"{call.function.name}({call.function.arguments})"
            for call in msg.tool_calls
        ))

        print(f"sig: {sig}")

        # ↓↓↓ 新增：跨轮判等检测 ↓↓↓
        if sig in turn_signatures:
            print(f"⚠️ Turn {turn} 的决策跟之前某轮完全一样，循环检测触发")
            return "循环检测：模型在反复做相同决策，已强制终止"

        turn_signatures.append(sig)

        for call in msg.tool_calls:
            # LLM 要调工具：逐个执行
            name = call.function.name
            args = json.loads(call.function.arguments) # 字符串→字典
            print(f"  🔧 调用 {name}({args})")
            result = safe_dispatch(name, args)
            print(f"  ↩️  结果: {result}")
            if "error" in result :
                reflection = llm_reflect(result)
                result=result+",反思:"+reflection['reflection']+",建议:"+reflection['decision']
                print(reflection)
                if reflection['decision'] == "stop": return "任务终止：stop"
            messages.append({                          # 结果回填给 LLM
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })


if __name__ == "__main__":
    run_agent("北京和火星的天气怎么样？")