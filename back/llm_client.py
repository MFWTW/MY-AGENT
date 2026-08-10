import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict

# 加载环境变量
load_dotenv()


class AgentsLLM:
    def __init__(
        self,
        model: str = None,
        api_key: str = None,
        base_url: str = None,
        timeout: int = None,
    ):
        """初始化客户端，先出入参数，若未提供从环境变量里面加载

        Args:
            model (str, optional): _description_. Defaults to None.
            api_key (str, optional): _description_. Defaults to None.
            base_url (str, optional): _description_. Defaults to None.
            timeout (int, optional): _description_. Defaults to None.
        """
        self.model = model or os.getenv("LLM_MODEL_ID")
        api_key = api_key or os.getenv("LLM_API_KEY")
        base_url = base_url or os.getenv("LLM_BASE_URL")
        timeout = timeout or int(os.getenv("LLM_TIMEOUT", 60))
        if not all([self.model, api_key, base_url]):
            raise ValueError(
                "Missing required parameters: model, api_key, or base_url."
            )

        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def think(self, messages: List[Dict[str, str]], temperature: float = 0) -> str:
        """初始化客户端，优先使用传入参数，如果没有，则从环境变量加载

        Args:
            messages (List[Dict[str, str]]): _description_
            temperature (float, optional): _description_. Defaults to 0.

        Returns:
            str: _description_
        """
        print(f"正在调用{self.model}模型进行推理...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )

            # 处理流式响应
            print("大模型响应成功")
            collected_content = []
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
                collected_content.append(content)
            print()  # 响应玩换行
            return "".join(collected_content)

        except Exception as e:
            print(f"调用大模型失败: {e}")
            return None


if __name__ == "__main__":
    llm = AgentsLLM()

    exampleMessages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that writes Python code.",
        },
        {"role": "user", "content": "写一个快速排序算法"},
    ]

    print("调用LLM")
    responseText = llm.think(messages=exampleMessages)
    if responseText:
        print("LLM返回结果：")
        print(responseText)
