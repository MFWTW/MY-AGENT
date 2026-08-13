import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import Callable, List, Dict, Optional

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
                "Missing required parameters: model, api_key, or base_url.")
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.last_error = ""
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def think(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """多轮对话请求，支持流式回调。

        Args:
            messages: OpenAI 格式的消息列表（system / user / assistant / tool 结果）。
            temperature: 采样温度。
            max_tokens: 最大生成 token 数。
            on_token: 流式回调，收到每个增量文本时调用；传入后自动启用流式。

        Returns:
            完整回答文本；模型返回空响应时返回 None。
        """
        self.last_error = ""
        stream = on_token is not None

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            "timeout": self.timeout,
        }

        if stream:
            chunks: List[str] = []
            response = self.client.chat.completions.create(**kwargs)
            for chunk in response:
                delta = chunk.choices[0].delta
                token = getattr(delta, "content", None) or ""
                if token:
                    chunks.append(token)
                    on_token(token)
            text = "".join(chunks).strip()
        else:
            response = self.client.chat.completions.create(**kwargs)
            text = (response.choices[0].message.content or "").strip()

        if not text:
            self.last_error = "模型返回了空响应"
            return None
        return text

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
