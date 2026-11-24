"""Seal and publish immutable Worktrees artifacts from an exact merged root.

Draft/asset reconciliation is adapted from the Operations producer at
62e4a1b62e3923e7013f7bac3d84b77b36204229. This repository owns subsequent
Worktrees publication. The readback helper is pinned to Scheduling.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tomllib
import zipfile

from github_release_readback import find_release, read_release, remote_assets

REPOSITORY = "bkrabach/amplifier-platform-worktrees"
RECEIPT = "worktrees-source.json"
# Package inputs are shipped in the sdist. Repository automation is instead bound
# by the full revision/root tree; it is not another installed library or test suite.
PACKAGE_ROOTS = ("pyproject.toml", "README.md", "LICENSE", "MANIFEST.in",
                 "PROVENANCE.json", "CODE_OF_CONDUCT.md", "SECURITY.md", "SUPPORT.md",
                 "amplifier_worktrees", "tests")


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def selection(root, revision, *, qualification=False):
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Select a full merged commit SHA.")
    if not qualification:
        run("git", "merge-base", "--is-ancestor", revision, "origin/main", cwd=root)
    project = tomllib.loads(run("git", "show", f"{revision}:pyproject.toml", cwd=root).decode())
    version = project["project"]["version"]
    if project["project"]["name"] != "amplifier-worktrees" or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected the stable standalone Worktrees project.")
    entries = run("git", "ls-tree", "-r", revision, "--", *PACKAGE_ROOTS, cwd=root).decode().splitlines()
    files = {}
    for entry in entries:
        identity, name = entry.split("\t", 1)
        if identity.split()[:2] not in (["100644", "blob"], ["100755", "blob"]):
            raise ValueError("Package inputs must be regular Git files.")
        safe(name)
        files[name] = sha(run("git", "show", f"{revision}:{name}", cwd=root))
    required = {*PACKAGE_ROOTS[:-2], "amplifier_worktrees/__init__.py"}
    if not required <= files.keys() or not any(name.startswith("tests/") for name in files):
        raise ValueError("Selected Worktrees package inputs are incomplete.")
    return {"schema": 1, "component": "worktrees", "repository": REPOSITORY,
            "revision": revision, "subdirectory": ".",
            "tree": run("git", "rev-parse", f"{revision}^{{tree}}", cwd=root).decode().strip(),
            "version": version, "tag": "worktrees-v" + version, "sourceFiles": files}


def artifact_names(selected):
    stem = "amplifier_worktrees-" + selected["version"]
    return stem + "-py3-none-any.whl", stem + ".tar.gz"


def safe(name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith("/") or "\\" in name or any(p in {".", ".."} for p in parts):
        raise ValueError("Unsafe package member.")


def requirement_key(value):
    # Same metadata formatting normalization as Unified's artifact selector.
    value = re.sub(r"\s+", "", value).replace('"', "'")
    requirement, separator, marker = value.partition(";")
    name, constraints = re.fullmatch(r"([A-Za-z0-9_.-]+)(.*)", requirement).groups()
    return name.lower().replace("_", "-") + ",".join(sorted(constraints.split(","))) + separator + marker


def package_identity(dist, selected):
    """Verify installed payload and every sdist package input against Git."""
    wheel, source = artifact_names(selected)
    expected = selected["sourceFiles"]
    runtime = {name: digest for name, digest in expected.items()
               if name.startswith("amplifier_worktrees/")}
    prefix = "amplifier_worktrees-" + selected["version"] + "/"
    with tarfile.open(dist / source) as archive:
        members = archive.getmembers()
        if len(members) != len({member.name for member in members}):
            raise ValueError("Duplicate source archive member.")
        observed = {}
        for member in members:
            safe(member.name)
            if (member.name != prefix.rstrip("/") and not member.name.startswith(prefix)) or not (member.isfile() or member.isdir()):
                raise ValueError("Unexpected source archive entry.")
            if member.isfile():
                name = member.name.removeprefix(prefix)
                if name in expected:
                    observed[name] = sha(archive.extractfile(member).read())
                elif name.endswith(".py"):
                    raise ValueError("Source archive contains unselected runtime code.")
        if observed != expected:
            raise ValueError("Source archive differs from selected package/tests.")
        project = tomllib.loads(archive.extractfile(prefix + "pyproject.toml").read().decode())["project"]
    info = f"amplifier_worktrees-{selected['version']}.dist-info/"
    with zipfile.ZipFile(dist / wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate wheel member.")
        for name in names:
            safe(name)
            if name not in runtime and not name.startswith(info):
                raise ValueError("Wheel includes a second package or non-runtime source.")
        if {name: sha(archive.read(name)) for name in names if name in runtime} != runtime:
            raise ValueError("Wheel runtime differs from selected source.")
        metadata = BytesParser().parsebytes(archive.read(info + "METADATA"))
        requirements = list(project.get("dependencies", []))
        extras = project.get("optional-dependencies", {})
        requirements.extend(value + '; extra == "' + extra + '"' for extra, values in extras.items() for value in values)
        if (metadata["Name"] != project["name"] or metadata["Version"] != selected["version"]
                or metadata["Requires-Python"] != project["requires-python"]
                or metadata["License-Expression"] != project["license"]
                or set(metadata.get_all("Provides-Extra", [])) != set(extras)
                or {requirement_key(value) for value in metadata.get_all("Requires-Dist", [])} != {requirement_key(value) for value in requirements}):
            raise ValueError("Wheel metadata differs from selected project.")
        if info + "entry_points.txt" in names:
            raise ValueError("Worktrees has no installed entry points.")
        if sha(archive.read(info + "licenses/LICENSE")) != expected["LICENSE"]:
            raise ValueError("Wheel license differs from selected source.")
    return {name: {"sha256": sha((dist / name).read_bytes()), "bytes": (dist / name).stat().st_size}
            for name in (wheel, source)}


def seal(root, revision, dist, *, qualification=False):
    selected = selection(root, revision, qualification=qualification)
    receipt_file = RECEIPT
    if set(p.name for p in dist.iterdir()) != set(artifact_names(selected)):
        raise ValueError("Seal requires only the original wheel and source archive.")
    receipt = {**selected, "artifacts": package_identity(dist, selected)}
    (dist / receipt_file).write_text(json.dumps(receipt, indent=2) + "\n")
    (dist / "SHA256SUMS").write_text("".join(f"{sha((dist / name).read_bytes())}  {name}\n"
                                               for name in (*artifact_names(selected), receipt_file)))
    return receipt


def verify(root, revision, dist, *, qualification=False):
    selected = selection(root, revision, qualification=qualification)
    receipt_file = RECEIPT
    expected = {*artifact_names(selected), receipt_file, "SHA256SUMS"}
    if set(p.name for p in dist.iterdir()) != expected:
        raise ValueError("Unexpected release asset set.")
    receipt = json.loads((dist / receipt_file).read_bytes())
    if receipt != {**selected, "artifacts": package_identity(dist, selected)}:
        raise ValueError("Release receipt does not match selected source and bytes.")
    sums = "".join(f"{sha((dist / name).read_bytes())}  {name}\n" for name in (*artifact_names(selected), receipt_file))
    if (dist / "SHA256SUMS").read_text() != sums:
        raise ValueError("Release checksums differ.")
    return receipt


def api(path, *args, missing=False):
    result = subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{path}", *args], capture_output=True, text=True)
    if result.returncode:
        if missing and "(HTTP 404)" in result.stderr:
            return None
        raise RuntimeError("GitHub operation failed; inspect its saved state before retrying.")
    return json.loads(result.stdout)


def download_asset(asset_id):
    return run("gh", "api", f"repos/{REPOSITORY}/releases/assets/{asset_id}",
               "-H", "Accept: application/octet-stream")


def publish(root, revision, dist):
    receipt = verify(root, revision, dist)
    tag = receipt["tag"]
    ref = api("git/ref/tags/" + tag, missing=True)
    if ref is not None and (ref.get("object", {}).get("type") != "commit" or ref["object"].get("sha") != revision):
        raise ValueError("Existing component tag differs; it will not be moved.")
    release = find_release(api, tag)
    if release:
        if not ref:
            raise ValueError("Existing release has no bound tag; preserve it for review.")
        remote_assets(download_asset, release, dist, complete=not release["draft"])
    if not ref:
        api("git/refs", "-X", "POST", "-f", "ref=refs/tags/" + tag, "-f", "sha=" + revision)
    if release and not release["draft"]:
        return {"tag": tag, "status": "already-published-exact-bytes"}
    if not release:
        release = api("releases", "-X", "POST", "-f", "tag_name=" + tag,
                      "-f", "name=Worktrees " + receipt["version"], "-F", "draft=true", "-f", "make_latest=false",
                      "-f", "body=Managed Git worktrees with durable ownership and recovery receipts. Source: " + revision +
                      ". Consumer selection is unchanged. Do not co-install with Unified while it owns this package.")
        release = read_release(api, release, tag)
    if not release["draft"]:
        raise ValueError("Component draft changed during preparation; preserve it for review.")
    present = remote_assets(download_asset, release, dist, complete=False)
    missing = [str(path) for path in sorted(dist.iterdir()) if path.name not in present]
    if missing:
        run("gh", "release", "upload", tag, *missing, "--repo", REPOSITORY)  # Never --clobber.
    release = read_release(api, release, tag)
    remote_assets(download_asset, release, dist, complete=True)
    if not release["draft"]:
        raise ValueError("Component draft changed during preparation; preserve it for review.")
    ref = api("git/ref/tags/" + tag)
    if ref["object"].get("type") != "commit" or ref["object"].get("sha") != revision:
        raise ValueError("Component tag changed during preparation; preserve the draft.")
    api(f"releases/{release['id']}", "-X", "PATCH", "-F", "draft=false", "-f", "make_latest=false")
    final = read_release(api, release, tag)
    remote_assets(download_asset, final, dist, complete=True)
    if final["draft"]:
        raise ValueError("Publication remained a draft.")
    return {"tag": tag, "status": "published", "revision": revision}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["plan", "seal", "verify", "publish"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--qualification", action="store_true", help="Allow an unmerged test candidate; never publication")
    args = parser.parse_args()
    if args.operation == "plan":
        result = selection(args.root, args.revision, qualification=args.qualification)
        if args.output:
            with args.output.open("a") as output:
                for key in ("revision", "version", "tag"):
                    output.write(f"{key}={result[key]}\n")
    else:
        if args.dist is None:
            parser.error("--dist is required")
        if args.operation == "publish":
            if args.qualification:
                parser.error("A qualification candidate cannot publish")
            result = publish(args.root, args.revision, args.dist)
        else:
            result = {"seal": seal, "verify": verify}[args.operation](args.root, args.revision, args.dist, qualification=args.qualification)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()


