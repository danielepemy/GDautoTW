#!/usr/bin/env python3
"""
GD_autoTW_v01

- PyQt UI: select folder, view log, run generator.
- Builds a timestamped gallery HTML using images/, commits & pushes it first.
- Infers GitHub Pages base URL from the repo remote to form Media_url values.
- Regenerates autoTW.csv with one row per image; board ids are cycled if fewer than images.
- Commits & pushes autoTW.csv and this script.
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from itertools import cycle
from pathlib import Path
from typing import Callable, Dict, List, Sequence

from PyQt5 import QtCore, QtWidgets

# CSV order must match existing autoTW.csv
CSV_HEADER = ["Pin_title", "Pin_description", "Website_link", "Media_url", "Board_id", "Alt_text"]
# Only count jpg/jpeg files for row generation
IMAGE_EXT = {".jpg", ".jpeg"}

PIN_PATTERN = re.compile(
    r"Pin\s*\d+\s*:\s*Title:\s*(?P<title>.*?)\s*Description:\s*(?P<description>.*?)\s*"
    r"Alt\s*Text:\s*(?P<alt>.*?)\s*Website\s*URL:\s*(?P<url>https?://\S+)"
    r"(?:\s*Board(?:\s*Name)?\s*:\s*(?P<board>.*?))?(?=\s*Pin\s*\d+\s*:|$)",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class PinDescription:
    title: str
    description: str
    alt_text: str
    website: str
    board_name: str | None = None


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def locate_board_csv(repo_root: Path) -> Path:
    bundle_path = repo_root / "GDautoTW_v04.app" / "Contents" / "Resources" / "board_list.csv"
    root_path = repo_root / "board_list.csv"
    if bundle_path.exists():
        return bundle_path
    if root_path.exists():
        return root_path
    raise FileNotFoundError("board_list.csv not found in repo root or GDautoTW_v04.app bundle")


def load_boards(board_csv: Path) -> List[Dict[str, str]]:
    with board_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        boards: List[Dict[str, str]] = []
        for row in reader:
            board_id = (row.get("board_id") or row.get("BoardId") or "").strip()
            name = (row.get("name") or row.get("Name") or "").strip()
            if board_id:
                boards.append({"board_id": board_id, "name": name})
    if not boards:
        raise ValueError(f"No board ids found in {board_csv}")
    return boards


def parse_pin_descriptions(pin_file: Path) -> List[PinDescription]:
    text = pin_file.read_text(encoding="utf-8", errors="ignore")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    pins: List[PinDescription] = []
    for match in PIN_PATTERN.finditer(text):
        pins.append(
            PinDescription(
                title=match.group("title").strip(),
                description=match.group("description").strip(),
                alt_text=match.group("alt").strip(),
                website=match.group("url").strip(),
                board_name=(match.group("board") or "").strip() or None,
            )
        )
    if not pins:
        raise ValueError(f"No pin blocks detected in {pin_file}")
    return pins


def discover_images(image_dir: Path) -> List[Path]:
    if not image_dir.is_dir():
        raise FileNotFoundError(f"Images folder missing: {image_dir}")
    images = sorted(
        p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT
    )
    if not images:
        raise ValueError(f"No jpg files found in {image_dir}")
    return images


def timestamp_slug() -> str:
    now = datetime.now()
    return f"{now.year}_{now.strftime('%b').lower()}_{now.strftime('%d_%I:%M%p')}"


def create_gallery_html(repo_root: Path, images: Sequence[Path]) -> Path:
    stamp = timestamp_slug()
    html_path = repo_root / f"index_{stamp}.html"
    lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>Images {stamp}</title>",
        "</head>",
        "<body>",
    ]
    for image in images:
        alt = image.stem.replace("-", " ")
        lines.append(f'  <img src="images/{image.name}" alt="{alt}">')
        lines.append("  <br>")
    lines.append("</body>")
    lines.append("</html>")
    html_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return html_path


def run_git(args: Sequence[str], repo_root: Path) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
    )
    return proc


def commit_and_push(files: Sequence[Path], message: str, repo_root: Path, log: Callable[[str], None]) -> None:
    rel_paths: List[str] = []
    for file in files:
        try:
            rel_paths.append(str(file.resolve().relative_to(repo_root)))
        except ValueError:
            log(f"Skipping {file} (outside repo).")
    if not rel_paths:
        raise RuntimeError("No files to commit.")

    add_proc = run_git(["add", *rel_paths], repo_root)
    if add_proc.returncode != 0:
        raise RuntimeError(f"git add failed: {add_proc.stderr.strip()}")

    commit_proc = run_git(["commit", "-m", message], repo_root)
    if commit_proc.returncode != 0:
        stderr = commit_proc.stderr.strip().lower()
        if "nothing to commit" in stderr:
            log("No changes to commit.")
        else:
            raise RuntimeError(f"git commit failed: {commit_proc.stderr.strip()}")
    else:
        log(f"Committed: {message}")

    push_proc = run_git(["push"], repo_root)
    if push_proc.returncode != 0:
        raise RuntimeError(f"git push failed: {push_proc.stderr.strip()}")
    log("Pushed to origin.")


def infer_pages_base(repo_root: Path, log: Callable[[str], None]) -> str:
    proc = run_git(["remote", "get-url", "origin"], repo_root)
    if proc.returncode != 0:
        raise RuntimeError(f"git remote get-url failed: {proc.stderr.strip()}")
    remote = proc.stdout.strip()
    if remote.startswith("git@"):
        _, slug = remote.split(":", 1)
    else:
        slug = remote.split("github.com/", 1)[-1]
    slug = slug.rstrip("/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    if "/" not in slug:
        raise RuntimeError(f"Unexpected remote format: {remote}")
    owner, repo = slug.split("/", 1)
    pages_base = f"https://{owner}.github.io/{repo}"
    log(f"GitHub Pages base resolved to {pages_base}")
    return pages_base


def build_rows(
    pins: Sequence[PinDescription],
    boards: Sequence[Dict[str, str]],
    images: Sequence[Path],
    media_base: str,
    log: Callable[[str], None],
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    board_cycle = cycle(boards)
    board_lookup = {normalize(b["name"]): b for b in boards if b.get("name")}

    for idx, image in enumerate(images):
        pin = pins[idx]
        board_row = None
        if pin.board_name:
            board_row = board_lookup.get(normalize(pin.board_name))
            if board_row is None:
                log(f"Board '{pin.board_name}' not found; cycling board ids.")
        if board_row is None:
            board_row = next(board_cycle)
        media_url = f"{media_base.rstrip('/')}/images/{image.name}"
        rows.append(
            {
                "Pin_title": pin.title,
                "Pin_description": pin.description,
                "Website_link": pin.website,
                "Media_url": media_url,
                "Board_id": board_row["board_id"],
                "Alt_text": pin.alt_text,
            }
        )
        log(
            f"Row {idx + 1}: '{pin.title}' -> board {board_row['board_id']} ({board_row.get('name') or 'Unnamed'})"
        )
    return rows


def write_csv(csv_path: Path, rows: Sequence[Dict[str, str]]) -> None:
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(repo_root: Path, log: Callable[[str], None]) -> None:
    repo_root = repo_root.resolve()
    log(f"Using repository at {repo_root}")

    board_csv = locate_board_csv(repo_root)
    boards = load_boards(board_csv)
    log(f"Loaded {len(boards)} boards from {board_csv.relative_to(repo_root)}")

    pins = parse_pin_descriptions(repo_root / "Pinterest Pin Descriptions.txt")
    log(f"Parsed {len(pins)} pin descriptions.")

    images = discover_images(repo_root / "images")
    log(f"Found {len(images)} jpg images; CSV will have {len(images)} rows.")

    if len(pins) < len(images):
        raise ValueError(f"Need at least {len(images)} pins but only found {len(pins)}.")
    if len(pins) > len(images):
        log(f"More pins than images; using the first {len(images)} pins to match image count.")
    pins = pins[: len(images)]

    gallery_path = create_gallery_html(repo_root, images)
    log(f"Created gallery {gallery_path.name}")
    commit_and_push([gallery_path], f"Add gallery {gallery_path.stem}", repo_root, log)

    media_base = infer_pages_base(repo_root, log)
    rows = build_rows(pins, boards, images, media_base, log)

    csv_path = repo_root / "autoTW.csv"
    write_csv(csv_path, rows)
    log(f"Wrote autoTW.csv with {len(rows)} rows.")

    files_to_commit = [csv_path, gallery_path]
    script_path = Path(__file__).resolve()
    try:
        script_path.relative_to(repo_root)
        files_to_commit.append(script_path)
    except ValueError:
        log("Script is outside repo; not auto-adding.")

    commit_and_push(files_to_commit, f"Update autoTW {datetime.now():%Y-%m-%d %H:%M}", repo_root, log)
    log("autoTW.csv update complete.")


class Worker(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()
    failed = QtCore.pyqtSignal(str)

    def __init__(self, repo_root: Path):
        super().__init__()
        self.repo_root = repo_root

    @QtCore.pyqtSlot()
    def process(self) -> None:
        try:
            run_pipeline(self.repo_root, self.log.emit)
            self.finished.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GD_autoTW_v01")
        self.resize(720, 540)
        self.repo_root: Path | None = None

        self.folder_label = QtWidgets.QLabel("No folder selected")
        self.folder_label.setWordWrap(True)

        choose_btn = QtWidgets.QPushButton("Select Folder")
        choose_btn.clicked.connect(self.choose_folder)

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)

        self.run_btn = QtWidgets.QPushButton("RUN")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.start_run)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.folder_label)
        layout.addWidget(choose_btn)
        layout.addWidget(self.log_view)
        layout.addWidget(self.run_btn)

        self.worker_thread: QtCore.QThread | None = None
        self.worker: Worker | None = None

    def choose_folder(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select GD_autoTW folder")
        if path:
            self.repo_root = Path(path)
            self.folder_label.setText(str(self.repo_root))
            self.run_btn.setEnabled(True)
            self.append_log(f"Selected {self.repo_root}")

    def append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")

    def start_run(self) -> None:
        if not self.repo_root:
            self.append_log("Please select the GD_autoTW folder first.")
            return
        self.run_btn.setEnabled(False)
        self.worker_thread = QtCore.QThread(self)
        self.worker = Worker(self.repo_root)
        self.worker.moveToThread(self.worker_thread)

        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)

        self.worker_thread.started.connect(self.worker.process)
        self.worker_thread.start()
        self.append_log("Started...")

    def on_finished(self) -> None:
        self.append_log("Completed successfully.")
        self.cleanup()

    def on_failed(self, trace: str) -> None:
        self.append_log("ERROR. See console for details.")
        print(trace, file=sys.stderr)
        self.cleanup()

    def cleanup(self) -> None:
        self.run_btn.setEnabled(True)
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
        self.worker_thread = None
        self.worker = None


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
