from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class SearchAgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    route_data: dict
    location: dict
    search_results: list

class SupervisorState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    route_data: dict
    location: dict
    current_intent: str
