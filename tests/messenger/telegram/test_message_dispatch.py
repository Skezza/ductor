"""Tests for Telegram message dispatch transcript shaping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from aiogram.types import Message

from ductor_bot.config import SceneConfig, StreamingConfig
from ductor_bot.messenger.telegram.message_dispatch import StreamingDispatch, run_streaming_message
from ductor_bot.orchestrator.registry import OrchestratorResult
from ductor_bot.session.key import SessionKey


class _FakeTypingContext:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _tb: object,
    ) -> None:
        return None


class _FakeEditor:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.tools: list[str] = []
        self.systems: list[str] = []
        self.finalized_text: str = ""
        self._has_content = False

    @property
    def has_content(self) -> bool:
        return self._has_content

    async def append_text(self, text: str) -> None:
        self.texts.append(text)
        self._has_content = self._has_content or bool(text.strip())

    async def append_tool(self, tool_name: str) -> None:
        self.tools.append(tool_name)
        self._has_content = True

    async def append_system(self, text: str) -> None:
        self.systems.append(text)
        self._has_content = True

    async def finalize(self, full_text: str) -> None:
        self.finalized_text = full_text


def _make_dispatch(
    orchestrator: MagicMock,
    *,
    scene_config: SceneConfig | None = None,
) -> tuple[MagicMock, Message, StreamingDispatch]:
    bot = MagicMock()
    message = MagicMock(spec=Message)
    type(message).message_id = PropertyMock(return_value=77)
    dispatch = StreamingDispatch(
        bot=bot,
        orchestrator=orchestrator,
        message=message,
        key=SessionKey.telegram(1),
        text="hello",
        streaming_cfg=StreamingConfig(edit_interval_seconds=0.0),
        allowed_roots=None,
        scene_config=scene_config,
    )
    return bot, message, dispatch


class TestRunStreamingMessage:
    async def test_tool_only_turn_keeps_actions_footer(self) -> None:
        editor = _FakeEditor()
        orchestrator = MagicMock()

        async def _handle(
            _key: SessionKey,
            _text: str,
            *,
            on_text_delta: AsyncMock | None = None,
            on_tool_activity: AsyncMock | None = None,
            on_system_status: AsyncMock | None = None,
        ) -> OrchestratorResult:
            assert on_text_delta is not None
            assert on_tool_activity is not None
            assert on_system_status is not None
            await on_tool_activity("Bash")
            await on_tool_activity("Bash")
            return OrchestratorResult(text="")

        orchestrator.handle_message_streaming = AsyncMock(side_effect=_handle)
        _bot, _message, dispatch = _make_dispatch(orchestrator)

        with (
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.create_stream_editor",
                return_value=editor,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.TypingContext",
                _FakeTypingContext,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.send_files_from_text",
                new_callable=AsyncMock,
            ) as mock_files,
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.send_rich",
                new_callable=AsyncMock,
            ) as mock_send_rich,
        ):
            result_text = await run_streaming_message(dispatch)

        assert "Actions: running shell x2" in result_text
        assert editor.finalized_text.endswith(result_text)
        mock_files.assert_awaited_once()
        mock_send_rich.assert_not_called()

    async def test_thinking_only_does_not_add_actions_footer(self) -> None:
        editor = _FakeEditor()
        orchestrator = MagicMock()

        async def _handle(
            _key: SessionKey,
            _text: str,
            *,
            on_text_delta: AsyncMock | None = None,
            on_tool_activity: AsyncMock | None = None,
            on_system_status: AsyncMock | None = None,
        ) -> OrchestratorResult:
            _ = on_tool_activity
            assert on_text_delta is not None
            assert on_system_status is not None
            await on_system_status("thinking")
            await on_text_delta("Final answer")
            return OrchestratorResult(text="Final answer")

        orchestrator.handle_message_streaming = AsyncMock(side_effect=_handle)
        _bot, _message, dispatch = _make_dispatch(orchestrator)

        with (
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.create_stream_editor",
                return_value=editor,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.TypingContext",
                _FakeTypingContext,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.send_files_from_text",
                new_callable=AsyncMock,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.send_rich",
                new_callable=AsyncMock,
            ),
        ):
            result_text = await run_streaming_message(dispatch)

        assert result_text == "Final answer"
        assert "Actions:" not in editor.finalized_text

    async def test_actions_footer_precedes_technical_footer(self) -> None:
        editor = _FakeEditor()
        orchestrator = MagicMock()

        async def _handle(
            _key: SessionKey,
            _text: str,
            *,
            on_text_delta: AsyncMock | None = None,
            on_tool_activity: AsyncMock | None = None,
            on_system_status: AsyncMock | None = None,
        ) -> OrchestratorResult:
            _ = on_system_status
            assert on_text_delta is not None
            assert on_tool_activity is not None
            await on_tool_activity("Write")
            await on_text_delta("Done")
            return OrchestratorResult(
                text="Done",
                model_name="gpt-5.4",
                total_tokens=100,
                input_tokens=40,
                cost_usd=0.01,
                duration_ms=2000.0,
            )

        orchestrator.handle_message_streaming = AsyncMock(side_effect=_handle)
        _bot, _message, dispatch = _make_dispatch(
            orchestrator,
            scene_config=SceneConfig(technical_footer=True),
        )

        with (
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.create_stream_editor",
                return_value=editor,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.TypingContext",
                _FakeTypingContext,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.send_files_from_text",
                new_callable=AsyncMock,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.send_rich",
                new_callable=AsyncMock,
            ),
        ):
            result_text = await run_streaming_message(dispatch)

        assert "Actions: editing files" in result_text
        assert "Model: gpt-5.4" in result_text
        assert result_text.index("Actions:") < result_text.index("Model:")

    async def test_recovering_status_is_included_in_actions_footer(self) -> None:
        editor = _FakeEditor()
        orchestrator = MagicMock()

        async def _handle(
            _key: SessionKey,
            _text: str,
            *,
            on_text_delta: AsyncMock | None = None,
            on_tool_activity: AsyncMock | None = None,
            on_system_status: AsyncMock | None = None,
        ) -> OrchestratorResult:
            _ = on_tool_activity
            assert on_text_delta is not None
            assert on_system_status is not None
            await on_system_status("recovering")
            await on_text_delta("Recovered")
            return OrchestratorResult(text="Recovered")

        orchestrator.handle_message_streaming = AsyncMock(side_effect=_handle)
        _bot, _message, dispatch = _make_dispatch(orchestrator)

        with (
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.create_stream_editor",
                return_value=editor,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.TypingContext",
                _FakeTypingContext,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.send_files_from_text",
                new_callable=AsyncMock,
            ),
            patch(
                "ductor_bot.messenger.telegram.message_dispatch.send_rich",
                new_callable=AsyncMock,
            ),
        ):
            result_text = await run_streaming_message(dispatch)

        assert "Actions: recovering session" in result_text
