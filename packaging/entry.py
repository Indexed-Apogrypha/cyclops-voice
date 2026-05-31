"""PyInstaller entry script. Delegates to the package frozen-entry point."""
from cyclops_voice.__main__ import entry

if __name__ == "__main__":
    raise SystemExit(entry())
