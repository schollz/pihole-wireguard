#!/usr/bin/env -S uv --quiet run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "python-dateutil",
#     "rich",
# ]
# ///

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from dateutil import tz
from rich.console import Console
from rich.traceback import install as install_rich_traceback


install_rich_traceback(show_locals=False)
console = Console()
LOCAL_TZ = tz.tzlocal()


class CommandError(RuntimeError):
    def __init__(self, command: Sequence[str], returncode: int, output: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.output = output
        super().__init__(f"command failed with exit code {returncode}: {shlex.join(command)}")


@dataclass
class Runner:
    console: Console

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> str:
        self._print_command(command, cwd=cwd)
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        output_lines: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(line)
            self._print_output(line.rstrip("\n"))

        returncode = process.wait()
        output = "".join(output_lines)
        if check and returncode != 0:
            raise CommandError(command, returncode, output)
        return output

    def _print_command(self, command: Sequence[str], *, cwd: Path | None) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        location = f" ({cwd})" if cwd else ""
        self.console.print(f"[bold cyan]{ts} $[/] {shlex.join(command)}[dim]{location}[/]")

    def _print_output(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S", time.localtime())
        if line:
            self.console.print(f"[dim]{ts}[/] {line}", soft_wrap=True)


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_name = time.strftime(
        "pihole-wireguard-%Y%m%d-%H%M%S",
        time.localtime(),
    )

    parser = argparse.ArgumentParser(
        description="Create a DigitalOcean droplet, upload this repo, and run setup.sh.",
    )
    parser.add_argument("name", nargs="?", default=default_name, help="Droplet name.")
    parser.add_argument("--region", default="sfo3", help="DigitalOcean region slug.")
    parser.add_argument("--size", default="s-1vcpu-1gb", help="DigitalOcean size slug.")
    parser.add_argument("--image", default="ubuntu-24-04-x64", help="Droplet image slug.")
    parser.add_argument(
        "--tag",
        action="append",
        default=["pihole-wireguard"],
        help="Droplet tag. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=script_dir,
        help="Project directory to upload.",
    )
    parser.add_argument(
        "--remote-dir",
        default="/root/pihole-wireguard",
        help="Remote directory where the project will be unpacked.",
    )
    parser.add_argument(
        "--ssh-key-path",
        type=Path,
        help="Local SSH public key to use. Defaults to the first common key found.",
    )
    parser.add_argument(
        "--ssh-wait-timeout",
        type=int,
        default=600,
        help="Seconds to wait for SSH to become available.",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep the temporary tarball after upload.",
    )
    return parser.parse_args()


def ensure_commands_exist(commands: Iterable[str]) -> None:
    missing = [command for command in commands if not shutil_which(command)]
    if missing:
        raise SystemExit(f"missing required command(s): {', '.join(missing)}")


def shutil_which(command: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def detect_ssh_key(pubkey_path: Path | None) -> tuple[Path, Path]:
    if pubkey_path:
        pubkey = pubkey_path.expanduser().resolve()
        if pubkey.suffix != ".pub":
            raise SystemExit("--ssh-key-path must point to a .pub file")
        private = pubkey.with_suffix("")
        if not pubkey.exists():
            raise SystemExit(f"SSH public key not found: {pubkey}")
        if not private.exists():
            raise SystemExit(f"SSH private key not found for public key: {private}")
        return pubkey, private

    candidates = [
        Path("~/.ssh/id_ed25519.pub").expanduser(),
        Path("~/.ssh/id_ecdsa.pub").expanduser(),
        Path("~/.ssh/id_rsa.pub").expanduser(),
    ]
    for candidate in candidates:
        if candidate.exists():
            private = candidate.with_suffix("")
            if private.exists():
                return candidate.resolve(), private.resolve()

    raise SystemExit("no default SSH public key found under ~/.ssh")


def ssh_fingerprint(pubkey: Path, runner: Runner) -> str:
    output = runner.run(["ssh-keygen", "-E", "md5", "-lf", str(pubkey)])
    parts = output.strip().split()
    if len(parts) < 2:
        raise SystemExit(f"unable to parse fingerprint for {pubkey}")
    fingerprint = parts[1]
    return fingerprint.removeprefix("MD5:")


def doctl_json(runner: Runner, command: Sequence[str]) -> object:
    output = runner.run(command)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"failed to parse JSON from {shlex.join(command)}: {exc}") from exc


def delete_existing_pihole_droplets(runner: Runner) -> None:
    droplets = doctl_json(runner, ["doctl", "compute", "droplet", "list", "-o", "json"])
    assert isinstance(droplets, list)

    matched: list[dict[str, object]] = []
    for droplet in droplets:
        if not isinstance(droplet, dict):
            continue
        name = str(droplet.get("name", "")).strip()
        if re.match(r"^pihole", name, re.IGNORECASE):
            matched.append(droplet)

    if not matched:
        console.print("[dim]No existing pihole* droplets found.[/]")
        return

    names = ", ".join(str(droplet.get("name", "<unknown>")) for droplet in matched)
    console.print(f"[yellow]Deleting existing pihole* droplets:[/] {names}")
    runner.run(
        [
            "doctl",
            "compute",
            "droplet",
            "delete",
            "--force",
            *(str(droplet["id"]) for droplet in matched if "id" in droplet),
        ]
    )


def ensure_do_ssh_key(pubkey: Path, runner: Runner) -> list[str]:
    local_fingerprint = ssh_fingerprint(pubkey, runner)
    keys = doctl_json(runner, ["doctl", "compute", "ssh-key", "list", "-o", "json"])
    assert isinstance(keys, list)

    key_ids = [str(item["id"]) for item in keys if "id" in item]
    for item in keys:
        if str(item.get("fingerprint", "")).lower() == local_fingerprint.lower():
            console.print(
                f"[green]Using existing DigitalOcean SSH key[/] "
                f"[bold]{item.get('name', item.get('id', 'unknown'))}[/]"
            )
            return key_ids

    import_name = f"{socket.gethostname()}-{pubkey.stem}-{int(time.time())}"
    imported = doctl_json(
        runner,
        [
            "doctl",
            "compute",
            "ssh-key",
            "import",
            import_name,
            "--public-key-file",
            str(pubkey),
            "-o",
            "json",
        ],
    )
    assert isinstance(imported, list) and imported
    imported_id = str(imported[0]["id"])
    console.print(f"[yellow]Imported local SSH key into DigitalOcean as[/] [bold]{import_name}[/]")
    key_ids.append(imported_id)
    return key_ids


def create_droplet(args: argparse.Namespace, key_ids: list[str], runner: Runner) -> tuple[str, str]:
    command = [
        "doctl",
        "compute",
        "droplet",
        "create",
        args.name,
        "--region",
        args.region,
        "--size",
        args.size,
        "--image",
        args.image,
        "--ssh-keys",
        ",".join(key_ids),
        "--wait",
        "-o",
        "json",
    ]
    for tag in dict.fromkeys(args.tag):
        command.extend(["--tag-name", tag])

    runner.run(command)
    droplet = doctl_json(
        runner,
        ["doctl", "compute", "droplet", "get", args.name, "-o", "json"],
    )
    assert isinstance(droplet, list) and droplet
    item = droplet[0]
    droplet_id = str(item["id"])
    public_ip = extract_public_ipv4(item)
    if not public_ip:
        raise SystemExit("droplet created but no public IPv4 address was returned")
    return droplet_id, public_ip


def extract_public_ipv4(droplet: dict[str, object]) -> str:
    public_ip = str(droplet.get("public_ipv4", "")).strip()
    if public_ip:
        return public_ip

    networks = droplet.get("networks")
    if isinstance(networks, dict):
        ipv4_networks = networks.get("v4")
        if isinstance(ipv4_networks, list):
            for network in ipv4_networks:
                if not isinstance(network, dict):
                    continue
                if str(network.get("type", "")).strip().lower() != "public":
                    continue
                ip_address = str(network.get("ip_address", "")).strip()
                if ip_address:
                    return ip_address

    return ""


def wait_for_ssh(ip: str, private_key: Path, timeout_seconds: int, runner: Runner) -> None:
    deadline = time.monotonic() + timeout_seconds
    ssh_base = ssh_options(private_key)
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        console.print(f"[blue]Waiting for SSH[/] on [bold]{ip}[/] (attempt {attempt})")
        try:
            runner.run(
                [*ssh_base, f"root@{ip}", "true"],
                check=True,
            )
            console.print(f"[green]SSH is ready on[/] [bold]{ip}[/]")
            return
        except CommandError:
            time.sleep(5)

    raise SystemExit(f"timed out waiting for SSH on {ip}")


def ssh_options(private_key: Path) -> list[str]:
    return [
        "ssh",
        "-i",
        str(private_key),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]


def scp_options(private_key: Path) -> list[str]:
    return [
        "scp",
        "-i",
        str(private_key),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]


def create_archive(project_dir: Path) -> Path:
    temp_file = tempfile.NamedTemporaryFile(prefix="pihole-wireguard-", suffix=".tar.gz", delete=False)
    temp_file.close()
    archive_path = Path(temp_file.name)

    excluded_names = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}

    with tarfile.open(archive_path, "w:gz") as tar:
        for path in sorted(project_dir.rglob("*")):
            relative = path.relative_to(project_dir)
            if any(part in excluded_names for part in relative.parts):
                continue
            tar.add(path, arcname=str(relative))

    return archive_path


def upload_and_run(
    project_dir: Path,
    remote_dir: str,
    ip: str,
    private_key: Path,
    archive_path: Path,
    runner: Runner,
) -> None:
    remote_archive = f"/root/{archive_path.name}"
    runner.run([*scp_options(private_key), str(archive_path), f"root@{ip}:{remote_archive}"])
    remote_script = (
        f"set -euo pipefail; "
        f"mkdir -p {shlex.quote(remote_dir)}; "
        f"tar xzf {shlex.quote(remote_archive)} -C {shlex.quote(remote_dir)}; "
        f"rm -f {shlex.quote(remote_archive)}; "
        f"cd {shlex.quote(remote_dir)}; "
        f"bash setup.sh"
    )
    runner.run([*ssh_options(private_key), f"root@{ip}", remote_script], cwd=project_dir)


def main() -> int:
    args = parse_args()
    args.project_dir = args.project_dir.expanduser().resolve()
    if not args.project_dir.exists():
        raise SystemExit(f"project directory not found: {args.project_dir}")

    ensure_commands_exist(["doctl", "ssh-keygen", "ssh", "scp"])

    runner = Runner(console=console)
    pubkey, private_key = detect_ssh_key(args.ssh_key_path)

    console.print(f"[bold]Project directory:[/] {args.project_dir}")
    console.print(f"[bold]Droplet name:[/] {args.name}")
    console.print(f"[bold]Region:[/] {args.region}")
    console.print(f"[bold]Size:[/] {args.size}")
    console.print(f"[bold]Image:[/] {args.image}")
    console.print(f"[bold]SSH public key:[/] {pubkey}")

    delete_existing_pihole_droplets(runner)

    key_ids = ensure_do_ssh_key(pubkey, runner)
    if not key_ids:
        raise SystemExit("no DigitalOcean SSH keys available to attach to the droplet")

    droplet_id, public_ip = create_droplet(args, key_ids, runner)
    console.print(f"[green]Droplet created:[/] id={droplet_id} ip={public_ip}")

    wait_for_ssh(public_ip, private_key, args.ssh_wait_timeout, runner)

    archive_path = create_archive(args.project_dir)
    console.print(f"[bold]Archive:[/] {archive_path}")
    try:
        upload_and_run(args.project_dir, args.remote_dir, public_ip, private_key, archive_path, runner)
    finally:
        if args.keep_archive:
            console.print(f"[yellow]Keeping local archive:[/] {archive_path}")
        else:
            archive_path.unlink(missing_ok=True)

    console.print(f"[bold green]Finished.[/] Droplet [bold]{args.name}[/] is at [bold]{public_ip}[/].")
    return 0


if __name__ == "__main__":
    sys.exit(main())
