# Chat streaming test guide

This build keeps the existing `POST /api/v1/chat` endpoint and adds:

```text
POST /api/v1/chat/stream
Content-Type: application/json
Accept: text/event-stream
```

No new environment variables or Python/JavaScript packages are required. The
implementation uses the existing FastAPI, LangGraph, LiteLLM and browser Fetch
APIs.

The frontend applies a typewriter pace by default: two Unicode characters
every 20 ms. Both values are optional build-time settings:

```env
VITE_CHAT_STREAM_DELAY_MS=20
VITE_CHAT_STREAM_CHARS_PER_TICK=2
```

Increase the delay or reduce the characters per tick for slower output. Setting
the delay to `0` disables artificial pacing. Because these are Vite variables,
rebuild the frontend after changing them.

## 1. Test the backend stream directly

Start the backend as usual, then run:

```bash
curl -N http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"message":"VinWonders Nha Trang có những hoạt động gì?","session_id":"stream-test-001"}'
```

Expected event order:

```text
event: status
data: {"stage":"understanding"}

event: status
data: {"stage":"searching"}

event: delta
data: {"content":"..."}

event: replace
data: {"content":"...final verified answer..."}

event: complete
data: {"answer":"...","session_id":"...","sources":[]}
```

For a RAG request, `delta` appears multiple times as soon as the main answer
model starts generating. Grounding and language validation continue after the
visible draft. If either validation step changes it, one optional `replace`
event atomically updates the UI to the verified final answer. Static branches
that do not run the answer node stream from the final response-language guard.
The `complete` event includes the normal route, ticket, source and debug
metadata.

## 2. Test in the frontend

Start the frontend normally and open `/chat`:

Re-run the normal frontend build before deploying. The `frontend/dist` folder
included in the original archive is an older compiled snapshot and does not
contain these source changes until it is rebuilt.

1. Send a greeting to test a short non-RAG branch.
2. Ask a destination question to test retrieval and grounding progress.
3. Ask a price question to test a longer answer with Markdown and sources.
4. Press **Stop** while tokens are arriving. The browser should stop rendering
   immediately, including during the typewriter delay, and the interrupted turn
   should not be saved as a completed assistant response.
5. Open the compact chat widget and repeat a question. It uses the same stream.

## 3. Automated regression test

From the project root, run the existing backend test command. The new test file
is:

```text
src/backend/tests/test_chat_streaming_regression.py
```

It verifies event ordering, token concatenation, final response metadata and
that only the post-grounding language guard publishes visible tokens.

## Deployment note

The endpoint sends `Cache-Control: no-cache, no-transform` and
`X-Accel-Buffering: no` to discourage reverse-proxy buffering. If a separate
CDN or proxy is added later, make sure it does not buffer `text/event-stream`
responses.
