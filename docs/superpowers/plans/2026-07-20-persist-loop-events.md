# Persist Agent Loop Events to DB

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist `tool_call` and `turn_end` events to the database so the frontend can show the agent loop in historical sessions, while stripping them from LLM history.

**Architecture:** Tool call + turn end events are saved to `session.history` JSON column as `role: "loop_event"` entries. `getHistory()` filters them out before sending to Gemini. Frontend loads the full history (including loop events) and renders them inline with the assistant message.

**Tech Stack:** Python 3.11+, SQLAlchemy, FastAPI, React (Vite), SQLite/MySQL

---

## Context

Currently, `LoopLogger` emits `tool_call`, `tool_result`, and `turn_end` events to a transient in-memory list during a request. After the request completes, only the user query and assistant response are saved to the database via `saveMessage()`. This means:

1. Agent loop UI (tool chips, turn metrics) only works during live streaming
2. When loading history, frontend sees only user/model messages — no loop context
3. Tool results (raw API outputs) should NOT be persisted (observation masking)

## Design

| Event | Persist to DB? | Sent to LLM? | Shown in Frontend? |
|-------|---------------|--------------|-------------------|
| `tool_call` | ✅ Yes | ❌ No (filtered by `getHistory`) | ✅ Yes (tool chip with name + args) |
| `tool_result` | ❌ No | ❌ No | ❌ No (observation masking) |
| `turn_end` | ✅ Yes | ❌ No (filtered by `getHistory`) | ✅ Yes (turn metrics header) |

History JSON shape after this change:
```json
[
  {"role": "user", "content": "Compare PETR4 and VALE3", "timestamp": "..."},
  {"role": "loop_event", "eventType": "tool_call", "metadata": {"toolName": "get_cotations", "args": {"search": "PETR4,VALE3"}}, "timestamp": "..."},
  {"role": "loop_event", "eventType": "turn_end", "metadata": {"turnNumber": 0, "durationMs": 1500, "toolsUsed": ["get_cotations"]}, "timestamp": "..."},
  {"role": "assistant", "content": "PETR4 P/L is 5.2, VALE3 is 8.1...", "timestamp": "..."}
]
```

---

## Task 1: Save loop events to DB in streamMessage()

**Files:**
- Modify: `main/app/prometheus/agent.py` — `streamMessage()` method

**Interfaces:**
- Consumes: `LoopLogger.emit()` returns event dicts (already working)
- Produces: Loop events appended to `session.history` via `saveLoopEvent()`

- [ ] **Step 1: Add `saveLoopEvent` method to `PrometheusChatManager`**

In `main/app/prometheus/chat.py`, add after `saveMessage`:

```python
@classmethod
def saveLoopEvent(cls, db: Session, sessionId: str, eventType: str, metadata: dict):
    """Persist a loop event (tool_call or turn_end) to session history."""
    session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

    if session:
        if session.history is None:
            session.history = []

        event = {
            "role": "loop_event",
            "eventType": eventType,
            "metadata": metadata,
            "timestamp": datetime.now().isoformat(),
        }

        session.history.append(event)
        flag_modified(session, "history")
        db.commit()
```

- [ ] **Step 2: Persist tool_call events in streamMessage()**

In `main/app/prometheus/agent.py`, in the `tool_call` event block (~line 315-323), after `loop.emit("tool_call", ...)`, add persistence:

```python
case "tool_call":
    # ... existing code ...
    tool_event = loop.emit(
        "tool_call",
        turn=tool_call_state["turn"],
        tool=tool_call_state["current_tool"],
        toolCallId=tool_call_state["current_tool_call_id"],
        args=arguments,
    )
    # Persist tool_call to DB
    if sessionId:
        try:
            PrometheusChatManager.saveLoopEvent(
                db, str(sessionId), "tool_call",
                {"toolName": tool_call_state["current_tool"], "args": arguments, "turn": tool_call_state["turn"]},
            )
        except Exception as e:
            logger.error(f"Failed to persist tool_call event: {e}")
    # ... existing yield ...
```

- [ ] **Step 3: Persist turn_end events in streamMessage()**

In `main/app/prometheus/agent.py`, in the `turn_end` block (~line 337-348), after `loop.emit("turn_end", ...)`, add persistence:

```python
case "turn_end":
    # ... existing code ...
    turn_event = loop.emit(
        "turn_end",
        # ... existing fields ...
    )
    # Persist turn_end to DB
    if sessionId:
        try:
            PrometheusChatManager.saveLoopEvent(
                db, str(sessionId), "turn_end",
                {"turnNumber": turn_event["metadata"]["turnNumber"], "durationMs": duration_ms, "toolsUsed": turn_event["metadata"]["toolsUsed"]},
            )
        except Exception as e:
            logger.error(f"Failed to persist turn_end event: {e}")
```

- [ ] **Step 4: Verify no import issues**

`PrometheusChatManager` is already imported in `agent.py` (line 12). No new imports needed.

- [ ] **Step 5: Commit**

```bash
git add main/app/prometheus/agent.py main/app/prometheus/chat.py
git commit -m "feat(prometheus): persist tool_call and turn_end events to DB"
```

---

## Task 2: Filter loop events from LLM history

**Files:**
- Modify: `main/app/prometheus/chat.py` — `getHistory()` method

**Interfaces:**
- Consumes: `session.history` list with `role: "loop_event"` entries
- Produces: Filtered history list with only `user` and `assistant` messages formatted for Gemini

- [ ] **Step 1: Add filtering in getHistory()**

In `main/app/prometheus/chat.py`, modify `getHistory()` to skip loop events:

```python
@classmethod
def getHistory(cls, db: Session, sessionId: str, limit: int = 20):
    session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

    if not session or not session.history:
        return []

    activeHistory: list = session.history[-limit:]

    formattedHistory = []
    for msg in activeHistory:
        # Skip loop events — they're for UI only, not for the LLM
        if msg.get("role") == "loop_event":
            continue
        formattedHistory.append(
            {"role": "user" if msg["role"] == "user" else "model", "parts": [{"text": msg["content"]}]}
        )
    return formattedHistory
```

- [ ] **Step 2: Commit**

```bash
git add main/app/prometheus/chat.py
git commit -m "feat(prometheus): filter loop events from LLM history"
```

---

## Task 3: Return full history (including loop events) to frontend

**Files:**
- Modify: `main/controller/prometheus_controller.py` — `getHistory()` endpoint

**Interfaces:**
- Consumes: `session.history` with loop events
- Produces: Full history array to frontend

- [ ] **Step 1: Verify controller already returns full history**

The controller at line 92 already returns `session.history or []` — this includes loop events. No change needed on the backend side for the controller.

- [ ] **Step 2: Add a separate endpoint for LLM-formatted history (optional)**

If you want to keep the existing endpoint clean for the frontend, add a separate one:

```python
@router.get("/history/{sessionId}/llm")
def getLLMHistory(
    sessionId: str,
    db: Session = Depends(getSession),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    verifySessionOwnsership(db, sessionId, user["userId"])
    formatted = PrometheusChatManager.getHistory(db, sessionId, limit=50)
    return {"success": True, "history": formatted}
```

But since the frontend needs the full history (with loop events), and `getHistory()` is only called internally for Gemini, the controller change is optional. The frontend will handle filtering on its side.

- [ ] **Step 3: Commit**

```bash
git add main/controller/prometheus_controller.py
git commit -m "feat(prometheus): optional LLM history endpoint"
```

---

## Task 4: Frontend — Load and display loop events from history

**Files:**
- Modify: `frontend/src/App.jsx` — `loadHistory()` function
- Modify: `frontend/src/components/MessageList.jsx` — render AgentLoop from history

**Interfaces:**
- Consumes: Full history array from `GET /history/{sessionId}` (includes loop events)
- Produces: Messages + loop events for each assistant message

- [ ] **Step 1: Update `loadHistory()` to extract loop events**

In `frontend/src/App.jsx`, modify `loadHistory()` to associate loop events with their assistant message:

```javascript
const loadHistory = async (sid) => {
  try {
    const hist = await fetchHistory(sid);
    // Separate loop events from user/model messages
    const messages = [];
    const eventsByAssistant = {}; // key = assistant message index
    let currentAssistantIdx = -1;

    for (const m of hist) {
      if (m.role === 'loop_event') {
        // Associate with the most recent assistant message (or next one)
        const key = currentAssistantIdx >= 0 ? currentAssistantIdx : messages.length;
        if (!eventsByAssistant[key]) eventsByAssistant[key] = [];
        eventsByAssistant[key].push({
          type: m.eventType,
          turn: m.metadata.turnNumber ?? m.metadata.turn,
          tool: m.metadata.toolName ?? m.metadata.tool,
          args: m.metadata.args,
          durationMs: m.metadata.durationMs,
          toolsUsed: m.metadata.toolsUsed,
        });
      } else if (m.role === 'assistant') {
        currentAssistantIdx = messages.length;
        messages.push({
          role: 'model',
          text: m.content || '',
          streaming: false,
        });
      } else {
        messages.push({
          role: 'user',
          text: m.content || '',
          streaming: false,
        });
      }
    }

    setMessages(messages);
    // For now, load last assistant's events into the live state
    const lastIdx = messages.length - 1;
    if (messages[lastIdx]?.role === 'model' && eventsByAssistant[lastIdx]) {
      setToolEvents(eventsByAssistant[lastIdx].filter(e => e.type === 'tool_call'));
      const lastTurn = eventsByAssistant[lastIdx].filter(e => e.type === 'turn_end').pop();
      setTurnMetrics(lastTurn || null);
    } else {
      setToolEvents([]);
      setTurnMetrics(null);
    }
  } catch {
    setMessages([]);
  }
};
```

- [ ] **Step 2: Update `MessageList.jsx` to show AgentLoop for all model messages**

In `frontend/src/components/MessageList.jsx`, pass `allToolEvents` and `allTurnMetrics` per message:

```jsx
export default function MessageList({ messages, toolEvents, turnMetrics }) {
  // ... existing refs and effects ...

  // Group tool events by assistant message index
  const eventsByAssistant = {};
  let assistantIdx = -1;
  messages.forEach((m, i) => {
    if (m.role === 'model') {
      assistantIdx = i;
    }
  });

  return (
    <div className="messages">
      {messages.map((m, i) => {
        const showAgentLoop = m.role === 'model' && (
          // Show for live streaming messages
          (i === messages.length - 1 && (toolEvents.length > 0 || turnMetrics))
        );

        return (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-body">
              {showAgentLoop && (
                <AgentLoop toolEvents={toolEvents} turnMetrics={turnMetrics} />
              )}
              {m.streaming ? (
                <MdocMessage text={m.text} streaming />
              ) : m.role === 'model' ? (
                <MdocMessage text={m.text} />
              ) : (
                <div className="content">{m.text}</div>
              )}
            </div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
```

Actually, for historical sessions, we need a different approach. Let me revise:

- [ ] **Step 2 (revised): Store loop events in message objects**

In `frontend/src/App.jsx`, include loop events in each message object:

```javascript
const loadHistory = async (sid) => {
  try {
    const hist = await fetchHistory(sid);
    const messages = [];
    let pendingToolEvents = [];

    for (const m of hist) {
      if (m.role === 'loop_event') {
        // Accumulate events until we hit the assistant message
        pendingToolEvents.push({
          type: m.eventType,
          turn: m.metadata.turnNumber ?? m.metadata.turn,
          tool: m.metadata.toolName ?? m.metadata.tool,
          args: m.metadata.args,
          durationMs: m.metadata.durationMs,
          toolsUsed: m.metadata.toolsUsed,
        });
      } else if (m.role === 'assistant') {
        // Attach accumulated events to this assistant message
        messages.push({
          role: 'model',
          text: m.content || '',
          streaming: false,
          loopEvents: [...pendingToolEvents],
          turnMetrics: pendingToolEvents.filter(e => e.type === 'turn_end').pop() || null,
        });
        pendingToolEvents = [];
      } else {
        messages.push({
          role: 'user',
          text: m.content || '',
          streaming: false,
        });
      }
    }

    // Handle events without a following assistant message (edge case)
    if (pendingToolEvents.length > 0 && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === 'model') {
        lastMsg.loopEvents = [...pendingToolEvents];
        lastMsg.turnMetrics = pendingToolEvents.filter(e => e.type === 'turn_end').pop() || null;
      }
    }

    setMessages(messages);
    // Clear live state since we loaded from DB
    setToolEvents([]);
    setTurnMetrics(null);
  } catch {
    setMessages([]);
  }
};
```

- [ ] **Step 3: Update MessageList to use per-message loop events**

In `frontend/src/components/MessageList.jsx`:

```jsx
export default function AgentLoop({ toolEvents, turnMetrics }) {
  // ... existing component ...
}

export default function MessageList({ messages, toolEvents, turnMetrics }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, toolEvents]);

  if (!messages.length) {
    return (
      <div className="messages">
        <div className="no-sessions">Start a conversation</div>
      </div>
    );
  }

  return (
    <div className="messages">
      {messages.map((m, i) => {
        // Use per-message loopEvents if available, otherwise fall back to live state
        const isLastModel = i === messages.length - 1 && m.role === 'model';
        const loopEvents = m.loopEvents || (isLastModel ? toolEvents : []);
        const turnMetricsForMsg = m.turnMetrics || (isLastModel ? turnMetrics : null);
        const showAgentLoop = m.role === 'model' && (loopEvents.length > 0 || turnMetricsForMsg);

        return (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-body">
              {showAgentLoop && (
                <AgentLoop toolEvents={loopEvents} turnMetrics={turnMetricsForMsg} />
              )}
              {m.streaming ? (
                <MdocMessage text={m.text} streaming />
              ) : m.role === 'model' ? (
                <MdocMessage text={m.text} />
              ) : (
                <div className="content">{m.text}</div>
              )}
            </div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/MessageList.jsx
git commit -m "feat(frontend): display agent loop from persisted history"
```

---

## Task 5: Test the full flow

**Files:**
- Test: Run the app and verify

- [ ] **Step 1: Start the backend**

```bash
docker-compose up -d --build
# or
python run.py
```

- [ ] **Step 2: Send a message that triggers tools**

Open the frontend, create a new session, send: "Cotação de PETR4"

Verify in browser DevTools (Network tab → `/history/{sessionId}` response):
- User message with content
- Loop events with `role: "loop_event"`, `eventType: "tool_call"`, `metadata: {toolName, args}`
- Loop events with `role: "loop_event"`, `eventType: "turn_end"`, `metadata: {turnNumber, durationMs, toolsUsed}`
- Assistant message with content

- [ ] **Step 3: Reload the page and load the same session**

Verify:
- User message renders
- Agent Loop block appears before assistant message with tool chips
- Tool chips show tool name and args (expandable)
- Turn metrics show turn number, duration, tools used count

- [ ] **Step 4: Send a follow-up message**

Verify the agent doesn't see previous tool outputs (observation masking):
- History sent to Gemini should only contain user/model messages
- Loop events should NOT appear in the LLM history

- [ ] **Step 5: Verify no DB bloat**

Check that `tool_result` events are NOT being saved:

```sql
SELECT COUNT(*) FROM prometheus WHERE JSON_CONTAINS_PATH(history, 'one', '$[*][?(@.eventType="tool_result")]');
```

Should return 0.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "test(prometheus): verify loop event persistence and observation masking"
```

---

## Summary of Changes

| File | Change | Lines |
|------|--------|-------|
| `main/app/prometheus/chat.py` | Add `saveLoopEvent()` method | ~15 new |
| `main/app/prometheus/chat.py` | Filter loop events in `getHistory()` | ~2 modified |
| `main/app/prometheus/agent.py` | Persist tool_call + turn_end after `loop.emit()` | ~20 new |
| `frontend/src/App.jsx` | `loadHistory()` extracts loop events per message | ~30 modified |
| `frontend/src/components/MessageList.jsx` | Use per-message loopEvents | ~15 modified |

**Total: ~80 lines changed across 5 files**

---

## Global Constraints

- No new database tables or columns (reuse existing `history` JSON column)
- No new dependencies
- `tool_result` events must NOT be persisted (observation masking)
- Loop events must be filtered out before sending to Gemini
- Frontend must work with both live streaming and historical sessions
- `getHistory()` limit applies to total entries including loop events
