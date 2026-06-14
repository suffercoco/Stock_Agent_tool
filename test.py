import json
from openai import OpenAI
from computer_use import *

client = OpenAI(base_url="http://127.0.0.1:1234/v1", api_key="lm-studio")

# Map tool names -> real python functions the model is allowed to call
available_tools = {
    "plus": plus,
}

tools = [
    {
        "type": "function",
        "function": {
            "name": "plus",
            "description": "Return the sum for 2 numbers",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "The first number for sum"},
                    "b": {"type": "number", "description": "the second number for sum"},
                },
                "required": ["a", "b"],
            },
        },
    }
]

messages = [
    {
        "role": "user",
        "content": "You are a helpful math assistent, plz calculate 1203+9902 for me.",
    }
]

# --- 1st call: model decides to request a tool call ---
resp = client.chat.completions.create(
    model="google/gemma-4-e4b",
    messages=messages,
    tools=tools,
)

msg = resp.choices[0].message
messages.append(msg)  # keep the assistant's tool-call turn in history

if msg.tool_calls:
    for call in msg.tool_calls:
        fn_name = call.function.name
        args = json.loads(call.function.arguments)  # arguments come back as a JSON string
        print(f"Model requested: {fn_name}({args})")

        result = available_tools[fn_name](**args)  # YOU run the real function
        print(f"Local result: {result}")

        # --- send the result back as a tool message ---
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result),
            }
        )

    # --- 2nd call: model turns the tool result into a final answer ---
    final = client.chat.completions.create(
        model="google/gemma-4-e4b",
        messages=messages,
        tools=tools,
    )
    print("Final answer:", final.choices[0].message.content)
else:
    print("No tool call. Direct answer:", msg.content)
