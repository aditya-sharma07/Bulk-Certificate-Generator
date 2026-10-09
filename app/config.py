from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    storage_dir: Path
    max_recipients_per_job: int = 1000

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_path=Path(
                os.getenv("DATABASE_PATH", "data/certificates.db")
            ),
            storage_dir=Path(os.getenv("STORAGE_DIR", "data/generated")),
            max_recipients_per_job=int(
                os.getenv("MAX_RECIPIENTS_PER_JOB", "1000")
            ),
        )

