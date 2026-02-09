# Testing Guide

Comprehensive testing strategies for the Speech-to-Speech AI system.

## 🧪 Testing Strategy Overview

```
Unit Tests → Integration Tests → E2E Tests → Manual Tests → Load Tests
```

## 🔬 Unit Testing

### Backend Unit Tests

**Test file: `backend/test_layers.py`**

```python
import pytest
from unittest.mock import Mock, AsyncMock, patch
from models import Message, STTResult
from orchestrator import ConversationOrchestrator
from llm_layer import LLMLayer
from tts_layer import TTSLayer
from stt_layer import STTLayer


class TestSTTLayer:
    """Test STT layer independently."""
    
    @pytest.mark.asyncio
    async def test_stt_initialization(self):
        """Test STT layer can be initialized."""
        callback = Mock()
        stt = STTLayer(on_transcript=callback)
        assert stt.is_active == False
    
    @pytest.mark.asyncio
    async def test_stt_receives_final_transcript(self):
        """Test STT layer processes final transcripts."""
        received_results = []
        
        def callback(result: STTResult):
            received_results.append(result)
        
        stt = STTLayer(on_transcript=callback)
        # Mock Deepgram response
        # ... test implementation


class TestLLMLayer:
    """Test LLM layer independently."""
    
    @pytest.mark.asyncio
    async def test_llm_generates_response(self):
        """Test LLM generates streaming response."""
        llm = LLMLayer()
        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello")
        ]
        
        response = []
        async for chunk in llm.generate_response(messages):
            response.append(chunk)
        
        assert len(response) > 0
        full_response = "".join(response)
        assert len(full_response) > 0


class TestTTSLayer:
    """Test TTS layer with different providers."""
    
    @pytest.mark.asyncio
    async def test_tts_mock_provider(self):
        """Test TTS with mock provider."""
        tts = TTSLayer(provider="mock")
        
        chunks = []
        async for chunk in tts.speak("Hello world"):
            chunks.append(chunk)
        
        assert len(chunks) > 0
    
    @pytest.mark.asyncio
    async def test_tts_interruption(self):
        """Test TTS can be interrupted."""
        tts = TTSLayer(provider="mock")
        
        # Start speaking
        task = asyncio.create_task(
            tts.speak("This is a long sentence that should be interrupted")
        )
        
        # Interrupt after short delay
        await asyncio.sleep(0.1)
        tts.stop()
        
        await task
        assert tts.is_speaking == False


class TestOrchestrator:
    """Test conversation orchestrator."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_state_transitions(self):
        """Test state machine transitions."""
        transcript_events = []
        audio_events = []
        
        def on_transcript(event):
            transcript_events.append(event)
        
        def on_audio(data):
            audio_events.append(data)
        
        orchestrator = ConversationOrchestrator(
            session_id="test",
            system_prompt="Test prompt",
            on_transcript_event=on_transcript,
            on_audio_output=on_audio
        )
        
        # Initial state should be LISTENING
        assert orchestrator.get_state() == ConversationState.LISTENING
        
        # Simulate final transcript
        result = STTResult(
            text="Hello",
            is_final=True,
            speech_final=True
        )
        orchestrator._handle_stt_result(result)
        
        # Should transition to THINKING
        await asyncio.sleep(0.1)
        assert orchestrator.get_state() in [
            ConversationState.THINKING,
            ConversationState.SPEAKING
        ]
```

**Run unit tests:**
```bash
cd backend
pip install pytest pytest-asyncio
pytest test_layers.py -v
```

---

## 🔗 Integration Testing

### Backend Integration Tests

**Test file: `backend/test_integration.py`**

```python
import pytest
from httpx import AsyncClient
from main import app


@pytest.mark.asyncio
async def test_create_session():
    """Test session creation endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/session",
            json={"system_prompt": "Test prompt"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0


@pytest.mark.asyncio
async def test_get_session_state():
    """Test getting session state."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create session
        response = await client.post(
            "/session",
            json={"system_prompt": "Test"}
        )
        session_id = response.json()["session_id"]
        
        # Get state
        response = await client.get(f"/session/{session_id}/state")
        assert response.status_code == 200
        
        data = response.json()
        assert "state" in data
        assert "messages" in data


@pytest.mark.asyncio
async def test_delete_session():
    """Test session deletion."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create session
        response = await client.post(
            "/session",
            json={"system_prompt": "Test"}
        )
        session_id = response.json()["session_id"]
        
        # Delete session
        response = await client.delete(f"/session/{session_id}")
        assert response.status_code == 200
        
        # Verify deleted
        response = await client.get(f"/session/{session_id}/state")
        assert response.status_code == 404
```

**Run integration tests:**
```bash
pytest test_integration.py -v
```

---

## 🌐 End-to-End Testing

### E2E Test with Playwright

**Test file: `frontend/e2e/conversation.spec.ts`**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Speech-to-Speech Conversation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
  });

  test('should show UI elements', async ({ page }) => {
    // Check header
    await expect(page.locator('h1')).toHaveText('Speech-to-Speech AI');
    
    // Check mic button
    const micButton = page.locator('button').first();
    await expect(micButton).toBeVisible();
    
    // Check transcript panel
    const panel = page.locator('.flex-1');
    await expect(panel).toBeVisible();
  });

  test('should connect to backend', async ({ page }) => {
    // Grant microphone permission
    await page.context().grantPermissions(['microphone']);
    
    // Click mic button
    await page.click('button');
    
    // Check connection status
    const status = page.locator('text=Connected');
    await expect(status).toBeVisible({ timeout: 5000 });
  });

  test('should show transcript after speaking', async ({ page, context }) => {
    await context.grantPermissions(['microphone']);
    
    // Start recording
    await page.click('button');
    
    // Wait for transcripts (mock or real)
    await page.waitForSelector('text=/Hello/', { timeout: 10000 });
    
    // Check message appears
    const message = page.locator('div').filter({ hasText: 'Hello' });
    await expect(message).toBeVisible();
  });
});
```

**Run E2E tests:**
```bash
cd frontend
npm install -D @playwright/test
npx playwright test
```

---

## 🎯 Manual Testing Checklist

### Basic Functionality

- [ ] Server starts without errors
- [ ] Frontend loads at http://localhost:3000
- [ ] Connection status shows "Connected"
- [ ] Mic button is visible and clickable

### Audio Input

- [ ] Browser requests microphone permission
- [ ] Mic button shows "Listening" when active
- [ ] Partial transcripts appear while speaking (gray text)
- [ ] Final transcripts appear after stopping (black text)
- [ ] Transcripts are accurate

### AI Response

- [ ] AI responds after user stops speaking
- [ ] Response appears in transcript
- [ ] Audio plays through speakers
- [ ] Response is relevant to user input

### Barge-in (Interruption)

- [ ] Start conversation with AI
- [ ] While AI is speaking, start speaking
- [ ] AI stops immediately
- [ ] User's new input is processed
- [ ] AI responds to new input

### State Transitions

- [ ] Initial state: Ready
- [ ] After speaking: Processing
- [ ] While AI talks: Speaking
- [ ] After AI finishes: Back to ready

### Error Handling

- [ ] Invalid API key shows error
- [ ] Network disconnect shows error
- [ ] Microphone denied shows error
- [ ] Session deletion works

---

## 📊 Load Testing

### Using Locust

**Test file: `backend/locustfile.py`**

```python
from locust import HttpUser, task, between
import json


class SpeechUser(HttpUser):
    wait_time = between(1, 5)
    session_id = None
    
    def on_start(self):
        """Create session when user starts."""
        response = self.client.post(
            "/session",
            json={"system_prompt": "You are helpful"},
            headers={"Content-Type": "application/json"}
        )
        self.session_id = response.json()["session_id"]
    
    @task(3)
    def get_state(self):
        """Get session state."""
        if self.session_id:
            self.client.get(f"/session/{self.session_id}/state")
    
    @task(1)
    def create_session(self):
        """Create new session."""
        self.client.post(
            "/session",
            json={"system_prompt": "Test prompt"}
        )
    
    def on_stop(self):
        """Clean up session."""
        if self.session_id:
            self.client.delete(f"/session/{self.session_id}")
```

**Run load tests:**
```bash
pip install locust
locust -f locustfile.py --host=http://localhost:8000
```

Open http://localhost:8089 and configure:
- Number of users: 100
- Spawn rate: 10/second

---

## 🔍 Testing Different Components

### 1. Test STT Only

```python
# test_stt_only.py
import asyncio
from stt_layer import STTLayer

async def test_stt():
    def on_transcript(result):
        print(f"{'[PARTIAL]' if not result.is_final else '[FINAL]'} {result.text}")
    
    stt = STTLayer(on_transcript)
    await stt.start()
    
    # Send mock audio or record from mic
    # ...
    
    await asyncio.sleep(10)
    await stt.stop()

asyncio.run(test_stt())
```

### 2. Test LLM Only

```python
# test_llm_only.py
import asyncio
from llm_layer import LLMLayer
from models import Message

async def test_llm():
    llm = LLMLayer()
    
    messages = [
        Message(role="system", content="You are helpful"),
        Message(role="user", content="Tell me a joke")
    ]
    
    print("Response: ", end="")
    async for chunk in llm.generate_response(messages):
        print(chunk, end="", flush=True)
    print()

asyncio.run(test_llm())
```

### 3. Test TTS Only

```python
# test_tts_only.py
import asyncio
from tts_layer import TTSLayer

async def test_tts():
    tts = TTSLayer(provider="mock")  # or "deepgram"
    
    print("Speaking...")
    chunk_count = 0
    async for chunk in tts.speak("Hello, this is a test of text to speech."):
        chunk_count += 1
        # Could save to file or play
    
    print(f"Received {chunk_count} audio chunks")

asyncio.run(test_tts())
```

---

## 🐛 Testing Edge Cases

### Test Scenarios

1. **Empty audio stream**
   - Send silence to STT
   - Verify no false transcripts

2. **Rapid barge-in**
   - Interrupt AI multiple times quickly
   - Verify state consistency

3. **Long response**
   - User asks complex question
   - Verify streaming works correctly

4. **Network interruption**
   - Disconnect WebSocket mid-conversation
   - Verify graceful handling

5. **API rate limits**
   - Send many requests quickly
   - Verify error handling

6. **Multiple concurrent sessions**
   - Create 10+ sessions simultaneously
   - Verify isolation

### Testing Script

```python
# test_edge_cases.py
import asyncio
import httpx

async def test_multiple_sessions():
    """Test multiple concurrent sessions."""
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(10):
            task = client.post(
                "http://localhost:8000/session",
                json={"system_prompt": f"Session {i}"}
            )
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        
        # Verify all succeeded
        session_ids = []
        for response in responses:
            assert response.status_code == 200
            session_ids.append(response.json()["session_id"])
        
        print(f"Created {len(session_ids)} sessions")
        
        # Clean up
        for session_id in session_ids:
            await client.delete(f"http://localhost:8000/session/{session_id}")

asyncio.run(test_multiple_sessions())
```

---

## 📈 Performance Testing

### Measure Latency

```python
# test_latency.py
import asyncio
import time
from models import Message
from llm_layer import LLMLayer
from tts_layer import TTSLayer

async def measure_llm_latency():
    """Measure LLM first-token latency."""
    llm = LLMLayer()
    
    messages = [
        Message(role="user", content="Hello")
    ]
    
    start = time.time()
    first_token = None
    
    async for chunk in llm.generate_response(messages):
        if first_token is None:
            first_token = time.time()
        break
    
    latency = (first_token - start) * 1000
    print(f"LLM first token latency: {latency:.0f}ms")

async def measure_tts_latency():
    """Measure TTS latency."""
    tts = TTSLayer(provider="mock")
    
    start = time.time()
    first_chunk = None
    
    async for chunk in tts.speak("Hello world"):
        if first_chunk is None:
            first_chunk = time.time()
        break
    
    latency = (first_chunk - start) * 1000
    print(f"TTS first chunk latency: {latency:.0f}ms")

async def main():
    await measure_llm_latency()
    await measure_tts_latency()

asyncio.run(main())
```

---

## ✅ Test Coverage Goals

### Backend
- [ ] Unit tests for all layers (80%+ coverage)
- [ ] Integration tests for API endpoints (100% coverage)
- [ ] WebSocket connection tests
- [ ] State machine transition tests
- [ ] Error handling tests

### Frontend
- [ ] Component unit tests (70%+ coverage)
- [ ] Integration tests for WebSocket
- [ ] E2E tests for user flows
- [ ] Audio handling tests
- [ ] Error state tests

### System
- [ ] End-to-end conversation tests
- [ ] Barge-in behavior tests
- [ ] Load tests (100+ concurrent users)
- [ ] Latency measurements
- [ ] Error recovery tests

---

## 🚀 Continuous Integration

### GitHub Actions Workflow

**.github/workflows/test.yml:**

```yaml
name: Test

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      
      - name: Run tests
        run: |
          cd backend
          pytest --cov=. --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v2

  frontend-tests:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Node
        uses: actions/setup-node@v2
        with:
          node-version: 18
      
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Run tests
        run: |
          cd frontend
          npm test -- --coverage
```

---

## 🎓 Best Practices

1. **Test in isolation** - Each layer independently
2. **Mock external APIs** - Don't hit real APIs in tests
3. **Test edge cases** - Not just happy path
4. **Measure performance** - Track latency over time
5. **Automate tests** - Run on every commit
6. **Test error handling** - Verify graceful failures
7. **Load test** - Ensure scalability
8. **Monitor in production** - Real-world behavior

---

## Summary

Testing ensures:
- ✅ Components work individually
- ✅ System works end-to-end
- ✅ Errors are handled gracefully
- ✅ Performance is acceptable
- ✅ Code quality is maintained
- ✅ Regressions are caught early
