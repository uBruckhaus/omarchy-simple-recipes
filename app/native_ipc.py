"""Private Unix socket for the bar; no HTTP listener or browser."""
import argparse
import json
import os
from pathlib import Path
import socket
import time


def socket_path():
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    directory = runtime / "simple-recipes"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    return directory / "control.sock"


def send(command, argument=None, timeout=2):
    payload = {"command": command}
    if argument is not None:
        payload["argument"] = argument
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path()))
        client.sendall(json.dumps(payload).encode() + b"\n")
        response = b""
        while b"\n" not in response and len(response) < 4096:
            chunk = client.recv(4096)
            if not chunk:
                break
            response += chunk
    return json.loads(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["ping", "show", "hide", "toggle", "settings", "recipe", "tab", "quit"])
    parser.add_argument("argument", nargs="?", type=int)
    parser.add_argument("--wait", type=float, default=0)
    args = parser.parse_args()
    deadline = time.monotonic() + args.wait
    while True:
        try:
            print(json.dumps(send(args.command, args.argument)))
            return
        except (OSError, ValueError):
            if time.monotonic() >= deadline:
                raise SystemExit("Simple Recipes is not ready. Run its setup or check the user service journal.")
            time.sleep(0.1)


if __name__ == "__main__":
    main()
