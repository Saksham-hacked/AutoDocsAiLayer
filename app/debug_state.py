"""
State persistence utility for debugging LangGraph executions.
Stores the full state after each pipeline run for inspection.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from app.models import GraphState


def _ensure_debug_dir() -> Path:
    """Ensure debug directory exists."""
    debug_dir = Path("debug_states")
    debug_dir.mkdir(exist_ok=True)
    return debug_dir


def _serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert GraphState dict to JSON-serializable format.
    Handles Pydantic models and other non-serializable objects.
    """
    serialized = {}
    
    for key, value in state.items():
        try:
            # Try direct serialization first
            json.dumps(value)
            serialized[key] = value
        except (TypeError, ValueError):
            # Handle Pydantic models
            if hasattr(value, 'model_dump'):
                serialized[key] = value.model_dump()
            elif hasattr(value, 'dict'):
                serialized[key] = value.dict()
            # Handle lists of Pydantic models
            elif isinstance(value, list) and len(value) > 0 and hasattr(value[0], 'model_dump'):
                serialized[key] = [item.model_dump() for item in value]
            elif isinstance(value, list) and len(value) > 0 and hasattr(value[0], 'dict'):
                serialized[key] = [item.dict() for item in value]
            else:
                # Fallback to string representation
                serialized[key] = str(value)
    
    return serialized


def save_debug_state(state: Dict[str, Any], repo: str, commit_id: str) -> str:
    """
    Save the final LangGraph state to a JSON file for debugging.
    
    Args:
        state: The final state dict from LangGraph
        repo: Repository name
        commit_id: Commit ID
    
    Returns:
        Path to the saved state file
    """
    debug_dir = _ensure_debug_dir()
    
    # Create filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_repo = repo.replace("/", "_").replace("\\", "_")
    short_commit = commit_id[:7] if commit_id else "unknown"
    filename = f"state_{safe_repo}_{short_commit}_{timestamp}.json"
    filepath = debug_dir / filename
    
    # Serialize state
    serialized = _serialize_state(state)
    
    # Add metadata
    debug_data = {
        "metadata": {
            "repo": repo,
            "commit_id": commit_id,
            "timestamp": datetime.utcnow().isoformat(),
            "saved_at": str(filepath),
        },
        "state": serialized
    }
    
    # Write to file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(debug_data, f, indent=2, ensure_ascii=False)
    
    return str(filepath)


def load_debug_state(filepath: str) -> Dict[str, Any]:
    """
    Load a previously saved debug state.
    
    Args:
        filepath: Path to the saved state file
    
    Returns:
        The loaded state dict
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        debug_data = json.load(f)
    
    return debug_data


def list_debug_states(repo: str = None, limit: int = 10) -> list[Dict[str, str]]:
    """
    List available debug state files.
    
    Args:
        repo: Optional repo filter (e.g., "acme_my-api")
        limit: Maximum number of files to return
    
    Returns:
        List of state file info dicts with path, repo, commit, timestamp
    """
    debug_dir = _ensure_debug_dir()
    
    # Get all JSON files
    pattern = f"state_{repo}*" if repo else "state_*"
    files = list(debug_dir.glob(f"{pattern}.json"))
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    # Return info about each file
    result = []
    for filepath in files[:limit]:
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                metadata = data.get("metadata", {})
                result.append({
                    "path": str(filepath),
                    "repo": metadata.get("repo", "unknown"),
                    "commit_id": metadata.get("commit_id", "unknown"),
                    "timestamp": metadata.get("timestamp", "unknown"),
                })
        except Exception:
            # Skip corrupted files
            continue
    
    return result
