"""Read GitHub releases by exact ID and compare asset bytes before publication.

Shared authoring home: bkrabach/amplifier-platform-scheduling, scripts/.
Each caller supplies its own repository-bound readers and owns every mutation.
"""
import hashlib


def _release_id(value, tag):
    if (not isinstance(value, dict) or type(value.get("id")) is not int or value["id"] <= 0
            or value.get("tag_name") != tag or value.get("prerelease") is not False
            or type(value.get("draft")) is not bool or not isinstance(value.get("assets"), list)):
        raise ValueError("Unexpected existing component release.")
    return value["id"]


def read_release(api, value, tag):
    """A draft may be absent from tag lookup; retain the exact returned ID."""
    identity = _release_id(value, tag)
    observed = api(f"releases/{identity}")
    if _release_id(observed, tag) != identity:
        raise ValueError("Component release identity changed; preserve it for review.")
    return observed


def find_release(api, tag):
    value = api("releases/tags/" + tag, missing=True)
    if value is not None:
        return read_release(api, value, tag)
    # A tag-endpoint 404 does not establish that no draft exists. Exhaust the
    # authenticated listing before creating anything; failures are never empty.
    matches = []
    for page in range(1, 101):
        values = api(f"releases?per_page=100&page={page}")
        if (not isinstance(values, list) or len(values) > 100
                or any(not isinstance(item, dict) or not isinstance(item.get("tag_name"), str) for item in values)):
            raise ValueError("Unexpected component release listing.")
        matches.extend(item for item in values if item["tag_name"] == tag)
        if len(matches) > 1:
            raise ValueError("Multiple component releases match; preserve them for review.")
        if len(values) < 100:
            return read_release(api, matches[0], tag) if matches else None
    raise ValueError("Component release listing is incomplete; nothing will be created.")


def remote_assets(download_asset, release, dist, *, complete):
    expected = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in dist.iterdir()}
    assets = release.get("assets", [])
    names = [asset["name"] for asset in assets]
    if len(names) != len(set(names)) or not set(names) <= set(expected) or (complete and set(names) != set(expected)):
        raise ValueError("Existing release assets differ; nothing will be overwritten.")
    for asset in assets:
        raw = download_asset(asset["id"])
        if hashlib.sha256(raw).hexdigest() != expected[asset["name"]]:
            raise ValueError("Existing release bytes differ; nothing will be overwritten.")
    return set(names)
