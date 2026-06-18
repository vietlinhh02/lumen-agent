#!/usr/bin/env python3
"""
End-to-end test for the ReAct agent chat flow.

Tests:
1. Create a session
2. Send a chat message
3. Stream SSE events and display them
"""

import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx


BASE_URL = "http://localhost:8000/api/assistant"

# Test user credentials (replace with valid ones)
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword"


async def get_token() -> str | None:
    """Get auth token."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/sessions",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                timeout=5.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("token")
        except Exception as e:
            print(f"Auth error: {e}")
    return None


async def create_session(token: str) -> str | None:
    """Create a new session."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/sessions",
                headers={"Authorization": f"Bearer {token}"},
                json={},
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                print(f"Created session: {data.get('id')}")
                return data.get("id")
            else:
                print(f"Failed to create session: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Create session error: {e}")
    return None


async def send_chat_stream(session_id: str, message: str, token: str):
    """Send a chat message and stream SSE events."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            print(f"\n{'='*60}")
            print(f" Sending: {message}")
            print(f"{'='*60}\n")
            
            async with client.stream(
                "POST",
                f"{BASE_URL}/sessions/{session_id}/chat",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"message": message},
            ) as resp:
                print(f"Status: {resp.status_code}")
                
                if resp.status_code != 200:
                    print(f"Error: {await resp.text()}")
                    return
                
                event_count = 0
                tool_calls = []
                thoughts = []
                iterations = []
                
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    
                    # SSE format: "event: <type>" or "data: <json>"
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        continue
                    
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        try:
                            data = json.loads(data_str)
                            event_count += 1
                            
                            event_name = data.get("type", "unknown")
                            print(f"  [{event_count}] {event_name}")
                            
                            if event_name == "thought":
                                delta = data.get("delta", "")
                                iteration = data.get("iteration", "?")
                                thoughts.append(delta)
                                # Print first 50 chars
                                print(f"       → {delta[:80]}{'...' if len(delta) > 80 else ''}")
                            
                            elif event_name == "iteration":
                                n = data.get("n", "?")
                                phase = data.get("phase", "?")
                                max_n = data.get("max", "?")
                                iterations.append(n)
                                print(f"       → Iteration {n}/{max_n} ({phase})")
                            
                            elif event_name == "tool":
                                name = data.get("function", data.get("name", "?"))
                                status = data.get("status", "?")
                                tool_calls.append(name)
                                print(f"       → Tool: {name} ({status})")
                            
                            elif event_name == "message":
                                role = data.get("role", "?")
                                content = data.get("content", "")
                                print(f"       → {role}: {content[:100]}{'...' if len(content) > 100 else ''}")
                            
                            elif event_name == "done":
                                summary = data.get("summary", "")
                                print(f"       → Done: {summary}")
                            
                            elif event_name == "error":
                                code = data.get("code", "?")
                                msg = data.get("message", "")
                                print(f"       → ERROR {code}: {msg}")
                            
                            elif event_name == "wait":
                                question = data.get("question", "")
                                print(f"       → WAIT: {question[:80]}...")
                            
                            else:
                                print(f"       → {json.dumps(data)[:100]}")
                                
                        except json.JSONDecodeError:
                            pass
                
                print(f"\n{'='*60}")
                print("SUMMARY")
                print(f"{'='*60}")
                print(f"Total events: {event_count}")
                print(f"Iterations: {len(iterations)} ({iterations})")
                print(f"Tool calls: {len(tool_calls)} ({tool_calls})")
                print(f"Thought chunks: {len(thoughts)}")
                print(f"Total thought chars: {sum(len(t) for t in thoughts)}")
                
        except Exception as e:
            print(f"Chat error: {e}")
            import traceback
            traceback.print_exc()


async def test_scenarios(token: str):
    """Run test scenarios."""
    # Create a session for testing
    session_id = await create_session(token)
    if not session_id:
        print("Failed to create session")
        return
    
    scenarios = [
        ("list my projects", "Direct intent - should use no LLM"),
        ("find 5 papers about machine learning", "Search intent - should call search_papers"),
        ("help me", "Ambiguous - should return WaitEvent"),
        ("generate a report", "Report intent - should generate report"),
    ]
    
    for message, description in scenarios:
        print(f"\n\n{'#'*60}")
        print(f"TEST: {description}")
        print(f"#'*60")
        await send_chat_stream(session_id, message, token)
        
        # Wait between tests
        await asyncio.sleep(1)


async def main():
    print("="*60)
    print("ReAct Agent E2E Test")
    print("="*60)
    
    # Try to get token (may fail if no valid user)
    token = await get_token()
    
    if not token:
        # Try anonymous access or use a test endpoint
        print("No auth token - trying session creation directly...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Try to create session without auth
                resp = await client.post(f"{BASE_URL}/sessions", json={})
                print(f"Session creation (no auth): {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    session_id = data.get("id")
                    print(f"Session ID: {session_id}")
                else:
                    print(f"Response: {resp.text}")
                    print("\nNOTE: You may need to start the frontend or use a valid auth token.")
                    print("Try running with a valid user token:")
                    print("  export TOKEN=your_jwt_token")
                    return
            except Exception as e:
                print(f"Error: {e}")
                print("\nMake sure the backend is running on http://localhost:8000")
                return
    
    # Run tests
    await test_scenarios(token)


if __name__ == "__main__":
    # Check for token in environment
    token = os.environ.get("TOKEN")
    if token:
        asyncio.run(test_scenarios(token))
    else:
        asyncio.run(main())
