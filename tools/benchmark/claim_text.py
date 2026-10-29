"""Recover a reply-text download that the app left as a pending temp file in ~/Downloads.

usage: python3 -I claim_text.py <response_id> <sha256>
The sha256 is computed in the ChatGPT page from the exact text that was downloaded, so the file
claimed here is byte-for-byte what was on the page. Copies it to ~/Downloads/bench-<response_id>.txt.
"""
import hashlib, shutil, sys
from pathlib import Path

rid, sha = sys.argv[1], sys.argv[2].lower()
dl = Path.home() / "Downloads"
dest = dl / f"bench-{rid}.txt"
for p in [dest, *dl.glob(".*claudefordesktop*")]:
    if p.is_file() and p.stat().st_size < 200_000 and hashlib.sha256(p.read_bytes()).hexdigest() == sha:
        if p != dest:
            shutil.copyfile(p, dest)
        print(f"{dest.name} <- {p.name} ({p.stat().st_size} bytes, sha matches)")
        break
else:
    sys.exit("no file in ~/Downloads matches that sha256")
