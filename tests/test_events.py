"""Tests for LoopLogger — appends events to history JSON list."""

from main.app.prometheus.events import LoopLogger


class TestLoopLogger:
    def test_init_with_empty_history(self):
        history = []
        logger = LoopLogger(history)
        assert logger._history is history

    def test_emit_tool_call_appends_to_history(self):
        history = []
        logger = LoopLogger(history)
        logger.emit_tool_call("get_cotations", {"search": "PETR4"}, turnNumber=1)
        assert len(history) == 1
        assert history[0]["role"] == "loop_event"
        assert history[0]["eventType"] == "tool_call"
        assert history[0]["toolName"] == "get_cotations"
        assert history[0]["metadata"]["args"] == {"search": "PETR4"}
        assert history[0]["metadata"]["turnNumber"] == 1
        assert "timestamp" in history[0]

    def test_emit_tool_result_appends_to_history(self):
        history = []
        logger = LoopLogger(history)
        logger.emit_tool_result("get_cotations", {"result": "data"}, turnNumber=2)
        assert len(history) == 1
        assert history[0]["eventType"] == "tool_result"
        assert history[0]["toolName"] == "get_cotations"
        assert history[0]["metadata"]["result"] == {"result": "data"}

    def test_emit_turn_end_appends_to_history(self):
        history = []
        logger = LoopLogger(history)
        logger.emit_turn_end(turnNumber=0, durationMs=150, toolsUsed=["get_cotations", "execute_code"])
        assert len(history) == 1
        assert history[0]["eventType"] == "turn_end"
        assert history[0]["metadata"]["durationMs"] == 150
        assert history[0]["metadata"]["toolsUsed"] == ["get_cotations", "execute_code"]

    def test_flush_is_noop(self):
        history = []
        logger = LoopLogger(history)
        logger.emit_tool_call("tool_a", {})
        logger.flush()  # should not clear history
        assert len(history) == 1

    def test_multiple_events_preserve_order(self):
        history = []
        logger = LoopLogger(history)
        logger.emit_tool_call("tool_a", {"step": 1})
        logger.emit_tool_result("tool_a", {"result": "ok"})
        logger.emit_turn_end(turnNumber=0, durationMs=100)
        types = [e["eventType"] for e in history]
        assert types == ["tool_call", "tool_result", "turn_end"]

    def test_events_share_history_with_chat_messages(self):
        """Loop events coexist with user/assistant messages in the same history list."""
        history = [
            {"role": "user", "content": "Analyze PETR4"},
            {"role": "assistant", "content": "I'll analyze..."},
        ]
        logger = LoopLogger(history)
        logger.emit_tool_call("execute_code", {"code": "print(42)"})
        logger.emit_tool_result("execute_code", {"stdout": "42\n"})
        # History now has 4 entries: 2 chat + 2 loop events
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "loop_event"
        assert history[3]["role"] == "loop_event"

    def test_emit_turn_end_with_default_tools_used(self):
        history = []
        logger = LoopLogger(history)
        logger.emit_turn_end(turnNumber=0, durationMs=50)
        assert history[0]["metadata"]["toolsUsed"] == []
