import os, json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ---------- 工具 ----------

def get_price(name: str) -> str:
    price: dict[str, str] = {
        "苹果": "3人民币1斤",
        "香蕉": "5人民币1斤",
        "火箭": "小型5000w人民币，中型1亿人民币，大型5亿人民币"
    }
    return price[name]

def get_goods_list() -> str:
    names: list[str] = ["苹果", "香蕉", "火箭"]
    return ", ".join(names)


# ---------- 工具说明书 ----------

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_price",
            "description": "获取物品价格",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "物品名称"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_goods_list",
            "description": "获取物品表单",
        },
    },
]


class RecoverableError(Exception): pass
class FatalError(Exception): pass

def safe_dispatch(name, args, max_retry=3):
    TOOL_REGISTRY = {
        "get_price": get_price,
        "get_goods_list": get_goods_list,
    }
    for attempt in range(max_retry + 1):
        try:
            return TOOL_REGISTRY[name](**args)
        except RecoverableError as e:
            if attempt == max_retry:
                return f"error 工具 {name} 重试 {max_retry} 次仍失败: {e}"
            continue
        except FatalError as e:
            print(f"Warning: 工具 {name} 不可恢复错误: {e}")
            choice = input("y = 我已人工修复，请重试；n = 终止任务: ").strip().lower()
            if choice == "y":
                try:
                    return TOOL_REGISTRY[name](**args)
                except Exception as retry_err:
                    return f"error 工具 {name} 人工修复后仍失败: {retry_err}"
            return f"error 工具 {name} 用户已终止"
        except Exception as e:
            return f"error 工具 {name} 未知错误: {e}"


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


# ---------- System Prompt ----------

SYSTEM_PROMPT = """# 身份
你是一个耐心友好的线上客服助手。你在一个 Agent 循环里工作——每轮可以看到用户的问题和工具返回的结果，然后决定下一步做什么。

# 工具使用规则
- 商品价格和商品列表必须调用对应工具获取，禁止用内置知识编造
- 允许基于工具返回的价格帮用户算账（如"苹果3元/斤，5元能买1斤多"），算术不属于内置知识禁令
- 工具返回的结果如果明显不合理（如几亿的商品），提醒用户确认，而不是直接推荐
- 工具失败 -> 立即停止尝试，如实告诉用户"系统暂时查不到，稍后再试"

# 思考流程（每步先 thought 再 action）
- 拿到用户需求后，先想：我需要查什么？是查价格还是看商品列表？
- 每次工具返回后，先想：结果合理吗？够回答用户的问题吗？
- 不调工具时，开头加 "Final Thought:" 再给最终答案

# 建议
- 当用户需要你给出建议时，你需要预构造多套方案，再选取最优方案给到客户

# 不确定性处理
- 不知道就说"目前系统没有这个信息，建议您联系人工客服"
- 禁止编造任何商品名称、价格、库存
- 用户问超出客服范围的问题（投资建议、医疗等）-> 礼貌拒绝

# 输出格式
- 语气：亲切但干脆，不啰嗦
- 开头："亲，" 结尾："还有什么疑惑可以接着问我，我一直都在~"
- 查询类回答直接列信息；推荐类回答先列候选再给简短理由

# 终止信号
- 完成：输出 Final Thought: 回答已完成，然后给出最终答案
- 无法处理：输出 Final Thought: 超出能力范围，引导联系人工客服

# 关键约束（再说一遍）
- 工具失败必须停手，不要换花样重试
- 不知道就说不知道
- 商品信息必须来自工具，禁止自己编"""


# ---------- Agent Loop ----------

def run_agent(messages: list[dict], max_turns: int = 10) -> str:
    """执行一轮 Agent 循环。messages 会就地追加（保留跨轮上下文）。"""
    turn_signatures = []
    for turn in range(max_turns):
        resp = client.chat.completions.create(
            model="deepseek-chat", messages=messages, tools=tools,
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            print(f"\n{msg.content}")
            return msg.content

        if msg.content:
            print(f"thought: {msg.content}\n")

        sig = " | ".join(sorted(
            f"{call.function.name}({call.function.arguments})"
            for call in msg.tool_calls
        ))
        print(f"sig: {sig}")

        if sig in turn_signatures:
            print(f"Turn {turn} 决策跟之前某轮完全一样，循环检测触发")
            return "循环检测：模型在反复做相同决策，已强制终止"

        turn_signatures.append(sig)

        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments)
            print(f"  Call {name}({args})")
            result = safe_dispatch(name, args)
            print(f"  Result: {result}")
            if "error" in result:
                reflection = llm_reflect(result)
                result = result + ",反思:" + reflection['reflection'] + ",建议:" + reflection['decision']
                print(reflection)
                if reflection['decision'] == "stop":
                    return "任务终止：stop"
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })


# ---------- 入口：多轮对话 REPL ----------

if __name__ == "__main__":
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("客服助手已启动。输入 exit 退出。\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit", ""):
            break
        messages.append({"role": "user", "content": user_input})
        run_agent(messages)
