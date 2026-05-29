from __future__ import annotations
import argparse
import sys
from .client import CyclopsClient
from .config import load_config


def _client(args) -> CyclopsClient:
    cfg = load_config(args.config)
    base = f"http://{cfg.service.host}:{cfg.service.port}"
    return CyclopsClient(base_url=base, token=cfg.service.auth_token)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cyclops", description="Cyclops voice TTS")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("say", help="speak text (use - to read stdin)")
    s.add_argument("text")
    s.add_argument("--preset", default=None)
    s.add_argument("--enqueue", action="store_true")

    for name in ("stop", "pause", "resume", "skip", "status"):
        sub.add_parser(name)

    r = sub.add_parser("render", help="render text to a .wav file")
    r.add_argument("text"); r.add_argument("-o", "--out", default=None)
    r.add_argument("--preset", default=None)

    d = sub.add_parser("daemon", help="run the background service")
    d.add_argument("--no-hotkey", action="store_true")
    d.add_argument("--no-tray", action="store_true")

    sub.add_parser("install-model", help="download the en_US-ryan voice model")
    sub.add_parser("install-autostart", help="add a Startup-folder shortcut")

    args = p.parse_args(argv)

    if args.cmd == "daemon":
        from .daemon import run_daemon
        run_daemon(args.config, enable_hotkey=not args.no_hotkey,
                   enable_tray=not args.no_tray)
        return 0
    if args.cmd == "install-model":
        from .model_download import main as m; return m()
    if args.cmd == "install-autostart":
        from scripts.install_autostart import main as m; return m()

    c = _client(args)
    if args.cmd != "status" and not c.is_up():
        print("Cyclops daemon not running. Start it with: cyclops daemon", file=sys.stderr)
        return 1

    if args.cmd == "say":
        text = sys.stdin.read() if args.text == "-" else args.text
        out = c.speak(text, preset=args.preset,
                      mode="enqueue" if args.enqueue else "interrupt")
        print(out["job_id"]); return 0
    if args.cmd == "render":
        out = c.render(args.text, preset=args.preset, path=args.out)
        print(out["path"]); return 0
    if args.cmd in ("stop", "pause", "resume", "skip"):
        print(getattr(c, args.cmd)()["state"]); return 0
    if args.cmd == "status":
        import json; print(json.dumps(c.status(), indent=2)); return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
