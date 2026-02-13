"""
Usage Examples for graph.py - MemOS Conversation Interface

This file demonstrates how to use the MemOS Graph for conversations.
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the chat function
from graph import chat, chat_sync


# ============================================================================
# Example 1: Simple Text Conversation (Async)
# ============================================================================

async def example_simple_chat():
    """Simple async chat example"""
    print("=" * 60)
    print("Example 1: Simple Chat")
    print("=" * 60)

    # Call the chat function
    result = await chat(
        user_input="Tell me about the MemOS project",
        session_id="user-001"  # Unique session ID for conversation tracking
    )

    # Print the response
    print(f"Intent: {result['intent']}")
    print(f"Response: {result['response']}")
    print(f"Metadata: {result['metadata']}")


# ============================================================================
# Example 2: Sync Wrapper (for non-async code)
# ============================================================================

def example_sync_chat():
    """Synchronous chat example"""
    print("\n" + "=" * 60)
    print("Example 2: Sync Chat")
    print("=" * 60)

    # Use the sync wrapper
    result = chat_sync(
        user_input="What technology stack are we using?",
        session_id="user-002"
    )

    print(f"Intent: {result['intent']}")
    print(f"Response: {result['response'][:200]}...")  # Truncate long response


# ============================================================================
# Example 3: Chat with Attachments (Multimodal)
# ============================================================================

async def example_chat_with_attachment():
    """Chat with image attachment"""
    print("\n" + "=" * 60)
    print("Example 3: Chat with Image Attachment")
    print("=" * 60)

    result = await chat(
        user_input="What do you see in this image?",
        attachments=[
            {
                "url": "https://example.com/screenshot.png",
                "mime_type": "image/png"
            }
        ],
        session_id="user-003"
    )

    print(f"Response: {result['response']}")
    print(f"Has attachments: {result['metadata'].get('has_attachments', False)}")


# ============================================================================
# Example 4: Interactive Chat Loop
# ============================================================================

async def interactive_chat():
    """Interactive chat session"""
    print("\n" + "=" * 60)
    print("Example 4: Interactive Chat (type 'quit' to exit)")
    print("=" * 60)

    session_id = "interactive-session-001"

    while True:
        # Get user input
        user_input = input("\nYou: ").strip()

        if user_input.lower() in ['quit', 'exit', 'bye']:
            print("Goodbye!")
            break

        if not user_input:
            continue

        # Send to MemOS
        try:
            result = await chat(
                user_input=user_input,
                session_id=session_id
            )

            print(f"\nMemOS: {result['response']}")
            print(f"[Intent: {result['intent']}, Entities: {result['metadata'].get('total_entities', 0)}]")

        except Exception as e:
            print(f"Error: {e}")


# ============================================================================
# Example 5: Web API Integration (FastAPI)
# ============================================================================

def example_fastapi_integration():
    """Example FastAPI integration code"""
    example_code = '''
# fastapi_app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from graph import chat

app = FastAPI(title="MemOS API")

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    attachments: Optional[List[dict]] = None

class ChatResponse(BaseModel):
    response: str
    intent: str
    metadata: dict

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Main chat endpoint"""
    try:
        result = await chat(
            user_input=request.message,
            session_id=request.session_id,
            attachments=request.attachments
        )

        return ChatResponse(
            response=result["response"],
            intent=result["intent"],
            metadata=result["metadata"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "memos"}

# Run with: uvicorn fastapi_app:app --host 0.0.0.0 --port 8000
'''
    print("\n" + "=" * 60)
    print("Example 5: FastAPI Integration")
    print("=" * 60)
    print(example_code)


# ============================================================================
# Example 6: Streamlit Web Interface
# ============================================================================

def example_streamlit_integration():
    """Example Streamlit integration code"""
    example_code = '''
# streamlit_app.py
import streamlit as st
import asyncio
from graph import chat

st.title("MemOS - AI Memory System")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit-{id(st.session_state)}"

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("What would you like to know?"):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get AI response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = asyncio.run(chat(
                user_input=prompt,
                session_id=st.session_state.session_id
            ))
            st.markdown(result["response"])

            # Show metadata
            with st.expander("Debug Info"):
                st.json(result["metadata"])

    # Add to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": result["response"]
    })

# Run with: streamlit run streamlit_app.py
'''
    print("\n" + "=" * 60)
    print("Example 6: Streamlit Web Interface")
    print("=" * 60)
    print(example_code)


# ============================================================================
# Main
# ============================================================================

async def main():
    """Run all examples"""

    # Example 1: Simple async chat
    await example_simple_chat()

    # Example 2: Sync chat
    example_sync_chat()

    # Example 3: Chat with attachment
    # await example_chat_with_attachment()

    # Example 4: Interactive (commented out for non-interactive runs)
    # await interactive_chat()

    # Example 5 & 6: Integration code
    example_fastapi_integration()
    example_streamlit_integration()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
