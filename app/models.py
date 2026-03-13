from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class OptionalPayload(BaseModel):
    diffs: Optional[Dict[str, str]] = None
    repo_size_commits: Optional[int] = None


class ProcessChangeRequest(BaseModel):
    repo: str
    owner: str
    branch: str
    installationId: int
    commitMessage: str
    commitId: str
    changedFiles: List[str]
    optional: Optional[OptionalPayload] = None


class SourceRef(BaseModel):
    path: str
    lines: str
    score: float


class FileUpdate(BaseModel):
    path: str
    content: str
    confidence: str
    sources: List[SourceRef]
    marker_section: Optional[str] = None


class ProcessChangeResponse(BaseModel):
    files_to_update: List[FileUpdate]
    pr_title: Optional[str]
    pr_body: str
    confidence: Optional[str]


class FileSummary(BaseModel):
    file_path: str
    summary: str
    score: float
    last_updated_commit: Optional[str]


class GraphState(BaseModel):
    request: ProcessChangeRequest
    repo_id: str = ""
    changed_summaries: List[Dict[str, Any]] = []
    retrieved_context: List[Dict[str, Any]] = []
    impact_result: Dict[str, Any] = {}
    generated_files: List[FileUpdate] = []
    pr_title: Optional[str] = None
    pr_body: str = ""
    overall_confidence: Optional[str] = None
    error: Optional[str] = None
    skip_generation: bool = False

    class Config:
        arbitrary_types_allowed = True
