"""Codex CLI 风格终端前端：Textual 实现。

支持两种模式：
- Agent 模式（默认）：调用 back/ReAct.py，实时展示思考 / 工具调用 / 观察结果 / 最终答案。
- 对话模式：调用 back/llm_client.py，直接与 LLM 流式对话。
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import List, Optional, Tuple, Type

from dotenv import load_dotenv
from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Collapsible, Footer, Header, Input, Static

BACK_DIR = Path(__file__).resolve().parent.parent / "back"
PROJECT_DIR = BACK_DIR.parent
load_dotenv(BACK_DIR / ".env")

THINK_COLLAPSE_THRESHOLD = 1000  # 思考过程超过该字数就折叠成小框


WELCOME = """[bold cyan]🤖 Codex 终端[/bold cyan]
[dim]本地 Coding Agent · Textual 前端[/dim]
[dim]输入任务开始执行，/help 查看命令，Ctrl+C 复制选中文本，Ctrl+Q 退出[/dim]"""

HELP_TEXT = """[bold cyan]/help[/]      显示本帮助
[bold cyan]/clear[/]     清空当前对话
[bold cyan]/agent[/]     切换到 Agent 模式（工具调用 + ReAct）
[bold cyan]/chat[/]      切换到对话模式（直接 LLM 流式对话）
[bold cyan]/model[/]     查看当前模型配置
[bold cyan]/pwd[/]       查看当前所在项目目录
[bold cyan]/again[/]     重新执行上一条任务
[bold cyan]/stop[/]      停止当前任务（或 Ctrl+X）
[bold cyan]/quit[/]      退出（或 Ctrl+Q）"""

CHAT_SYSTEM = (
    "你是一个运行在终端里的 AI 编程助手。"
    "请用中文回答，代码示例保持简洁，涉及文件操作时给出可执行的命令。"
)


class _AgentCancelled(Exception):
    """用户主动停止任务时抛出，用于穿透 LLM 流式调用。"""


class CodexApp(App):
    """Codex 风格终端应用"""

    TITLE = "Codex"
    SUB_TITLE = "本地 Coding Agent · ReAct"
    background = "transparent"

    BINDINGS = [
        # Ctrl+C 保留 Textual 默认的“复制选中文本”，不再退出
        Binding("ctrl+q", "quit", "退出", priority=True),
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
                        placeholder="输入任务，Enter 发送，/help 查看命令",
                        id="prompt",
                    )
                yield Static("", id="status", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.messages = self.query_one("#messages", VerticalScroll)
        self.status_bar = self.query_one("#status", Static)
        self.prompt = self.query_one("#prompt", Input)
        self._set_status()
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
                "输入任务，Enter 发送，/help 查看命令"
                if self.mode == "agent"
                else "输入问题，Enter 发送，/help 查看命令"
            )
            self._confirm_event.set()
            self._set_status()
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
        elif cmd == "/pwd":
            self._mount(
                Static(
                    f"[dim]当前目录: {escape(str(PROJECT_DIR))}[/]",
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
            "输入任务，Enter 发送，/help 查看命令"
            if mode == "agent"
            else "输入问题，Enter 发送，/help 查看命令"
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

    # ---------- 状态 ----------

    def _model_info_text(self) -> str:
        """从本地 .env 读取模型与 API 地址（不包含密钥）"""
        model = os.getenv("LLM_MODEL_ID") or "(未设置)"
        base_url = os.getenv("LLM_BASE_URL") or "(未设置)"
        # 本地 vLLM 的模型 ID 常常是一整条路径，这里只显示最后一段
        short_model = model.replace("\\", "/").rstrip("/").split("/")[-1]
        short_api = base_url.replace("http://", "").replace("https://", "").rstrip("/")
        return f"模型: {short_model} · API: {short_api}"

    def _compact_model_info(self) -> str:
        """状态栏用的紧凑版：模型名截断，API 只显示 host:port"""
        model = os.getenv("LLM_MODEL_ID") or "(未设置)"
        base_url = os.getenv("LLM_BASE_URL") or "(未设置)"
        short_model = model.replace("\\", "/").rstrip("/").split("/")[-1]
        if len(short_model) > 12:
            short_model = short_model[:12] + "…"
        api_host = (
            base_url.replace("http://", "")
            .replace("https://", "")
            .rstrip("/")
            .split("/")[0]
        )
        return f"模型: {short_model} · API: {api_host}"

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
        text += f" · 📁 {PROJECT_DIR.name}"
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
            from llm_client import AgentsLLM
            from ReAct import MAX_STEPS, run_react_loop
            import ReAct

            # ===== 后端导入时绑定人工确认回调 =====
            ReAct.CONFIRM_CALLBACK = self._handle_confirm
            ReAct.CONFIRM_ENABLED = True

            self._backend = (AgentsLLM, run_react_loop, MAX_STEPS)
        return self._backend

    def run_agent(self, task: str) -> None:
        """Agent 模式：跑 ReAct 主循环，把事件实时投递到界面"""
        try:
            AgentsLLM, run_react_loop, _ = self._import_backend()
            llm = AgentsLLM()
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
            llm = AgentsLLM()
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
