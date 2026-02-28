"""Local Gemini Account Manager — manages GEMINI_ACCOUNTS_CONFIG JSON file on disk.

Accounts are stored as a JSON array in a file so they persist across restarts
(when backed by a Docker volume).
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class LocalGeminiManager:
    """Manages Gemini Business accounts stored in a JSON file."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

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

        return {
            "status": "ok",
            "message": "Gemini account ditambahkan",
            "before_count": before_count,
            "after_count": before_count + 1,
        }

    def remove_last_account(self) -> Dict[str, str]:
        accounts = self.list_accounts()
        if not accounts:
            return {"status": "error", "message": "Tidak ada account untuk dihapus"}

        removed = accounts.pop()
        self.file_path.write_text(json.dumps(accounts), encoding="utf-8")

        preview = removed.get("secure_c_ses", "")
        if len(preview) > 12:
            preview = preview[:6] + "..." + preview[-4:]
        else:
            preview = preview[:3] + "***"

        return {"status": "ok", "message": f"Account terakhir dihapus ({preview})"}

    def get_masked_summary(self) -> List[str]:
        accounts = self.list_accounts()
        result = []
        for idx, acc in enumerate(accounts, start=1):
            ses = acc.get("secure_c_ses", "???")
            if len(ses) > 12:
                masked = ses[:6] + "..." + ses[-4:]
            else:
                masked = ses[:3] + "***"
            csesidx = acc.get("csesidx", "?")
            cfg = acc.get("config_id", "?")
            cfg_short = cfg[:8] + "…" if len(cfg) > 8 else cfg
            result.append(f"{idx}. {masked} (idx: {csesidx}, cfg: {cfg_short})")
        return result

    def get_config_json(self) -> str:
        """Return the JSON string for GEMINI_ACCOUNTS_CONFIG."""
        return self.file_path.read_text(encoding="utf-8") if self.file_path.exists() else "[]"
