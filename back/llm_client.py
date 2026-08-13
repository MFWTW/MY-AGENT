import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import Callable, List, Dict, Optional

# 加载环境变量
# 无论从哪个目录启动，都优先加载 llm_client.py 同目录下的 .env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ===== 双配置：本地 vLLM / 云端 OpenAI 兼容 API =====
PROFILES = ("local", "api")
PROFILE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "storage_text",
    "active_profile.txt",
)

_PROFILE_VARS = {
    "local": {
        "base_url": "LLM_BASE_URL",
        "model": "LLM_MODEL_ID",
        "api_key": "LLM_API_KEY",
        "timeout": "LLM_TIMEOUT",
        "model_dir": "LOCAL_MODEL_DIR",
    },
    "api": {
        "base_url": "API_BASE_URL",
        "model": "API_MODEL_ID",
        "api_key": "API_API_KEY",
        "timeout": "API_TIMEOUT",
    },
}

_PROFILE_LABELS = {
    "local": "本地模型",
    "api": "API 模型",
}


def get_active_profile() -> str:
    """返回当前生效的配置：local 或 api"""
    profile = os.getenv("AGENT_PROFILE", "").strip().lower()
    if profile not in PROFILES:
        profile = ""
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                profile = f.read().strip().lower()
        except (OSError, IOError):
            profile = ""
    return profile if profile in PROFILES else "local"


def set_active_profile(profile: str) -> str:
    """切换配置并持久化，返回切换后的 profile"""
    profile = (profile or "").strip().lower()
    if profile not in PROFILES:
        raise ValueError("profile 必须是 'local' 或 'api'")
    os.environ["AGENT_PROFILE"] = profile
    os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        f.write(profile)
    return profile


def get_profile_config(profile: str = None) -> dict:
    """读取某个配置的实际参数"""
    profile = profile or get_active_profile()
    if profile not in PROFILES:
        profile = "local"
    vars_map = _PROFILE_VARS[profile]
    return {
        "profile": profile,
        "label": _PROFILE_LABELS[profile],
        "model": os.getenv(vars_map["model"], ""),
        "base_url": os.getenv(vars_map["base_url"], ""),
        "api_key": os.getenv(vars_map["api_key"], ""),
        "timeout": os.getenv(vars_map["timeout"], "60"),
        "model_dir": os.getenv(vars_map.get("model_dir", ""), ""),
    }


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_local_model_dir() -> str:
    return os.path.join(_project_root(), "Qwen2.5-Coder-7B-Instruct-AWQ")


def is_model_dir(path: str) -> bool:
    """判断目录是否像本地模型：config.json + 权重文件"""
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        return False
    if not os.path.isfile(os.path.join(path, "config.json")):
        return False
    try:
        names = os.listdir(path)
    except OSError:
        return False
    return any(
        name.endswith((".safetensors", ".bin", ".gguf", ".pt", ".pth"))
        for name in names
    )


def get_local_model_dir() -> str:
    """返回本地模型目录：优先 LOCAL_MODEL_DIR，否则项目默认路径"""
    cfg = get_profile_config("local")
    model_dir = cfg.get("model_dir", "").strip()
    return model_dir or _default_local_model_dir()


def has_local_model() -> bool:
    return is_model_dir(get_local_model_dir())


def has_api_config() -> bool:
    cfg = get_profile_config("api")
    return bool(
        cfg["base_url"]
        and cfg["model"]
        and cfg["api_key"]
        and "请替换" not in cfg["api_key"]
    )


def has_model_config() -> bool:
    """是否已有可用模型：本地模型目录存在，或 API 配置完整"""
    return has_local_model() or has_api_config()


def update_env_file(key: str, value: str) -> None:
    """写入 back/.env（更新或追加），并同步到当前进程环境变量"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    prefix = f"{key}="
    new_line = f'{key}="{value}"\n'
    replaced = False
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) or stripped.startswith(f"# {prefix}"):
            out.append(new_line)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(new_line)

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(out)
    os.environ[key] = str(value)


def save_local_model(model_dir: str) -> str:
    """保存本地模型路径，并把当前配置切到 local"""
    model_dir = os.path.abspath(os.path.expanduser(str(model_dir).strip().strip('"')))
    if not is_model_dir(model_dir):
        raise ValueError(
            f"该目录不是有效模型目录: {model_dir}\n需要包含 config.json 和权重文件"
        )
    model_name = os.path.basename(model_dir.rstrip("/\\"))
    update_env_file("LOCAL_MODEL_DIR", model_dir)
    update_env_file("LLM_MODEL_ID", model_name)
    update_env_file("LLM_BASE_URL", "http://localhost:8000/v1")
    update_env_file("LLM_API_KEY", "sk-local-vllm")
    update_env_file("LLM_TIMEOUT", "30")
    set_active_profile("local")
    return model_dir


def save_api_config(
    base_url: str,
    model_id: str,
    api_key: str,
    timeout: str = "60",
) -> None:
    """保存 OpenAI 兼容 API 配置，并把当前配置切到 api"""
    base_url = str(base_url or "").strip()
    model_id = str(model_id or "").strip()
    api_key = str(api_key or "").strip()
    timeout = str(timeout or "60").strip()
    if not all([base_url, model_id, api_key]):
        raise ValueError("API Base URL、模型 ID、API Key 都不能为空")
    update_env_file("API_BASE_URL", base_url)
    update_env_file("API_MODEL_ID", model_id)
    update_env_file("API_API_KEY", api_key)
    update_env_file("API_TIMEOUT", timeout)
    set_active_profile("api")


def find_local_model_dirs(
    root: str = None,
    max_depth: int = 4,
    max_results: int = 20,
) -> list:
    """在项目目录内检索可能的本地模型目录"""
    root = os.path.abspath(
        os.path.expanduser(root or _project_root())
    )
    if not os.path.isdir(root):
        return []
    root_depth = root.rstrip(os.sep).count(os.sep)
    results = []
    skip_dirs = {
        ".git",
        "node_modules",
        "__pycache__",
        "docs",
        "knowledge_base",
        "logs",
        "storage",
        "storage_text",
        ".venv",
        "venv",
    }
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.count(os.sep) - root_depth
        if depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        if is_model_dir(dirpath):
            results.append(dirpath)
            if len(results) >= max_results:
                break
    return results


class AgentsLLM:
    def __init__(
        self,
        model: str = None,
        api_key: str = None,
        base_url: str = None,
        timeout: int = None,
        profile: str = None,
    ):
        """初始化客户端，先出入参数，若未提供从环境变量里面加载

        Args:
            model (str, optional): _description_. Defaults to None.
            api_key (str, optional): _description_. Defaults to None.
            base_url (str, optional): _description_. Defaults to None.
            timeout (int, optional): _description_. Defaults to None.
            profile (str, optional): local=本地 vLLM，api=云端 API。
        """
        self.profile = (profile or get_active_profile()).strip().lower()
        if self.profile not in PROFILES:
            self.profile = "local"
        config = get_profile_config(self.profile)
        self.model = model or config["model"]
        api_key = api_key or config["api_key"]
        base_url = base_url or config["base_url"]
        timeout = timeout or int(config["timeout"] or 60)
        if not all([self.model, api_key, base_url]):
            raise ValueError(
                f"配置 '{self.profile}' 缺少参数: model, api_key, base_url。"
                "请检查 back/.env 中的 LLM_* 或 API_* 配置。"
            )
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
