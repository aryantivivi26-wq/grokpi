from pathlib import Path
from typing import Dict, List


class LocalSSOManager:
    def __init__(self, file_path: Path):
        self.file_path = file_path

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text("", encoding="utf-8")

    def list_keys(self) -> List[str]:
        self._ensure_file()
        lines = self.file_path.read_text(encoding="utf-8").splitlines()
        keys = [line.strip() for line in lines if line.strip()]
        return keys

    def add_key(self, key: str) -> Dict[str, str]:
        key = key.strip()
        if not key:
            return {"status": "error", "message": "Key kosong"}

        keys = self.list_keys()
        if key in keys:
            return {"status": "ok", "message": "Key sudah ada"}

        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(key + "\n")

        return {"status": "ok", "message": "Key ditambahkan"}

    def remove_last_key(self) -> Dict[str, str]:
        keys = self.list_keys()
        if not keys:
            return {"status": "error", "message": "Tidak ada key untuk dihapus"}

        removed = keys.pop()
        content = "\n".join(keys)
        if content:
            content += "\n"
        self.file_path.write_text(content, encoding="utf-8")

        preview = removed[:6] + "..." + removed[-4:] if len(removed) > 12 else removed[:3] + "***"
        return {"status": "ok", "message": f"Key terakhir dihapus ({preview})"}

    def get_masked_summary(self) -> List[str]:
        keys = self.list_keys()
        result = []
        for idx, value in enumerate(keys, start=1):
            if len(value) <= 12:
                masked = value[:3] + "***"
            else:
                masked = value[:6] + "..." + value[-4:]
            result.append(f"{idx}. {masked}")
        return result
