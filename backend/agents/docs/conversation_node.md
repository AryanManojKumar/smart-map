# conversation_node — General chat

## Purpose
Handle general conversation, greetings, help requests, and off-topic messages that don't fit routing, search, or route questions.

## When to use
- Greetings: "hi", "hello", "hey"
- Help requests: "what can you do?", "kya kya kar sakte ho?"
- Off-topic: anything not navigation-related
- Ambiguous messages that don't clearly fit other intents

## When NOT to use
- Any navigation or routing request — use **routing_node**
- Any place/POI discovery request — use **search_node**
- Questions about active route — use **route_question_node**
- Location disambiguation — use **disambiguation_node**

## Inputs
- `messages`: Conversation history for context
- `route_data`: Optional — if active route exists, conversation_node mentions it

## Tools
None — pure LLM conversation.

## Behavior
1. Uses GPT-5-2 for natural, friendly responses
2. Aware of Nav AI's capabilities (routing, search, route Q&A)
3. If an active route exists, can suggest asking about it
4. Responds in the user's language (Hindi/Hinglish/English)
