"""Local Gemini Account Manager — manages GEMINI_ACCOUNTS_CONFIG JSON file on disk.

Accounts are stored as a JSON array in a file so they persist across restarts
(when backed by a Docker volume). Each account also tracks an `_status` field
for the bot UI (active / dead / unknown).
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


# Status constants
STATUS_ACTIVE = "active"
STATUS_DEAD = "dead"
STATUS_UNKNOWN = "unknown"
STATUS_DISABLED = "disabled"
STATUS_EXPIRED = "expired"

STATUS_ICONS = {
    STATUS_ACTIVE: "🟢",
    STATUS_DEAD: "🔴",
    STATUS_UNKNOWN: "⚪",
    STATUS_DISABLED: "⏸",
    STATUS_EXPIRED: "⏰",
}


class LocalGeminiManager:
    """Manages Gemini Business accounts stored in a JSON file."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        # In-memory status cache (not persisted to disk — refreshed via health check)
        self._status: Dict[int, str] = {}  # index -> status

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text("[]", encoding="utf-8")

    def list_accounts(self) -> List[dict]:
        self._ensure_file()
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, Exception):
            return []

    def add_account(
        self,
        secure_c_ses: str,
        host_c_oses: str = "",
        csesidx: str = "",
        config_id: str = "",
    ) -> Dict[str, Any]:
        """Add a new Gemini account. Returns status dict."""
        if not secure_c_ses:
            return {"status": "error", "message": "secure_c_ses kosong"}

        accounts = self.list_accounts()
        before_count = len(accounts)

        # Check duplicate by secure_c_ses prefix (first 30 chars)
        for acc in accounts:
            if acc.get("secure_c_ses", "")[:30] == secure_c_ses[:30]:
                return {
                    "status": "exists",
                    "message": "Account dengan secure_c_ses yang sama sudah ada",
                    "before_count": before_count,
                    "after_count": before_count,
                }

        new_account = {
            "secure_c_ses": secure_c_ses,
            "host_c_oses": host_c_oses,
            "csesidx": csesidx,
            "config_id": config_id or str(uuid.uuid4()),
        }
        accounts.append(new_account)
        self.file_path.write_text(json.dumps(accounts), encoding="utf-8")

        # Default new account status
        self._status[before_count] = STATUS_UNKNOWN

        return {
            "status": "ok",
            "message": "Gemini account ditambahkan",
            "before_count": before_count,
            "after_count": before_count + 1,
        }

    def remove_account(self, index: int) -> Dict[str, str]:
        """Remove account by index (0-based). Returns status dict."""
        accounts = self.list_accounts()
        if not accounts:
            return {"status": "error", "message": "Tidak ada account untuk dihapus"}
        if index < 0 or index >= len(accounts):
            return {"status": "error", "message": f"Index {index + 1} tidak valid (total: {len(accounts)})"}

        removed = accounts.pop(index)
        self.file_path.write_text(json.dumps(accounts), encoding="utf-8")

        # Re-index status cache
        new_status = {}
        for i in range(len(accounts)):
            old_i = i if i < index else i + 1
            new_status[i] = self._status.get(old_i, STATUS_UNKNOWN)
        self._status = new_status

        preview = removed.get("secure_c_ses", "")
        if len(preview) > 12:
            preview = preview[:6] + "..." + preview[-4:]
        else:
            preview = preview[:3] + "***"

        return {"status": "ok", "message": f"Server {index + 1} dihapus ({preview})"}

    def remove_last_account(self) -> Dict[str, str]:
        accounts = self.list_accounts()
        if not accounts:
            return {"status": "error", "message": "Tidak ada account untuk dihapus"}
        return self.remove_account(len(accounts) - 1)

    def update_status(self, health_results: List[dict]) -> None:
        """Update status cache from gateway health check results."""
        self._status.clear()
        for i, result in enumerate(health_results):
            self._status[i] = result.get("status", STATUS_UNKNOWN)

    def get_status(self, index: int) -> str:
        return self._status.get(index, STATUS_UNKNOWN)

    def get_masked_summary(self) -> List[str]:
        accounts = self.list_accounts()
        result = []
        for idx, acc in enumerate(accounts):
            ses = acc.get("secure_c_ses", "???")
            if len(ses) > 12:
                masked = ses[:6] + "..." + ses[-4:]
            else:
                masked = ses[:3] + "***"
            csesidx = acc.get("csesidx", "?")
            cfg = acc.get("config_id", "?")
            cfg_short = cfg[:8] + "…" if len(cfg) > 8 else cfg
            status = self._status.get(idx, STATUS_UNKNOWN)
            icon = STATUS_ICONS.get(status, "❓")
            result.append(f"{icon} Server {idx + 1}: {masked} (idx: {csesidx}, cfg: {cfg_short})")
        return result

    def get_server_keyboard_data(self) -> List[Dict[str, Any]]:
        """Return data for building server keyboard buttons."""
        accounts = self.list_accounts()
        data = []
        for idx, acc in enumerate(accounts):
            status = self._status.get(idx, STATUS_UNKNOWN)
            icon = STATUS_ICONS.get(status, "❓")
            if status == STATUS_DEAD:
                label = f"{icon} Server {idx + 1} (MT)"
            elif status == STATUS_ACTIVE:
                label = f"{icon} Server {idx + 1}"
            else:
                label = f"{icon} Server {idx + 1}"
            data.append({"index": idx, "label": label, "status": status})
        return data

    def get_config_json(self) -> str:
        """Return the JSON string for GEMINI_ACCOUNTS_CONFIG."""
        return self.file_path.read_text(encoding="utf-8") if self.file_path.exists() else "[]"
