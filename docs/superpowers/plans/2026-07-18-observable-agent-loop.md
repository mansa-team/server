# Observable Agent Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface tool calls, results, and turn metrics from the Prometheus agent loop to the Vite+React testing frontend in real-time via SSE, making the agent's reasoning process visible.

**Architecture:** Backend yields new SSE event types (`tool_call`, `tool_result`, `turn_end`) alongside existing `text` events. Frontend `api.js` dispatches these to callbacks. A new `AgentLoop` component renders tool activity inline with messages. CSS keeps it simple — collapsible tool cards with status indicators.

**Tech Stack:** React 18, Vite, SSE (fetch + ReadableStream), existing `LoopLogger` + `LoopHarness` from `events.py`/`agent.py`

## Global Constraints

- Frontend lives in `frontend/` (Vite+React, port 3100, in `.gitignore` — testing only)
- Backend SSE events must be backward-compatible (existing `text`/`session`/`error` unchanged)
- No new npm dependencies — React stdlib + CSS only
- `LoopLogger` already emits events to history/DB — we're just ALSO yielding them to SSE
- Keep it simple: this is a testing tool, not production UI

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `main/app/prometheus/agent.py` | Modify | Yield tool events to SSE stream |
| `main/app/prometheus/events.py` | Modify | Add `emit()` method that yields events |
| `frontend/src/api.js` | Modify | Add `onToolCall`, `onToolResult`, `onTurnEnd` callbacks to `streamChat` |
| `frontend/src/App.jsx` | Modify | Handle new event types in state |
| `frontend/src/components/AgentLoop.jsx` | Create | Tool call/result visualization component |
| `frontend/src/App.css` | Modify | Styles for agent loop panel |

---

### Task 1: Backend — Yield tool events to SSE

**Files:**
- Modify: `main/app/prometheus/agent.py:195-238`
- Modify: `main/app/prometheus/events.py:1-44`

**Interfaces:**
- Consumes: `LoopLogger` from `events.py`
- Produces: `{"type": "tool_call", "tool": "...", "args": {...}, "turn": N}` SSE events, `{"type": "tool_result", "tool": "...", "result": "...", "turn": N}`, `{"type": "turn_end", "turn": N, "durationMs": N, "toolsUsed": N}`

- [ ] **Step 1: Add emit method to LoopLogger**

In `main/app/prometheus/events.py`, add a method that returns the event dict instead of just appending:

```python
def emit_tool_call(self, toolName: str, args: dict, turnNumber: int) -> dict:
    event = {"role": "loop_event", "type": "tool_call", "toolName": toolName, "args": args, "turnNumber": turnNumber}
    self.history.append(event)
    return event

def emit_tool_result(self, toolName: str, result, turnNumber: int) -> dict:
    event = {"role": "loop_event", "type": "tool_result", "toolName": toolName, "result": result, "turnNumber": turnNumber}
    self.history.append(event)
    return event

def emit_turn_end(self, turnNumber: int, durationMs: int, toolsUsed: int) -> dict:
    event = {"role": "loop_event", "type": "turn_end", "turnNumber": turnNumber, "durationMs": durationMs, "toolsUsed": toolsUsed}
    self.history.append(event)
    return event
```

- [ ] **Step 2: Yield tool events in agent.py streamMessage**

In `main/app/prometheus/agent.py`, after each `loop.emit_*()` call, also `yield` the event as SSE:

```python
# After loop.emit_tool_call(...)
yield {"type": "tool_call", "tool": toolName, "args": args, "turn": turnNumber}

# After loop.emit_tool_result(...)
yield {"type": "tool_result", "tool": toolName, "result": str(result)[:500], "turn": turnNumber}

# After loop.emit_turn_end(...)
yield {"type": "turn_end", "turn": turnNumber, "durationMs": durationMs, "toolsUsed": toolsUsed}
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_agent.py tests/test_events.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add main/app/prometheus/agent.py main/app/prometheus/events.py
git commit -m "yield tool call events to SSE stream"
```

---

### Task 2: Frontend — Update api.js to dispatch tool events

**Files:**
- Modify: `frontend/src/api.js:111-148`

**Interfaces:**
- Consumes: SSE events from backend
- Produces: `onToolCall(event)`, `onToolResult(event)`, `onTurnEnd(event)` callbacks

- [ ] **Step 1: Update streamChat signature**

Add new optional callbacks to `streamChat`:

```javascript
export async function streamChat(query, sessionId, onChunk, onDone, onError, onToolCall, onToolResult, onTurnEnd) {
```

- [ ] **Step 2: Dispatch new event types**

In the SSE parsing loop (line 137-144), add handlers for new event types:

```javascript
try {
  const event = JSON.parse(data);
  if (event.type === 'text') {
    onChunk(event.text);
  } else if (event.type === 'error') {
    onError(event.message);
  } else if (event.type === 'tool_call' && onToolCall) {
    onToolCall(event);
  } else if (event.type === 'tool_result' && onToolResult) {
    onToolResult(event);
  } else if (event.type === 'turn_end' && onTurnEnd) {
    onTurnEnd(event);
  }
} catch {}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "dispatch tool events from SSE stream"
```

---

### Task 3: Frontend — Add AgentLoop component

**Files:**
- Create: `frontend/src/components/AgentLoop.jsx`

**Interfaces:**
- Consumes: `toolEvents` array from App.jsx state
- Produces: Visual render of tool calls/results

- [ ] **Step 1: Create AgentLoop component**

```jsx
import { useState } from 'react';

const STATUS = {
  pending: { icon: '⏳', color: '#f59e0b' },
  running: { icon: '⚡', color: '#3b82f6' },
  done: { icon: '✓', color: '#10b981' },
  error: { icon: '✗', color: '#ef4444' },
};

function ToolCard({ event }) {
  const [expanded, setExpanded] = useState(false);
  const status = event.type === 'tool_result'
    ? (event.result?.error ? 'error' : 'done')
    : 'running';
  const { icon, color } = STATUS[status];

  const argsStr = event.args ? JSON.stringify(event.args, null, 2) : '';
  const resultStr = event.result ? JSON.stringify(event.result, null, 2) : '';

  return (
    <div className="tool-card" style={{ borderLeftColor: color }}>
      <button className="tool-header" onClick={() => setExpanded(!expanded)}>
        <span className="tool-icon">{icon}</span>
        <span className="tool-name">{event.tool || event.toolName}</span>
        <span className="tool-turn">turn {event.turn ?? event.turnNumber}</span>
        <span className="tool-chevron">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <div className="tool-details">
          {argsStr && <div className="tool-section"><label>args</label><pre>{argsStr}</pre></div>}
          {resultStr && <div className="tool-section"><label>result</label><pre>{resultStr}</pre></div>}
        </div>
      )}
    </div>
  );
}

export default function AgentLoop({ toolEvents, turnMetrics }) {
  if (!toolEvents.length && !turnMetrics) return null;

  return (
    <div className="agent-loop">
      <div className="agent-loop-header">
        <span className="agent-loop-title">Agent Loop</span>
        {turnMetrics && (
          <span className="agent-loop-metrics">
            turn {turnMetrics.turn} · {turnMetrics.durationMs}ms · {turnMetrics.toolsUsed} tool{turnMetrics.toolsUsed !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      <div className="agent-loop-events">
        {toolEvents.map((ev, i) => (
          <ToolCard key={i} event={ev} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AgentLoop.jsx
git commit -m "add AgentLoop component for tool call visualization"
```

---

### Task 4: Frontend — Wire AgentLoop into App.jsx

**Files:**
- Modify: `frontend/src/App.jsx:16-154`

**Interfaces:**
- Consumes: `AgentLoop` component, `streamChat` with new callbacks
- Produces: `toolEvents` state array, `turnMetrics` state object

- [ ] **Step 1: Add toolEvents state**

After the existing state declarations (line 22), add:

```javascript
const [toolEvents, setToolEvents] = useState([]);
const [turnMetrics, setTurnMetrics] = useState(null);
```

- [ ] **Step 2: Clear toolEvents on new session or new message**

In `handleNewSession` and `handleSelectSession`, clear tool events:

```javascript
setToolEvents([]);
setTurnMetrics(null);
```

In `handleSend`, before the streamChat call, clear previous turn's events:

```javascript
setToolEvents([]);
setTurnMetrics(null);
```

- [ ] **Step 3: Pass callbacks to streamChat**

Update the `streamChat` call in `handleSend` (line 117) to include new callbacks:

```javascript
await streamChat(
  query,
  activeSid,
  (chunk) => { /* onChunk — existing */ },
  () => { /* onDone — existing */ },
  (msg) => { /* onError — existing */ },
  // New callbacks:
  (event) => setToolEvents((prev) => [...prev, event]),
  (event) => setToolEvents((prev) => [...prev, event]),
  (event) => setTurnMetrics(event),
);
```

- [ ] **Step 4: Render AgentLoop in layout**

In the JSX, add AgentLoop between MessageList and InputBar:

```jsx
<div className="main">
  <MessageList messages={messages} />
  <AgentLoop toolEvents={toolEvents} turnMetrics={turnMetrics} />
  <InputBar onSend={handleSend} disabled={sending} />
</div>
```

Add import at top:

```javascript
import AgentLoop from './components/AgentLoop';
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "wire AgentLoop into chat layout"
```

---

### Task 5: Frontend — Add CSS styles

**Files:**
- Modify: `frontend/src/App.css`

**Interfaces:**
- Consumes: AgentLoop component class names
- Produces: Visual styling

- [ ] **Step 1: Add agent loop styles**

Append to `frontend/src/App.css`:

```css
/* Agent Loop */
.agent-loop { border-top: 1px solid #eee; padding: 8px 16px; max-height: 200px; overflow-y: auto; background: #fafafa; }
.agent-loop-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.agent-loop-title { font-size: 11px; font-weight: 600; text-transform: uppercase; color: #888; letter-spacing: 0.5px; }
.agent-loop-metrics { font-size: 11px; color: #999; }
.agent-loop-events { display: flex; flex-direction: column; gap: 4px; }

.tool-card { border-left: 3px solid #ccc; background: #fff; border-radius: 0 4px 4px 0; }
.tool-header { display: flex; align-items: center; gap: 6px; width: 100%; padding: 6px 10px; border: none; background: none; cursor: pointer; font-size: 13px; text-align: left; }
.tool-header:hover { background: #f5f5f5; }
.tool-icon { font-size: 12px; }
.tool-name { font-weight: 600; color: #333; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 12px; }
.tool-turn { color: #999; font-size: 11px; margin-left: auto; }
.tool-chevron { color: #999; font-size: 10px; }
.tool-details { padding: 4px 10px 8px; }
.tool-section { margin-bottom: 4px; }
.tool-section label { display: block; font-size: 10px; font-weight: 600; text-transform: uppercase; color: #888; margin-bottom: 2px; }
.tool-section pre { background: #f5f5f5; padding: 6px 8px; border-radius: 3px; font-size: 11px; overflow-x: auto; margin: 0; white-space: pre-wrap; word-break: break-word; max-height: 80px; overflow-y: auto; }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.css
git commit -m "add agent loop styles"
```

---

### Task 6: Integration test

**Files:**
- Test: `frontend/tests/agent-loop.test.jsx` (or manual verification)

**Interfaces:**
- Consumes: All previous tasks
- Produces: Verified end-to-end flow

- [ ] **Step 1: Start backend + frontend**

```bash
docker compose up -d --build
cd frontend && npm run dev
```

- [ ] **Step 2: Send a message that triggers tools**

In the frontend, send: "search my memory for trading strategies"

Expected: Agent loop panel shows tool cards for `search_memory` with args and result, turn metrics update after each turn.

- [ ] **Step 3: Verify backward compatibility**

Send a simple message: "hello"

Expected: Only text events, agent loop panel hidden (no tool events).

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend && npx vitest run
```

Expected: PASS

- [ ] **Step 5: Final commit**

```bash
git add -A && git commit -m "observable agent loop: backend yields tool events, frontend renders them"
```
