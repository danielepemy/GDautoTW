GD_autoTW_v01 – Detailed Overview
=================================

Purpose
-------
GD_autoTW_v01 automates the full workflow for updating social-media-ready assets in the GDautoTW repository. It combines a minimal PyQt interface with scripted Git operations to ensure the local data (images, pin descriptions, and board IDs) stay in sync with the GitHub repository and its GitHub Pages site.

High-Level Flow
---------------
1. User launches the PyQt app, selects the local GDautoTW folder, and clicks RUN.
2. The script validates inputs and gathers data (boards, pin descriptions, images).
3. It generates a timestamped gallery HTML file referencing each image.
4. It commits/pushes this HTML immediately so GitHub Pages can host the images.
5. It infers the GitHub Pages base URL to build final `Media_url` links.
6. It regenerates autoTW.csv with one row per image, cycling board IDs if necessary.
7. It commits/pushes the CSV, the new HTML file, and (if inside the repo) the script itself.
8. Logs of every step appear in the UI.

Detailed Behavior
-----------------
Input files:
- `board_list.csv` (preferentially pulled from `GDautoTW_v04.app/Contents/Resources` if present, otherwise from the repo root).
- `Pinterest Pin Descriptions.txt` containing blocks like “Pin 1: Title: … Description: … Alt Text: … Website URL: …”.
- `images/` folder containing the JPG/JPEG assets. The number of `.jpg`/`.jpeg` files determines the number of rows in autoTW.csv.

Pin data handling:
- The parser normalizes CR/LF combinations to handle Windows-style line endings.
- Regex extracts Title, Description, Alt Text, Website URL, and an optional board name.
- If extra pins exist beyond the image count, the script silently trims to match the number of images.
- If there are fewer pins than images, execution stops with a clear error message.

Board assignment:
- Board IDs are loaded into memory, with a dictionary keyed on normalized board names for quick lookup.
- When a pin specifies a board name, the script attempts an exact case-insensitive match.
- If the board name is missing or not found, the script cycles through every available board ID in order (restarting from the top when it reaches the end) so no autoTW row is left without a board.

Gallery generation:
- A timestamped file name like `index_2025_dec_15_07:47PM.html` is created.
- The HTML is intentionally minimal: a `<body>` with `<img>` tags referencing `images/<filename>`.
- After writing the file, the script stages, commits, and pushes it immediately. This ensures GitHub Pages publishes the page (and the images folder) before the CSV references the URLs.

GitHub Pages URL:
- The script runs `git remote get-url origin`, strips `.git`, and converts `owner/repo` into `https://owner.github.io/repo`.
- Media URLs in autoTW.csv are built as `<pages_base>/images/<image_name>`.

autoTW.csv generation:
- Output columns strictly follow `Pin_title, Pin_description, Website_link, Media_url, Board_id, Alt_text`.
- Each row corresponds to one image and the matching pin.
- The CSV is written with UTF-8 encoding and Unix line endings.

Git steps and safety:
- All Git commands run inside the selected repo folder.
- Files staged/committed: the new gallery HTML, `autoTW.csv`, and (if located inside the repo) `GD_autoTW_v01.py`.
- The script reports “No changes to commit” if a commit is unnecessary, but it still attempts to push in case the remote has diverged.
- Any Git failure (e.g., rejected push) raises an exception and surfaces in the log widget.

PyQt interface:
- Simple layout with three primary elements: folder selector, log display, RUN button.
- The log shows a timestamped stream of activity (data loading, Git commands, errors).
- Work runs in a background thread to keep the UI responsive, with signals for success/failure.

Dependencies
------------
- Python 3.9+ (tested with 3.11) and PyQt5.
- Git must be installed and authenticated with write access to the repository.
- Local environment must have network access to push to GitHub.

Usage Recap
-----------
1. Activate the virtual environment (e.g., `source GD_autoTW_env/bin/activate`).
2. `python GD_autoTW_v01.py`.
3. Select the GDautoTW repo folder when prompted.
4. Click RUN and monitor the log.
5. On success, verify the remote repo (and GitHub Pages) reflect the new gallery and autoTW.csv.
