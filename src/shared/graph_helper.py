"""Microsoft Graph client for SharePoint (WBS 4.2).

Folders, permanent links and file uploads. Email sending is added later, once
the Mail.Send permission is granted.

    graph = GraphClient.from_secrets()
    folder = graph.get_or_create_folder(existing_link, parent_id, "4601.Tanaka_Taro")
    graph.upload_file(folder["drive_id"], folder["id"], "resume.pdf", data)

It replaces the helpers that were copied into create_new_folder.py and
upload_files.py in Pipedream. Requires httpx and tenacity.
"""

import base64
import time
import urllib.parse

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt

from shared.secrets_helper import get_secrets

GRAPH_URL = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
RETRY_DELAY = 2  # seconds, as in the Pipedream steps
MAX_RETRY_AFTER = 30  # never wait longer than this, even if Graph asks for more


class GraphError(Exception):
    """Graph answered with an error status. .status and .body hold the details."""

    def __init__(self, status, body, url=""):
        super().__init__(f"Graph error {status} for {url}: {body[:300]}")
        self.status = status
        self.body = body


def _is_retryable(exc):
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRY_STATUSES
    return False


def _wait(retry_state):
    exc = retry_state.outcome.exception()
    if isinstance(exc, httpx.HTTPStatusError):
        retry_after = exc.response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(int(retry_after), MAX_RETRY_AFTER)
    return RETRY_DELAY


def _folder_info(item, default_drive_id):
    return {
        "id": item["id"],
        "drive_id": item.get("parentReference", {}).get("driveId", default_drive_id),
        "name": item.get("name"),
        "web_url": item.get("webUrl"),
    }


# The library folder name that comes before the folder path in a direct link.
# Same marker as Pipedream's upload_files.py.
DRIVE_PATH_MARKER = "Shared Documents/"


def _is_sharing_link(url):
    """A sharing link looks like https://host/:f:/s/site/..., as in upload_files.py."""
    path = urllib.parse.urlparse(url).path
    return "/:" in path and "/s/" in path


def _drive_path_from_link(url):
    """The folder path inside the library, taken from a direct link.

    Same rules as resolve_sharepoint_url in Pipedream's upload_files.py:
    a view link keeps the path in its id= part, any other link keeps it in the
    address itself. Everything after "Shared Documents/" is the path, each part
    percent-encoded for the Graph request. An empty string means the library root.
    """
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "id" in query:
        decoded_path = urllib.parse.unquote(query["id"][0])
    else:
        decoded_path = urllib.parse.unquote(parsed.path)

    if DRIVE_PATH_MARKER not in decoded_path:
        raise ValueError(f"Could not determine the folder path from the decoded path: '{decoded_path}'")

    path = decoded_path.split(DRIVE_PATH_MARKER, 1)[1].strip("/")
    return "/".join(urllib.parse.quote(part, safe="") for part in path.split("/")) if path else ""


class GraphClient:
    def __init__(
        self,
        tenant_id,
        client_id,
        client_secret,
        drive_id,
        *,
        timeout=30,
        transport=None,  # tests pass httpx.MockTransport here
        sleep=time.sleep,  # tests pass a no-op here
    ):
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._drive_id = drive_id
        self._timeout = timeout
        self._sleep = sleep
        self._http = httpx.Client(timeout=timeout, transport=transport)
        self._token = None
        self._token_expires = 0.0

    @classmethod
    def from_secrets(cls, **kwargs):
        names = ["MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "MS_DRIVE_ID"]
        secrets = get_secrets(names)
        # put names to attributes
        return cls(*(secrets[name] for name in names), **kwargs)

    # ---- low level -------------------------------------------------------

    def _request(self, method, url, **kwargs):
        """Send one request, retrying network errors, 408, 429 and 5xx."""
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(MAX_ATTEMPTS),
                wait=_wait,
                retry=retry_if_exception(_is_retryable),
                sleep=self._sleep,
                reraise=True,
            ):
                with attempt:
                    response = self._http.request(method, url, **kwargs)
                    response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GraphError(exc.response.status_code, exc.response.text, url) from exc
        return response

    def get_token(self):
        """A Graph access token, kept until shortly before it expires."""
        if self._token and time.time() < self._token_expires:
            return self._token
        response = self._request(
            "POST",
            TOKEN_URL.format(tenant=self._tenant_id),
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise GraphError(response.status_code, "no access_token in the token response")
        self._token = token
        self._token_expires = time.time() + max(int(data.get("expires_in", 3600)) - 120, 0)
        return token

    def _graph(self, method, path, json_body=None):
        url = path if path.startswith("http") else GRAPH_URL + path
        response = self._request(
            method,
            url,
            headers={"Authorization": f"Bearer {self.get_token()}"},
            json=json_body,
        )
        return response.json() if response.content else {}

    # ---- folders and links -----------------------------------------------

    def get_item(self, drive_id, item_id):
        return self._graph(
            "GET", f"/drives/{drive_id}/items/{item_id}?$select=id,name,webUrl,folder,parentReference"
        )

    def create_folder(self, parent_id, name, conflict="rename"):
        """Create a folder under parent_id. On a name clash Graph renames it."""
        item = self._graph(
            "POST",
            f"/drives/{self._drive_id}/items/{parent_id}/children",
            {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": conflict},
        )
        return _folder_info(item, self._drive_id)

    def create_view_link(self, drive_id, item_id):
        """A permanent view link that works for anyone signed in to the organization."""
        result = self._graph(
            "POST",
            f"/drives/{drive_id}/items/{item_id}/createLink",
            {"type": "view", "scope": "organization"},
        )
        link = result.get("link", {}).get("webUrl")
        if not link:
            raise GraphError(200, f"createLink returned no webUrl: {result}")
        return link

    def resolve_folder(self, url):
        try:
            return self.resolve_folder_by_share(url)
        except GraphError as exc:
            if _is_sharing_link(url) or exc.status not in (400, 404):
                raise
            return self.resolve_folder_by_path(url)

    def resolve_folder_by_share(self, url):
        """Resolve a link with Graph's shares lookup (works for sharing links)."""
        encoded = "u!" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        item = self._graph(
            "GET", f"/shares/{encoded}/driveItem?$select=id,name,webUrl,folder,parentReference"
        )
        return self._folder_from_item(item, url)

    def resolve_folder_by_path(self, url):
        """Resolve a direct link by its folder path inside the library (MS_DRIVE_ID)."""
        path = _drive_path_from_link(url)
        select = "?$select=id,name,webUrl,folder,parentReference"
        item = self._graph(
            "GET", f"/drives/{self._drive_id}/root:/{path}{select}" if path else f"/drives/{self._drive_id}/root{select}"
        )
        return self._folder_from_item(item, url, default_drive_id=self._drive_id)

    @staticmethod
    def _folder_from_item(item, url, default_drive_id=None):
        parent = item.get("parentReference", {})
        is_folder = "folder" in item
        folder_id = item.get("id") if is_folder else parent.get("id")
        drive_id = parent.get("driveId") or default_drive_id
        if not folder_id or not drive_id:
            raise ValueError(f"Could not resolve the link to a folder: {url}")
        return {
            "id": folder_id,
            "drive_id": drive_id,
            "name": item.get("name") if is_folder else None,
        }

    def get_or_create_folder(self, existing_url, parent_id, name):
        """Reuse the folder behind existing_url, or create name under parent_id.

        Either way the result has a permanent "link". "created" says which one happened.
        """
        if existing_url:
            folder = self.resolve_folder(existing_url)
            created = False
        else:
            folder = self.create_folder(parent_id, name)
            created = True
        link = self.create_view_link(folder["drive_id"], folder["id"])
        return {**folder, "link": link, "created": created}

    def list_children(self, drive_id, item_id):
        path = f"/drives/{drive_id}/items/{item_id}/children?$select=id,name,webUrl,size,folder&$top=200"
        items = []
        while path:
            page = self._graph("GET", path)
            items.extend(page.get("value", []))
            path = page.get("@odata.nextLink")
        return items

    def delete_item(self, drive_id, item_id):
        self._graph("DELETE", f"/drives/{drive_id}/items/{item_id}")

    # ---- files -----------------------------------------------------------

    def upload_file(self, drive_id, folder_id, filename, content, conflict="rename"):
        """Upload bytes as filename into a folder, in one piece (fine up to 10 MB)."""
        if not content:
            raise ValueError("cannot upload an empty file")
        quoted = urllib.parse.quote(filename, safe="")
        session = self._graph(
            "POST",
            f"/drives/{drive_id}/items/{folder_id}:/{quoted}:/createUploadSession",
            {"item": {"@microsoft.graph.conflictBehavior": conflict}},
        )
        upload_url = session.get("uploadUrl")
        if not upload_url:
            raise GraphError(200, "createUploadSession returned no uploadUrl")
        size = len(content)
        # The upload address is already authorized, so no Authorization header here.
        response = self._request(
            "PUT",
            upload_url,
            headers={
                "Content-Range": f"bytes 0-{size - 1}/{size}",
                "Content-Type": "application/octet-stream",
            },
            content=content,
            timeout=self._timeout * 6,
        )
        result = response.json() if response.content else {}
        return {
            "id": result.get("id"),
            "name": result.get("name"),
            "web_url": result.get("webUrl"),
            "size": result.get("size", size),
        }
