from langgraph.graph import StateGraph, END
from app.models import GraphState
from app.agents.classify_change import validate_input
from app.agents.update_memory import update_memory
from app.agents.retrieve_context import retrieve_context
from app.agents.impact_analysis import impact_analysis
from app.agents.generate_docs import generate_docs
from app.agents.confidence import confidence_check
from app.agents.format_response import format_response


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("validate_input", validate_input)
    g.add_node("update_memory", update_memory)
    g.add_node("retrieve_context", retrieve_context)
    g.add_node("impact_analysis", impact_analysis)
    g.add_node("generate_docs", generate_docs)
    g.add_node("confidence_check", confidence_check)
    g.add_node("format_response", format_response)

    g.set_entry_point("validate_input")
    g.add_edge("validate_input", "update_memory")
    g.add_edge("update_memory", "retrieve_context")
    g.add_edge("retrieve_context", "impact_analysis")
    g.add_edge("impact_analysis", "generate_docs")
    g.add_edge("generate_docs", "confidence_check")
    g.add_edge("confidence_check", "format_response")
    g.add_edge("format_response", END)

    return g.compile()


graph = build_graph()
