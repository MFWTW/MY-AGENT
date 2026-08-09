import json
import re
import subprocess
import sys

from llm_client import AgentsLLM

#配置
MAX_STEPS = 5 #最多迭代轮数
CMD_TIMEOUT = 30 #命令执行超时时间，单位秒
MAX_OBS_LEN = 2000 #工具输出最多保留的字数

#工具注册表
def run_bash(cmd: str) -> str:
    """在shell执行命令，返回标准输出和标准错误"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT
        )
        output = (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        output = f"[命令超时(>{CMD_TIMEOUT}秒)]"
    except Exception as exc:
        output = f"[执行错误: {exc}]"
    return output[:MAX_OBS_LEN]  #限制输出长度

#工具注册表
TOOLS= {
    "run_bash": run_bash,
}

#系统提示词
TOOL_LIST = "\n".join(
    f"- {name}: {fn.__doc__}" for name, fn in TOOLS.items()
)

SYSTEM_PROMPT = f"""你是一个运行在终端里的 Coding Agent。

你可以调用这些工具：
{TOOL_LIST}

输出规则：
1. 每次只能输出一个 JSON 对象，不要输出任何解释文字。
2. 需要调用工具时，输出：{{"tool": "工具名", "args": {{"参数名": "值"}}}}
3. 已经完成任务时，输出：{{"answer": "最终答案"}}

示例：
{{"tool": "run_bash", "args": {{"cmd": "ls -la"}}}}
"""

#解析模型输出
def parse_llm_output(text: str):
    """从模型输出中提取 JSON，兼容 ```json 代码块和前后多余文字。"""
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end != -1:
            try:
                return json.loads(text[start: end + 1])
            except json.JSONDecodeError:
                return None
    return None

#ReAct 主循环
def run_react_loop(llm: AgentsLLM, task: str):
    """REACT主循环

    Args:
        llm (AgentsLLM): 大模型客户端
        task (str): 任务
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    
    for step in range(MAX_STEPS):
        print(f"\n=== Step {step + 1} ===")
        
        #1.1.思考:让模型输出动作
        response = llm.think(messages=messages,)
        parsed = parse_llm_output(response)
        
        #1.2.检查模型输出
        if parsed is None:
            messages.append({"role": "assistant", "content": response or ""})
            messages.append({"role": "system", "content": "[模型输出无法解析为JSON]"})
            continue
        
        #2.1:输出answer:如果模型输出了最终答案，直接返回
        if "answer" in parsed:
            print(f"\n[完成]{parsed['answer']}")
            return parsed["answer"]
        
        #3.1:输出tool:如果模型输出了工具调用，执行工具
        tool_name = parsed.get("tool")
        args = parsed.get("args") or {}
        if tool_name not in TOOLS:
            observation = (
                f"[系统]没有{tool_name!r}这个工具"
                f"可用工具:{', '.join(TOOLS)}"
            )
            
        else:
            try:
                observation = TOOLS[tool_name](**args)
            except Exception as e:
                observation = f"[系统]工具参数不正确: {e}"
        
        print(f"[观察]{observation[:300]}")  #限制输出长度
        
        #3.2:将观察结果加入消息列表，继续下一轮
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": f"[工具结果]\n{observation}"})
        
    print("\n[停止] 达到最大轮数，任务未完成。")
    return None

#入口
if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "列出当前目录下的文件"
    llm = AgentsLLM()
    run_react_loop(llm, task)