"""Codex CLI 风格终端前端：Textual 实现。

支持两种模式：
- Agent 模式（默认）：调用 back/ReAct.py，实时展示思考 / 工具调用 / 观察结果 / 最终答案。
- 对话模式：调用 back/llm_client.py，直接与 LLM 流式对话。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple, Type

from dotenv import load_dotenv
from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.suggester import Suggester
from textual.widgets import Collapsible, Footer, Header, Input, Static

BACK_DIR = Path(__file__).resolve().parent.parent / "back"
PROJECT_DIR = BACK_DIR.parent
load_dotenv(BACK_DIR / ".env")

WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE") or PROJECT_DIR)

THINK_COLLAPSE_THRESHOLD = 1000  # 思考过程超过该字数就折叠成小框


WELCOME = """[bold cyan]🤖 Codex 终端[/bold cyan]
[dim]本地 Coding Agent · Textual 前端[/dim]
[dim]输入任务开始执行，输入 / 有命令提示，Ctrl+C 复制选中文本，Ctrl+D 退出[/dim]"""

HELP_TEXT = """[bold cyan]/help[/]      显示本帮助
[bold cyan]/clear[/]     清空当前对话
[bold cyan]/agent[/]     切换到 Agent 模式（工具调用 + ReAct）
[bold cyan]/chat[/]      切换到对话模式（直接 LLM 流式对话）
[bold cyan]/model[/]     查看当前模型配置
[bold cyan]/api[/]       切换到 API 模型
[bold cyan]/local[/]     切换到本地模型
[bold cyan]/switch[/]    切换模型，如 /switch api
[bold cyan]/import-local[/] 扫描并导入本地模型
[bold cyan]/config-api[/]   配置云端 API
[bold cyan]/cancel[/]       取消当前配置
[bold cyan]/pwd[/]       查看当前所在项目目录
[bold cyan]/again[/]     重新执行上一条任务
[bold cyan]/stop[/]      停止当前任务（或 Ctrl+X）
[bold cyan]/quit[/]      退出（或 Ctrl+D）"""

CHAT_SYSTEM = (
    "你是一个运行在终端里的 AI 编程助手。"
    "请用中文回答，代码示例保持简洁，涉及文件操作时给出可执行的命令。"
)


class _AgentCancelled(Exception):
    """用户主动停止任务时抛出，用于穿透 LLM 流式调用。"""


COMMAND_SUGGESTIONS = [
    "/help",
    "/clear",
    "/agent",
    "/chat",
    "/model",
    "/api",
    "/local",
    "/switch api",
    "/switch local",
    "/import-local",
    "/config-api",
    "/cancel",
    "/again",
    "/pwd",
    "/stop",
    "/quit",
]


class CommandSuggester(Suggester):
    """输入 / 开头时，提示可用的命令"""

    def __init__(self, enabled) -> None:
        super().__init__(case_sensitive=False)
        self._enabled = enabled

    async def get_suggestion(self, value: str) -> str | None:
        if not self._enabled() or not value.startswith("/"):
            return None
        for cmd in COMMAND_SUGGESTIONS:
            if cmd.startswith(value):
                return cmd
        return None


class CodexApp(App):
    """Codex 风格终端应用"""

    TITLE = "Codex"
    SUB_TITLE = "本地 Coding Agent · ReAct"
    background = "transparent"

    BINDINGS = [
        # Ctrl+C 保留 Textual 默认的“复制选中文本”，不再退出
        # Ctrl+Q 在 VS Code 终端里会被编辑器拦截，所以退出改用 Ctrl+D
        Binding("ctrl+d", "quit", "退出", priority=True),
        Binding("ctrl+x", "stop", "停止", priority=True),
        Binding("ctrl+l", "clear", "清空"),
        Binding("ctrl+t", "toggle_mode", "切换模式"),
    ]

    CSS = """
    Screen {
        background: #0d1117;
        color: #e6edf3;
    }

    #layout {
        height: 1fr;
        background: #0d1117;
    }

    #messages {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
        background: #0d1117;
    }

    #bottom_bar {
        dock: bottom;
        height: 4;
        background: #161b22;
        border-top: solid #30363d;
    }

    #status {
        height: 1;
        padding: 0 2;
        background: #161b22;
        color: #8b949e;
    }

    #prompt_row {
        height: 1;
        padding: 0 2;
        align-vertical: middle;
    }

    #prompt_symbol {
        width: 3;
        content-align: right middle;
        color: #a371f7;
        text-style: bold;
    }

    #prompt {
        width: 1fr;
        height: 1;
        min-height: 1;
        max-height: 1;
        border: none;
        background: transparent;
        color: #e6edf3;
    }

    #prompt:focus {
        border: none;
    }

    Header {
        background: #161b22;
        color: #e6edf3;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }

    Static {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    .welcome-msg {
        margin: 1 0 2 0;
        padding: 1;
        border-left: tall #a371f7;
    }

    .user-msg {
        background: #161b22;
        border-left: tall #a371f7;
    }

    .assistant-msg {
        background: #0d1117;
        border-left: tall #58a6ff;
    }

    .tool-msg {
        background: #1c2128;
        border-left: tall #d29922;
    }

    .obs-msg {
        background: #10151b;
        border-left: tall #8b949e;
        color: #8b949e;
    }

    .warn-msg {
        background: #2d1d0f;
        border-left: tall #d29922;
        color: #d29922;
    }

    .error-msg {
        background: #2d1517;
        border-left: tall #ff7b72;
        color: #ff7b72;
    }

    .step-msg {
        color: #58a6ff;
    }

    .log-msg {
        color: #6e7681;
    }

    .thinking-msg {
        color: #8b949e;
    }

    .thinking-collapsible {
        margin: 0 0 1 0;
        padding: 0;
        background: #10151b;
        border: none;
        border-left: tall #8b949e;
    }

    .thinking-collapsible > CollapsibleTitle {
        color: #8b949e;
        padding: 0 1;
    }

    .thinking-detail {
        margin: 0;
        padding: 0 1;
        color: #8b949e;
    }

    """

    mode: str = "agent"
    busy: bool = False
    last_task: str = ""
    chat_messages: List[dict] = []

    def __init__(self) -> None:
        super().__init__()
        self._backend: Optional[Tuple[Type, object, int]] = None
        self._worker: Optional[threading.Thread] = None
        self._cancel_event = threading.Event()
        self._thinking_widget: Optional[Static] = None
        self._think_buffer: List[str] = []
        self._chat_widget: Optional[Static] = None
        self._chat_buffer: List[str] = []
        self.step_no = 0
        self.messages: Optional[VerticalScroll] = None
        self.status_bar: Optional[Static] = None
        self.prompt: Optional[Input] = None
        self._confirm_event = threading.Event()
        self._pending_confirm = None  # 等待确认的命令
        self._confirm_result = False
        self._llm_profile: Optional[str] = None  # local / api
        self._setup_step: Optional[str] = None
        self._setup_data: dict = {}
        self._setup_scan_results: List[str] = []
        self._command_suggester = CommandSuggester(
            lambda: self._setup_step is None
        )
        # 注册到后端模块
        try:
            from ReAct import CONFIRM_CALLBACK

            # 用模块全局变量注册（ReAct 在 back 目录，需要已 import）
        except Exception:
            pass

    # ---------- 界面 ----------

    def compose(self) -> ComposeResult:
        """组装界面：Header(顶) + 消息区(中) + 状态栏/输入框(底)"""
        yield Header(show_clock=True)
        with Vertical(id="layout"):
            with VerticalScroll(id="messages"):
                yield Static(WELCOME, markup=True, classes="welcome-msg")
            with Container(id="bottom_bar"):
                with Horizontal(id="prompt_row"):
                    yield Static("❯", id="prompt_symbol", markup=False)
                    yield Input(
                        placeholder="输入任务，输入 / 查看命令提示",
                        id="prompt",
                        suggester=self._command_suggester,
                    )
                yield Static("", id="status", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.messages = self.query_one("#messages", VerticalScroll)
        self.status_bar = self.query_one("#status", Static)
        self.prompt = self.query_one("#prompt", Input)
        self._set_status()
        try:
            self._import_backend()
        except Exception:
            pass
        self._set_status()
        self._check_first_run()
        self.prompt.focus()

    # ---------- 输入与命令 ----------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.prompt.value = ""
        # ===== 人工确认：等待 y/n =====
        if self._pending_confirm is not None:
            self._confirm_result = text.lower() in ("y", "yes")
            self._pending_confirm = None
            self.prompt.placeholder = (
                "输入任务，输入 / 查看命令提示"
                if self.mode == "agent"
                else "输入问题，输入 / 查看命令提示"
            )
            self._confirm_event.set()
            self._set_status()
            return
        if self._setup_step is not None:
            self._handle_setup_input(text)
            return
        if not text:
            return
        if text.startswith("/"):
            self._handle_command(text)
            return
        if self.busy:
            self.notify("正在处理中，按 Ctrl+X 停止", severity="warning", timeout=3)
            return
        self._submit(text)

    def _handle_command(self, text: str) -> None:
        cmd = text.partition(" ")[0]

        if cmd in ("/help", "/?"):
            self._mount(Static(HELP_TEXT, markup=True, classes="log-msg"))
        elif cmd == "/clear":
            self._clear_messages()
        elif cmd == "/chat":
            self._switch_mode("chat")
        elif cmd == "/agent":
            self._switch_mode("agent")
        elif cmd == "/model":
            self._show_model_info()
        elif cmd == "/api":
            self._switch_profile("api")
        elif cmd == "/local":
            self._switch_profile("local")
        elif cmd == "/switch":
            arg = text.partition(" ")[2].strip().lower()
            if arg in ("api", "local"):
                self._switch_profile(arg)
            else:
                self._mount(
                    Static(
                        "[#d29922]用法: /switch api 或 /switch local[/]",
                        classes="warn-msg",
                    )
                )
        elif cmd == "/import-local":
            arg = text.partition(" ")[2].strip()
            self._start_local_import(arg or None)
        elif cmd == "/config-api":
            self._start_api_config()
        elif cmd == "/cancel":
            self._cancel_setup()
        elif cmd == "/pwd":
            self._mount(
                Static(
                    f"[dim]当前目录: {escape(str(WORKSPACE))}[/]",
                    classes="log-msg",
                )
            )
        elif cmd == "/again":
            if self.busy:
                self.notify("正在处理中，不能重跑", severity="warning", timeout=3)
            elif self.last_task:
                self._submit(self.last_task)
            else:
                self._mount(Static("[red]还没有可重跑的任务[/]", classes="error-msg"))
        elif cmd == "/stop":
            self._stop()
        elif cmd in ("/quit", "/exit"):
            self.exit()
        else:
            self._mount(
                Static(
                    f"[#d29922]未知命令 {escape(cmd)}，输入 /help 查看帮助[/]",
                    classes="warn-msg",
                )
            )

    def _submit(self, text: str) -> None:
        self.last_task = text
        self._add_user(text)
        self._set_busy(True)
        self._cancel_event.clear()
        if self.mode == "chat":
            target = self.run_chat
        else:
            target = self.run_agent
        self._worker = threading.Thread(
            target=target,
            args=(text,),
            name="codex-worker",
            daemon=True,
        )
        self._worker.start()

    def _clear_messages(self) -> None:
        if self.busy:
            self.notify(
                "处理中不能清空，先按 Ctrl+X 停止", severity="warning", timeout=3
            )
            return
        for widget in list(self.messages.children):
            widget.remove()
        self.chat_messages = []
        self._thinking_widget = None
        self._think_buffer.clear()
        self._chat_widget = None
        self._chat_buffer.clear()
        self._mount(Static(WELCOME, markup=True, classes="welcome-msg"))

    def _switch_mode(self, mode: str) -> None:
        if self.busy:
            self.notify("处理中不能切换模式", severity="warning", timeout=3)
            return
        self.mode = mode
        self.prompt.placeholder = (
            "输入任务，输入 / 查看命令提示"
            if mode == "agent"
            else "输入问题，输入 / 查看命令提示"
        )
        self._set_status()
        self._mount(
            Static(
                f"[dim]已切换到 {'Agent 模式' if mode == 'agent' else '对话模式'}[/]",
                classes="log-msg",
            )
        )
        self.prompt.focus()

    def _stop(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._cancel_event.set()
            self._mount(
                Static("[#d29922]已请求停止，等待当前请求返回…[/]", classes="warn-msg")
            )
        elif self.busy:
            self.notify("正在等待请求返回", severity="warning", timeout=3)

    def _show_model_info(self) -> None:
        try:
            self._import_backend()
        except Exception as exc:
            self._mount(
                Static(f"[red]后端导入失败：{escape(str(exc))}[/]", classes="error-msg")
            )
            return
        self._mount(
            Static(
                f"[dim]{escape(self._model_info_text())}[/]",
                classes="log-msg",
            )
        )

    def _switch_profile(self, profile: str) -> None:
        """在本地模型与 API 之间切换"""
        if self.busy:
            self.notify("正在处理中，不能切换模型", severity="warning", timeout=3)
            return
        try:
            self._import_backend()
            from llm_client import (
                AgentsLLM,
                get_profile_config,
                has_api_config,
                has_local_model,
                set_active_profile,
            )

            # 配置还没填好时，直接打开对应的配置向导，而不是报错
            if profile == "api" and not has_api_config():
                self._mount(
                    Static(
                        "[#d29922]API 尚未配置，正在打开 API 配置向导…[/]",
                        classes="warn-msg",
                    )
                )
                self._start_api_config()
                return
            if profile == "local" and not has_local_model():
                self._mount(
                    Static(
                        "[#d29922]本地模型尚未导入，正在打开模型导入向导…[/]",
                        classes="warn-msg",
                    )
                )
                self._start_local_import()
                return

            AgentsLLM(profile=profile)  # 最后校验参数完整
            set_active_profile(profile)
            self._llm_profile = profile
            cfg = get_profile_config(profile)
            self._mount(
                Static(
                    f"[dim]已切换到 {cfg['label']}: {cfg['model']} · {cfg['base_url']}[/]",
                    classes="log-msg",
                )
            )
            self._set_status()
            self.prompt.focus()
        except Exception as exc:
            self._mount(
                Static(f"[red]切换失败：{escape(str(exc))}[/]", classes="error-msg")
            )

    # ---------- 首次配置向导 ----------

    def _check_first_run(self) -> None:
        """没有可用模型时，提示用户先导入本地模型或配置 API"""
        if self._backend is None:
            return
        try:
            from llm_client import has_model_config

            if not has_model_config():
                self._mount(
                    Static(
                        "[bold #d29922]首次使用[/]\n"
                        "还没有可用模型，请选择：\n"
                        "  [bold]/import-local[/]  扫描项目目录并导入本地模型\n"
                        "  [bold]/config-api[/]    配置云端 API\n"
                        "配置成功后可用 /local 和 /api 来回切换",
                        classes="warn-msg",
                    )
                )
        except Exception:
            pass

    def _start_local_import(self, path_arg: Optional[str] = None) -> None:
        """开始导入本地模型：可直接带路径，也可以扫描项目目录"""
        if self.busy:
            self.notify("正在处理中，不能导入模型", severity="warning", timeout=3)
            return
        try:
            self._import_backend()
            from llm_client import save_local_model

            if path_arg:
                model_dir = save_local_model(path_arg)
                self._finish_setup(
                    f"本地模型已导入：{model_dir}\n"
                    "已保存到 back/.env，当前使用本地模型。\n"
                    "若 vLLM 未启动，重启 myagent 后会自动拉起。"
                )
                return

            self._setup_step = "local_path"
            self._setup_data = {}
            self._setup_scan_results = []
            self.prompt.placeholder = "输入本地模型绝对路径，或输入 scan 自动检索"
            self._mount(
                Static(
                    "[#d29922]导入本地模型[/]\n"
                    "输入模型目录的绝对路径，例如：\n"
                    "[dim]/mnt/e/models/Qwen2.5-Coder-7B-Instruct-AWQ[/]\n"
                    "也可以输入 [bold]scan[/] 自动扫描项目目录；输入 /cancel 取消",
                    classes="warn-msg",
                )
            )
            self.prompt.focus()
        except Exception as exc:
            self._mount(
                Static(f"[red]导入失败：{escape(str(exc))}[/]", classes="error-msg")
            )

    def _start_api_config(self) -> None:
        """开始交互式配置云端 API"""
        if self.busy:
            self.notify("正在处理中，不能配置 API", severity="warning", timeout=3)
            return
        try:
            self._import_backend()
            self._setup_step = "api_base_url"
            self._setup_data = {}
            self._setup_scan_results = []
            self.prompt.placeholder = "输入 API Base URL"
            self._mount(
                Static(
                    "[#d29922]配置云端 API[/]\n"
                    "输入 OpenAI 兼容 API 地址，例如：\n"
                    "[dim]https://api.deepseek.com/v1[/]\n"
                    "输入 /cancel 取消",
                    classes="warn-msg",
                )
            )
            self.prompt.focus()
        except Exception as exc:
            self._mount(
                Static(f"[red]配置失败：{escape(str(exc))}[/]", classes="error-msg")
            )

    def _handle_setup_input(self, text: str) -> None:
        """处理配置向导中的逐步输入"""
        text = text.strip()
        if text.lower() == "/cancel":
            self._cancel_setup()
            return
        step = self._setup_step
        if not text and step != "api_timeout":
            self.notify("输入不能为空", severity="warning", timeout=3)
            return

        if step == "local_path":
            self._handle_local_setup_input(text)
        elif step == "api_base_url":
            if not text.startswith(("http://", "https://")):
                self._mount(
                    Static(
                        "[red]这不是有效的 API Base URL[/]\n"
                        "请输入以 http:// 或 https:// 开头的地址，"
                        "例如 https://api.deepseek.com/v1；不要粘贴 API Key",
                        classes="error-msg",
                    )
                )
                return
            self._setup_data["base_url"] = text
            self._setup_step = "api_model_id"
            self.prompt.placeholder = "输入模型 ID"
            self._mount(
                Static(f"[dim]API Base URL: {escape(text)}[/]", classes="log-msg")
            )
            self._mount(
                Static(
                    "[#d29922]下一步[/]\n输入模型 ID，例如 [bold]deepseek-chat[/]",
                    classes="warn-msg",
                )
            )
            self.prompt.focus()
        elif step == "api_model_id":
            self._setup_data["model_id"] = text
            self._setup_step = "api_api_key"
            self.prompt.password = True
            self.prompt.placeholder = "输入 API Key"
            self._mount(
                Static(
                    f"[dim]模型 ID: {escape(text)}[/]",
                    classes="log-msg",
                )
            )
            self._mount(
                Static(
                    "[#d29922]下一步[/]\n输入 API Key（只保存在本地 back/.env）",
                    classes="warn-msg",
                )
            )
            self.prompt.focus()
        elif step == "api_api_key":
            self._setup_data["api_key"] = text
            self._setup_step = "api_timeout"
            self.prompt.password = False
            self.prompt.placeholder = "输入超时秒数（默认 60）"
            self._mount(
                Static("[#d29922]下一步[/]\n输入超时秒数，直接回车使用 60", classes="warn-msg")
            )
            self.prompt.focus()
        elif step == "api_timeout":
            try:
                from llm_client import save_api_config

                save_api_config(
                    self._setup_data["base_url"],
                    self._setup_data["model_id"],
                    self._setup_data["api_key"],
                    text or "60",
                )
                self._finish_setup("API 配置已保存，当前已切换到 API 模型")
            except Exception as exc:
                self._mount(
                    Static(
                        f"[red]保存失败：{escape(str(exc))}[/]",
                        classes="error-msg",
                    )
                )

    def _handle_local_setup_input(self, text: str) -> None:
        """处理本地模型路径输入 / 项目目录扫描"""
        try:
            from llm_client import find_local_model_dirs, save_local_model

            if text.lower() == "scan":
                results = find_local_model_dirs()
                self._setup_scan_results = results
                if not results:
                    self._mount(
                        Static(
                            "[#d29922]项目目录中未找到模型，请直接输入完整路径[/]",
                            classes="warn-msg",
                        )
                    )
                    self.prompt.placeholder = "输入本地模型绝对路径"
                    return
                lines = [f"  [bold]{i + 1}[/]. {p}" for i, p in enumerate(results)]
                self._mount(
                    Static(
                        "扫描到以下模型目录：\n"
                        + "\n".join(lines)
                        + "\n输入序号或完整路径即可导入",
                        classes="log-msg",
                    )
                )
                self.prompt.placeholder = "输入序号或模型绝对路径"
                return

            if text.isdigit() and self._setup_scan_results:
                idx = int(text) - 1
                if 0 <= idx < len(self._setup_scan_results):
                    text = self._setup_scan_results[idx]

            model_dir = save_local_model(text)
            self._finish_setup(
                f"本地模型已导入：{model_dir}\n"
                "已保存到 back/.env，当前使用本地模型。\n"
                "若 vLLM 未启动，重启 myagent 后会自动拉起。"
            )
        except Exception as exc:
            self._mount(
                Static(f"[red]导入失败：{escape(str(exc))}[/]", classes="error-msg")
            )

    def _cancel_setup(self) -> None:
        """取消当前配置向导"""
        self._setup_step = None
        self._setup_data = {}
        self._setup_scan_results = []
        self.prompt.password = False
        self.prompt.placeholder = (
            "输入任务，输入 / 查看命令提示"
            if self.mode == "agent"
            else "输入问题，输入 / 查看命令提示"
        )
        self._set_status()
        self._mount(Static("[#d29922]已取消配置[/]", classes="warn-msg"))
        self.prompt.focus()

    def _finish_setup(self, message: str) -> None:
        """配置完成：清理向导状态并刷新界面"""
        from llm_client import get_active_profile

        self._setup_step = None
        self._setup_data = {}
        self._setup_scan_results = []
        self.prompt.password = False
        self._llm_profile = get_active_profile()
        self.prompt.placeholder = (
            "输入任务，输入 / 查看命令提示"
            if self.mode == "agent"
            else "输入问题，输入 / 查看命令提示"
        )
        self._set_status()
        self._mount(
            Static(f"[bold green]✅ {escape(message)}[/]", classes="assistant-msg")
        )
        self.prompt.focus()

    # ---------- 状态 ----------

    def _model_info_text(self) -> str:
        """读取当前配置的模型与 API 地址（不显示密钥）"""
        try:
            from llm_client import get_profile_config

            cfg = get_profile_config(self._llm_profile or "local")
        except Exception:
            cfg = {
                "label": "本地模型",
                "model": os.getenv("LLM_MODEL_ID", ""),
                "base_url": os.getenv("LLM_BASE_URL", ""),
            }
        model = cfg.get("model") or "(未设置)"
        base_url = cfg.get("base_url") or "(未设置)"
        # 本地 vLLM 的模型 ID 常常是一整条路径，这里只显示最后一段
        short_model = model.replace("\\", "/").rstrip("/").split("/")[-1]
        short_api = base_url.replace("http://", "").replace("https://", "").rstrip("/")
        return f"{cfg.get('label', '模型')}: {short_model} · API: {short_api}"

    def _compact_model_info(self) -> str:
        """状态栏用的紧凑版：模型名截断，API 只显示 host:port"""
        try:
            from llm_client import get_profile_config

            cfg = get_profile_config(self._llm_profile or "local")
        except Exception:
            cfg = {
                "label": "本地模型",
                "model": os.getenv("LLM_MODEL_ID", ""),
                "base_url": os.getenv("LLM_BASE_URL", ""),
            }
        model = cfg.get("model") or "(未设置)"
        base_url = cfg.get("base_url") or "(未设置)"
        short_model = model.replace("\\", "/").rstrip("/").split("/")[-1]
        if len(short_model) > 12:
            short_model = short_model[:12] + "…"
        api_host = (
            base_url.replace("http://", "")
            .replace("https://", "")
            .rstrip("/")
            .split("/")[0]
        )
        return f"{cfg.get('label', '模型')}: {short_model} · {api_host}"

    def _set_status(self, extra: str = "") -> None:
        if self.status_bar is None:
            return
        mode_label = "Agent" if self.mode == "agent" else "对话"
        if self.busy:
            dot = "[#d29922]●[/]"
            state = "处理中"
        else:
            dot = "[#3fb950]●[/]"
            state = "就绪"
        text = f"{dot} {state} · {mode_label}"
        if extra:
            text += f" · {extra}"
        text += f" · 📁 {WORKSPACE.name}"
        text += f" · {self._compact_model_info()}"
        self.status_bar.update(text)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if busy:
            self._set_status("等待模型…")
        else:
            self.step_no = 0
            self._worker = None
            self._set_status()

    def _ui(self, func, *args, **kwargs) -> None:
        """从工作线程安全地切回 UI 线程执行"""
        try:
            self.call_from_thread(func, *args, **kwargs)
        except RuntimeError:
            # 应用已退出，后台守护线程还在收尾时忽略 UI 更新
            pass

    # ---------- 消息渲染 ----------

    def _mount(self, widget) -> None:
        self.messages.mount(widget)
        self._scroll_end()

    def _scroll_end(self) -> None:
        self.messages.scroll_end(animate=False)

    def _add_user(self, text: str) -> None:
        self._mount(
            Static(
                f"[bold #a371f7]❯[/] {escape(text)}", markup=True, classes="user-msg"
            )
        )

    def _add_step(self, step: int) -> None:
        self._mount(Static(f"[bold cyan]── Step {step} ──[/]", classes="step-msg"))

    def _add_log(self, msg: str) -> None:
        self._mount(Static(f"[dim]ℹ {escape(msg)}[/]", classes="log-msg"))

    def _add_tool(self, tool: str, args: dict) -> None:
        try:
            args_text = json.dumps(args, ensure_ascii=False)
        except Exception:
            args_text = str(args)
        self._mount(
            Static(
                f"[bold #d29922]🔧 {escape(tool)}[/] [dim]{escape(args_text)}[/]",
                classes="tool-msg",
            )
        )

    def _add_observation(self, observation: str) -> None:
        preview = observation
        if len(preview) > 900:
            preview = preview[:900] + "\n… (输出过长，已截断)"
        self._mount(Static(f"[dim]📥 {escape(preview)}[/]", classes="obs-msg"))

    def _add_warn(self, msg: str) -> None:
        self._mount(Static(f"[#d29922]⚠ {escape(msg)}[/]", classes="warn-msg"))

    def _add_error(self, msg: str) -> None:
        self._mount(Static(f"[bold red]✗[/] {escape(msg)}", classes="error-msg"))

    def _add_answer(self, answer: str) -> None:
        self._mount(
            Static(f"[bold green]✅ 完成[/]\n{escape(answer)}", classes="assistant-msg")
        )

    # ---------- Agent 模式：思考区 ----------

    def _ensure_thinking(self) -> None:
        if self._thinking_widget is None:
            self._thinking_widget = Static(
                "[dim]🤔 模型思考中…[/]", classes="thinking-msg"
            )
            self._mount(self._thinking_widget)

    def _update_thinking(self, raw: str) -> None:
        widget = self._thinking_widget
        if widget is None:
            return
        preview = raw.strip()
        if len(preview) > 400:
            preview = preview[:400] + "…"
        widget.update(f"[dim]🧠 {escape(preview)}[/]")
        self._scroll_end()

    def _finish_thinking(self) -> None:
        """把本次思考过程收尾：超过阈值时折叠成可点击展开的小框"""
        raw = "".join(self._think_buffer).strip()
        widget = self._thinking_widget
        self._thinking_widget = None
        self._think_buffer.clear()
        if widget is not None:
            widget.remove()
        if not raw:
            return

        if len(raw) > THINK_COLLAPSE_THRESHOLD:
            collapsible = Collapsible(
                Static(raw, markup=False, classes="thinking-detail"),
                title=f"🧠 思考过程（{len(raw)} 字）",
                collapsed=True,
                classes="thinking-collapsible",
            )
            self._mount(collapsible)
        else:
            self._mount(
                Static(
                    f"[dim]🧠 思考：{escape(raw)}[/]",
                    classes="thinking-msg",
                )
            )

    # ---------- 后端调用 ----------

    def _import_backend(self) -> Tuple[Type, object, int]:
        if self._backend is None:
            back_dir = Path(__file__).resolve().parent.parent / "back"
            if str(back_dir) not in sys.path:
                sys.path.insert(0, str(back_dir))
            from llm_client import AgentsLLM, get_active_profile
            from ReAct import MAX_STEPS, run_react_loop
            import ReAct

            # ===== 后端导入时绑定人工确认回调 =====
            ReAct.CONFIRM_CALLBACK = self._handle_confirm
            ReAct.CONFIRM_ENABLED = True
            self._llm_profile = get_active_profile()

            self._backend = (AgentsLLM, run_react_loop, MAX_STEPS)
        return self._backend

    # ---------- 本地 vLLM 自动拉起 ----------

    def _local_api_ready(self) -> bool:
        """探测本地 vLLM 是否已就绪"""
        try:
            from llm_client import get_profile_config

            base_url = (
                get_profile_config("local").get("base_url")
                or "http://localhost:8000/v1"
            )
            url = base_url.rstrip("/") + "/models"
            with urllib.request.urlopen(url, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _start_local_vllm(self) -> subprocess.Popen:
        """后台启动本地 vLLM 服务"""
        script = PROJECT_DIR / "back" / "vllm_server" / "start.sh"
        return subprocess.Popen(
            ["bash", str(script)],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _ensure_local_vllm(self) -> None:
        """确保本地 vLLM 已就绪；未运行则自动启动并等待"""
        if self._local_api_ready():
            return
        self._ui(
            self._add_log,
            "本地 vLLM 未运行，正在后台启动（首次约 2~3 分钟）...",
        )
        proc = self._start_local_vllm()
        deadline = time.time() + 300
        while time.time() < deadline:
            if self._cancel_event.is_set():
                raise _AgentCancelled()
            time.sleep(3)
            if self._local_api_ready():
                self._ui(self._add_log, "本地 vLLM 已就绪")
                return
            if proc.poll() is not None:
                raise RuntimeError(
                    "本地 vLLM 进程已退出，请查看 logs/vllm.log"
                )
        raise RuntimeError("本地 vLLM 启动超时，请查看 logs/vllm.log")

    def run_agent(self, task: str) -> None:
        """Agent 模式：跑 ReAct 主循环，把事件实时投递到界面"""
        try:
            AgentsLLM, run_react_loop, _ = self._import_backend()
            if (self._llm_profile or "local") == "local":
                self._ensure_local_vllm()
            llm = AgentsLLM(profile=self._llm_profile)
            hooks = {
                "on_step": self._agent_step,
                "on_log": self._agent_log,
                "on_token": self._agent_token,
                "on_tool": self._agent_tool,
                "on_observe": self._agent_observe,
                "on_warn": self._agent_warn,
                "on_answer": self._agent_answer,
                "on_stop": self._agent_stop,
            }
            run_react_loop(llm, task, hooks=hooks)
        except _AgentCancelled:
            self._ui(self._finish_thinking)
            self._ui(self._add_warn, "已停止")
        except Exception as exc:
            self._ui(self._finish_thinking)
            self._ui(self._add_error, f"Agent 运行失败：{exc}")
        finally:
            self._ui(self._set_busy, False)

    def _agent_step(self, step: int) -> None:
        if self._cancel_event.is_set():
            raise _AgentCancelled()
        self.step_no = step
        self._ui(self._add_step, step)
        self._ui(self._set_status, f"Step {step} 正在思考…")

    def _agent_log(self, msg: str) -> None:
        self._ui(self._add_log, msg)

    # ---------- 人工确认 ----------

    def _handle_confirm(self, cmd: str) -> bool:
        """后端工作线程调用：显示确认请求并阻塞等待用户回答"""
        self._confirm_event.clear()
        self._pending_confirm = cmd
        self._confirm_result = False
        # 切回 UI 线程显示提示
        self._ui(self._show_confirm, cmd)
        # 阻塞等待用户输入 y/n（最多 120 秒，超时按拒绝处理）
        self._confirm_event.wait(timeout=120)
        return self._confirm_result

    def _show_confirm(self, cmd: str) -> None:
        """UI 线程：把输入框变成确认框"""
        self.prompt.placeholder = "危险命令，输入 y 放行 / n 拒绝: "
        self._mount(
            Static(
                f"[#d29922]❓ 人工确认[/]\n[#d29922]命令: {escape(cmd)}[/]\n"
                f"[dim]输入 [bold]y[/] 放行，[bold]n[/] 拒绝[/]",
                classes="warn-msg",
            )
        )
        self.prompt.focus()

    def _agent_token(self, token: str) -> None:
        if self._cancel_event.is_set():
            raise _AgentCancelled()
        self._think_buffer.append(token)
        self._ui(self._ensure_thinking)
        raw = "".join(self._think_buffer)
        self._ui(self._update_thinking, raw)

    def _agent_tool(self, tool: str, args: dict) -> None:
        self._ui(self._finish_thinking)
        self._ui(self._add_tool, tool, args)

    def _agent_observe(self, observation: str) -> None:
        self._ui(self._add_observation, observation)

    def _agent_warn(self, msg: str) -> None:
        self._ui(self._finish_thinking)
        self._ui(self._add_warn, msg)

    def _agent_answer(self, answer: str) -> None:
        self._ui(self._finish_thinking)
        self._ui(self._add_answer, answer)

    def _agent_stop(self, msg: str) -> None:
        self._ui(self._finish_thinking)
        self._ui(self._add_error, msg)

    def run_chat(self, task: str) -> None:
        """对话模式：直接流式调用 LLM"""
        try:
            AgentsLLM, _, _ = self._import_backend()
            if (self._llm_profile or "local") == "local":
                self._ensure_local_vllm()
            llm = AgentsLLM(profile=self._llm_profile)
            messages = list(self.chat_messages)
            if not messages:
                messages = [{"role": "system", "content": CHAT_SYSTEM}]
            messages.append({"role": "user", "content": task})

            self._ui(self._begin_chat_answer)
            response = llm.think(messages=messages, on_token=self._chat_token)
            if response is None:
                reason = getattr(llm, "last_error", "") or "模型返回了空响应"
                raise RuntimeError(f"模型服务未响应：{reason}")

            messages.append({"role": "assistant", "content": response})
            self.chat_messages = messages
        except _AgentCancelled:
            self._ui(self._add_warn, "已停止")
        except Exception as exc:
            self._ui(self._add_error, f"对话失败：{exc}")
        finally:
            self._ui(self._set_busy, False)

    def _begin_chat_answer(self) -> None:
        self._chat_buffer = []
        self._chat_widget = Static("", markup=False, classes="assistant-msg")
        self._mount(self._chat_widget)

    def _chat_token(self, token: str) -> None:
        if self._cancel_event.is_set():
            raise _AgentCancelled()
        self._chat_buffer.append(token)
        text = "".join(self._chat_buffer)
        self._ui(self._update_chat_answer, text)

    def _update_chat_answer(self, text: str) -> None:
        if self._chat_widget is not None:
            self._chat_widget.update(text)
            self._scroll_end()

    # ---------- 按键动作 ----------

    def action_clear(self) -> None:
        self._clear_messages()

    def action_stop(self) -> None:
        self._stop()

    def action_toggle_mode(self) -> None:
        self._switch_mode("chat" if self.mode == "agent" else "agent")


if __name__ == "__main__":
    app = CodexApp()
    app.run()
