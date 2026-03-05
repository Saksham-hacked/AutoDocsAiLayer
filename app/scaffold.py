"""Scaffold docs structure for a new repo installation."""
from typing import List, Dict

SCAFFOLD_FILES = {
    "README.md": "OVERVIEW",
    "docs/api.md": "ROUTES",
    "docs/architecture.md": "MODULES",
    "docs/setup.md": "INSTALL",
    "docs/env.md": "ENV",
}


def scaffold_docs(repo_id: str, owner: str, branch: str) -> List[Dict]:
    """Return a patch list for Layer1 to create scaffolded doc files."""
    patches = []
    for path, marker in SCAFFOLD_FILES.items():
        content = (
            f"# {path.split('/')[-1].replace('.md','').title()}\n\n"
            f"<!-- AUTODOCS:{marker}_START -->\n"
            f"<!-- Managed by AutoDocs v1 — Changes may be overwritten -->\n"
            f"_Documentation will be auto-generated here._\n"
            f"<!-- AUTODOCS:{marker}_END -->\n"
        )
        patches.append({"path": path, "content": content})
    return patches
