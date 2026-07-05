from typing import AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import load_config
from backend.chat_history import ChatHistoryStore, ChatMessage
from pydantic_ai import Agent

router = APIRouter()
_store = ChatHistoryStore()
_cfg = load_config()

class MessageRequest(BaseModel):
    content: str

@router.get("/history", response_model=list[ChatMessage])
async def get_history(limit: int = 100) -> list[ChatMessage]:
    return _store.get_messages(limit)

@router.post("/message")
async def send_message(req: MessageRequest):
    # Save user message
    _store.add_message("user", req.content)
    
    # Reload config for latest prompt
    global _cfg
    _cfg = load_config()
    
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # We must load history for context
            history = _store.get_messages(limit=10)
            
            model = _cfg.llm.model
            if model.startswith("gemini"):
                model = f"google:{model}"
            
            agent = Agent(
                model,
                system_prompt=_cfg.llm.assistant_prompt,
            )        
            
            # Using synchronous stream because run_stream is async and requires async contexts,
            # but we can use run_sync_stream or just run_sync for simplicity if we don't have async deps.
            # Let's use run_sync_stream for immediate streaming
            # Wait, pydantic-ai has `run_sync` and `run`. For streaming, it's `run_stream`.
            # Let's format history appropriately.
            
            # Pydantic AI v0.0.12 stream:
            # async with agent.run_stream(req.content) as result:
            #     async for chunk in result.stream_text():
            #         yield chunk
            
            # In pydantic-ai, message_history is a list of their native message types, 
            # but for simplicity we can just pass the latest message and it will be stateless,
            # OR we can pass history as text context.
            context = "\n".join([f"{m.role}: {m.content}" for m in history[:-1]])
            
            prompt = f"Chat history:\n{context}\n\nuser: {req.content}" if context else req.content
            
            full_response = ""
            async with agent.run_stream(prompt) as result:
                async for chunk in result.stream_text(delta=True):
                    full_response += chunk
                    yield chunk
            
            # Save assistant message when done
            _store.add_message("assistant", full_response)
        except Exception as e:
            import logging
            logging.getLogger("carefulwhisper.chat").exception("Chat failed")
            yield f"\n[Error: {str(e)}]"

    return StreamingResponse(event_generator(), media_type="text/plain")
