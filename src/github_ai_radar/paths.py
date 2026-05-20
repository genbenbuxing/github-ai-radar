from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RadarPaths:
    root: Path
    data_dir: Path
    reports_dir: Path
    state_dir: Path
    partials_dir: Path
    logs_dir: Path
    raw_dir: Path
    database: Path

    @classmethod
    def from_root(cls, root: Path) -> "RadarPaths":
        reports_dir = root / "reports" / "github-radar"
        return cls(
            root=root,
            data_dir=root / "data",
            reports_dir=reports_dir,
            state_dir=reports_dir / "state",
            partials_dir=reports_dir / "partials",
            logs_dir=reports_dir / "logs",
            raw_dir=reports_dir / "raw",
            database=root / "data" / "radar.sqlite",
        )

    def ensure(self) -> None:
        for path in [
            self.data_dir,
            self.reports_dir,
            self.state_dir,
            self.partials_dir,
            self.logs_dir,
            self.raw_dir / "github",
            self.raw_dir / "sources",
        ]:
            path.mkdir(parents=True, exist_ok=True)
