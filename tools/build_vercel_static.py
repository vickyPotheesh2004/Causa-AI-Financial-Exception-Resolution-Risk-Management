"""Copy the static synthetic-demo user interface into Vercel's public directory."""

from pathlib import Path
from shutil import copytree, rmtree

root = Path(__file__).resolve().parents[1]
target = root / "public"
if target.exists():
    rmtree(target)
copytree(root / "src" / "cause_ai" / "static", target)
