from app.agent.schemas.chat import (
    AssistantMessage,
    FunctionCall,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)


def test_message_schemas():
    system = SystemMessage(content="sys")
    assert system.role == "system"

    user = HumanMessage(content="hi")
    assert user.role == "user"

    assistant = AssistantMessage(content="hello", reasoning_content="think")
    assert assistant.role == "assistant"
    assert assistant.reasoning_content == "think"

    tool_msg = ToolMessage(content="res", tool_call_id="123")
    assert tool_msg.role == "tool"
    assert tool_msg.tool_call_id == "123"


def test_tool_call_schema():
    tc = ToolCall(id="call_1", function=FunctionCall(name="test", arguments='{"a": 1}'))
    assert tc.type == "function"
    assert tc.function.name == "test"
