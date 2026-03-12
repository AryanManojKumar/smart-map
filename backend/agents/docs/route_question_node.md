# route_question_node — Route Q&A

## Purpose
Answer detailed questions about the currently active route using the pre-built route context document. Provides data-backed answers about highways, turns, distances, road surfaces, lanes, and more.

## When to use
- There IS an active route (`route_data` exists) AND user asks about it
- Examples: "how many highways?", "list the turns", "any tolls?", "total distance on NH?", "what roads?", "how many lanes?", "kitne tolls lagenge?"

## When NOT to use
- No active route exists — use **conversation_node** (which will suggest getting a route first)
- User wants a NEW route — use **routing_node**
- User wants to find places — use **search_node**

## Inputs
- `route_context`: Pre-built text document containing all route details (built by `build_route_context`)
- `route_data`: Raw route object for fallback context rebuilding
- `messages`: Recent conversation history

## Tools
None — this node is purely LLM reasoning over the route_context document.

## Behavior
1. Uses GPT-5-2 with the full route context as a reference document
2. Answers ONLY from the data — never makes up information
3. Uses road names, numbers, distances from the actual route data
4. Formats answers with bullet points and lists for readability

## Output state
- `current_intent`: "route_question"
- No state mutations — just adds an answer message
