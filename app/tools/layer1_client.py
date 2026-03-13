import httpx
from app.config import get_settings
from app.utils import log

settings = get_settings()


class Layer1Client:
    def __init__(self, base_url: str = None, secret: str = None):
        self.base_url = base_url or settings.layer1_base_url
        self.secret = secret or settings.autodocs_shared_secret
        self._headers = {"X-AUTODOCS-SECRET": self.secret, "Content-Type": "application/json"}

    async def fetch_file(self, path: str, repo: str, owner: str, branch: str, installation_id: int = None) -> str:
        """Fetch raw file content from Layer1 (/files/file-content)."""
        url = f"{self.base_url}/files/file-content"
        params = {"path": path, "repo": repo, "owner": owner, "branch": branch}
        if installation_id:
            params["installationId"] = installation_id
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers, params=params)
            resp.raise_for_status()
            return resp.json().get("content", "")

    async def fetch_diff(self, path: str, repo: str, owner: str, branch: str, commit_id: str, installation_id: int = None) -> str:
        """Fetch diff for a file from Layer1 (/files/file-diff)."""
        url = f"{self.base_url}/files/file-diff"
        params = {"path": path, "repo": repo, "owner": owner, "branch": branch, "commit_id": commit_id}
        if installation_id:
            params["installationId"] = installation_id
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers, params=params)
            resp.raise_for_status()
            return resp.json().get("diff", "")

    async def patch_files(self, owner: str, repo: str, branch: str, files: list) -> dict:
        """Send file patches to Layer1 to apply."""
        url = f"{self.base_url}/apply-patch"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers, json={
                "owner": owner, "repo": repo, "branch": branch, "files": files
            })
            resp.raise_for_status()
            return resp.json()
