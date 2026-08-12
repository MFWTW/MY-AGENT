import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import Callable, List, Dict

# 加载环境变量
# 无论从哪个目录启动，都优先加载 llm_client.py 同目录下的 .env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


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
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def process_request(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            timeout=self.timeout
        )
        return response.choices[0].message.content.strip()

if __name__ == '__main__':
    llm = AgentsLLM()
    result = llm.process_request('Hello, how are you?')
    print(result)
