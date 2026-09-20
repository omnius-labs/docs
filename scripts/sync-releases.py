#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3"]
# ///
"""GitHub Release の配布物を Cloudflare R2 にミラーし、Downloads 章を最新化する。

    ./scripts/sync-releases.py [--dry-run] [--product NAME]

対象は releases.toml に書く。同期の記録は data/releases.json に残り、
Hugo の downloads shortcode がそこから Downloads 表を描画する。
必要な環境変数は .envrc.example を参照する。

git は操作しない。GitHub 側で削除された Release にも追従しない。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import boto3
import tomllib
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "releases.toml"
STATE_PATH = REPO_ROOT / "data" / "releases.json"
PRODUCTS_DIR = REPO_ROOT / "content.ja" / "docs" / "products"
SHORTCODE = "{{< downloads >}}"
CHUNK_SIZE = 1024 * 1024


class SyncError(Exception):
    """利用者に見せるべき、回復不能な失敗。"""


# --- 設定と環境 ---------------------------------------------------------


def load_products(only: list[str] | None) -> list[dict[str, Any]]:
    if not CONFIG_PATH.exists():
        raise SyncError(f"設定ファイルがありません: {CONFIG_PATH}")
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    products = config.get("products", [])
    if not products:
        raise SyncError(f"{CONFIG_PATH} に [[products]] がありません")

    for product in products:
        for key in ("name", "repo"):
            if not product.get(key):
                raise SyncError(f"{CONFIG_PATH} の [[products]] に {key} がありません")

    if only:
        known = {p["name"] for p in products}
        unknown = sorted(set(only) - known)
        if unknown:
            raise SyncError(f"設定にないプロダクトです: {', '.join(unknown)}")
        products = [p for p in products if p["name"] in only]
    return products


def require_env() -> dict[str, str]:
    names = ("R2_BUCKET", "R2_ACCOUNT_ID", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise SyncError(
            "環境変数が設定されていません: "
            + ", ".join(missing)
            + "\n.envrc.example を参考に .envrc を用意してください。"
        )
    return {name: os.environ[name] for name in names}


def check_gh_auth() -> None:
    proc = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise SyncError(
            f"gh が認証されていません。gh auth login を実行してください。\n{detail}"
        )


# --- GitHub -------------------------------------------------------------


def gh_json(args: list[str]) -> Any:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SyncError(
            (proc.stderr or proc.stdout).strip()
            or f"gh {' '.join(args)} が失敗しました"
        )
    return json.loads(proc.stdout)


def flatten_pages(payload: Any) -> list[dict[str, Any]]:
    """gh api --slurp はページの配列を返す。平坦な配列で返る場合も許容する。"""
    items: list[dict[str, Any]] = []
    for entry in payload:
        if isinstance(entry, list):
            items.extend(entry)
        else:
            items.append(entry)
    return items


def fetch_releases(repo: str, include_prerelease: bool) -> list[dict[str, Any]]:
    payload = gh_json(["api", f"repos/{repo}/releases", "--paginate", "--slurp"])
    releases = []
    for release in flatten_pages(payload):
        if release.get("draft"):
            continue
        if release.get("prerelease") and not include_prerelease:
            continue
        releases.append(release)
    return releases


def digest_sha256(asset: dict[str, Any]) -> str | None:
    digest = asset.get("digest")
    if isinstance(digest, str) and digest.startswith("sha256:"):
        return digest.removeprefix("sha256:")
    return None


def download_asset(repo: str, tag: str, name: str, dest_dir: Path) -> Path:
    proc = subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            repo,
            "--pattern",
            glob_escape(name),
            "--dir",
            str(dest_dir),
            "--clobber",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SyncError(
            (proc.stderr or proc.stdout).strip() or "gh release download が失敗しました"
        )
    path = dest_dir / name
    if not path.is_file():
        raise SyncError(f"ダウンロードした {name} が見つかりません")
    return path


def glob_escape(name: str) -> str:
    """filepath.Match のメタ文字を無効化し、資産名を完全一致で指定する。"""
    return re.sub(r"([*?\[\]\\])", r"\\\1", name)


# --- R2 -----------------------------------------------------------------


def make_r2_client(env: dict[str, str]):
    # botocore 1.36 以降は既定で aws-chunked のチェックサムを送る。R2 はこれを
    # 受け付けないことがあるため、必要なときだけ送る設定にしておく。
    config = Config(
        region_name="auto",
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    return boto3.client(
        "s3",
        endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        config=config,
    )


def head_size(client, bucket: str, key: str) -> int | None:
    try:
        response = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    return response["ContentLength"]


def upload(client, bucket: str, key: str, path: Path) -> None:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type})


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- state --------------------------------------------------------------


def load_state() -> dict[str, list[dict[str, Any]]]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, list[dict[str, Any]]]) -> None:
    for releases in state.values():
        releases.sort(key=lambda r: r["published_at"], reverse=True)
        for release in releases:
            release["assets"].sort(key=lambda a: a["name"])
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def known_assets(
    state: dict[str, list[dict[str, Any]]], product: str
) -> dict[tuple[str, str], dict[str, Any]]:
    index = {}
    for release in state.get(product, []):
        for asset in release["assets"]:
            index[(release["tag"], asset["name"])] = asset
    return index


def upsert_asset(
    state: dict[str, list[dict[str, Any]]],
    product: str,
    release: dict[str, Any],
    asset: dict[str, Any],
) -> None:
    releases = state.setdefault(product, [])
    entry = next((r for r in releases if r["tag"] == release["tag_name"]), None)
    if entry is None:
        entry = {
            "tag": release["tag_name"],
            "published_at": release.get("published_at") or release.get("created_at"),
            "prerelease": bool(release.get("prerelease")),
            "assets": [],
        }
        releases.append(entry)
    entry["assets"] = [a for a in entry["assets"] if a["name"] != asset["name"]]
    entry["assets"].append(asset)


# --- ドキュメント -------------------------------------------------------


def ensure_download_section(product: str) -> bool:
    """Downloads 章が無ければ、GUIDELINES の章順に従って挿入する。"""
    path = PRODUCTS_DIR / product / "_index.md"
    if not path.is_file():
        raise SyncError(f"製品ページがありません: {path}")
    text = path.read_text(encoding="utf-8")
    if SHORTCODE in text:
        return False

    block = f"## Downloads\n\n{SHORTCODE}\n"
    match = re.search(r"^## Links\s*$", text, re.MULTILINE)
    if match:
        updated = text[: match.start()] + block + "\n" + text[match.start() :]
    else:
        updated = text.rstrip("\n") + "\n\n" + block
    path.write_text(updated, encoding="utf-8")
    return True


# --- 同期 ---------------------------------------------------------------


def sync_product(
    product: dict[str, Any],
    state: dict[str, list[dict[str, Any]]],
    client,
    env: dict[str, str],
    dry_run: bool,
    failures: list[str],
) -> int:
    name = product["name"]
    repo = product["repo"]
    pattern = product.get("assets", "*")
    releases = fetch_releases(repo, bool(product.get("prerelease")))
    already = known_assets(state, name)
    synced = 0

    for release in releases:
        tag = release["tag_name"]
        for asset in release.get("assets", []):
            asset_name = asset["name"]
            if not fnmatch.fnmatch(asset_name, pattern):
                continue
            if (tag, asset_name) in already:
                continue

            key = f"{name}/{tag}/{asset_name}"
            try:
                record = resolve_asset(repo, tag, asset, key, client, env, dry_run)
            except (SyncError, ClientError, BotoCoreError, OSError) as exc:
                failures.append(f"{name} {tag} {asset_name}: {exc}")
                continue

            if record is None:
                print(f"  [dry-run] {key} をアップロードします")
                continue
            upsert_asset(state, name, release, record)
            synced += 1
            if dry_run:
                print(f"  [dry-run] {key} は R2 にあります。state に記録します")
            else:
                print(f"  {key}")

    return synced


def resolve_asset(
    repo: str,
    tag: str,
    asset: dict[str, Any],
    key: str,
    client,
    env: dict[str, str],
    dry_run: bool,
) -> dict[str, Any] | None:
    """資産を R2 に置き、state に載せる記録を返す。dry-run では None を返す。"""
    bucket = env["R2_BUCKET"]
    asset_name = asset["name"]
    remote_size = head_size(client, bucket, key)

    # R2 に実体があり、サイズも一致する。GitHub の digest があれば state だけ直す。
    if remote_size is not None and remote_size == asset.get("size"):
        known = digest_sha256(asset)
        if known:
            return record_for(asset_name, remote_size, known, key)

    if dry_run:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        path = download_asset(repo, tag, asset_name, Path(tmp))
        checksum = sha256_of(path)
        size = path.stat().st_size
        if remote_size != size:
            upload(client, bucket, key, path)

    return record_for(asset_name, size, checksum, key)


def record_for(name: str, size: int, checksum: str, key: str) -> dict[str, Any]:
    """state に載せる 1 資産分の記録。

    key は R2 のオブジェクトキーそのもの。path はそれを URL に埋められる形に
    したもので、公開 URL は Hugo 側で params.downloadsBaseURL と繋いで作る。
    ここに絶対 URL を持たせないので、配信ドメインを変えても state は不変。
    """
    return {
        "name": name,
        "size": size,
        "sha256": checksum,
        "key": key,
        "path": quote(key),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="R2 にもファイルにも書き込まず、予定だけ出力する",
    )
    parser.add_argument(
        "--product",
        action="append",
        metavar="NAME",
        help="対象を絞る。繰り返し指定できる",
    )
    args = parser.parse_args()

    try:
        products = load_products(args.product)
        env = require_env()
        check_gh_auth()
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    client = make_r2_client(env)
    state = load_state()
    failures: list[str] = []
    total = 0

    for product in products:
        name = product["name"]
        print(f"{name} ({product['repo']})")
        try:
            total += sync_product(product, state, client, env, args.dry_run, failures)
        except (SyncError, ClientError, BotoCoreError) as exc:
            failures.append(f"{name}: {exc}")

    if args.dry_run:
        print("\ndry-run のため、data/releases.json と製品ページは変更していません。")
    else:
        save_state(state)
        for product in products:
            name = product["name"]
            if not state.get(name):
                continue
            try:
                if ensure_download_section(name):
                    print(f"{name}: Downloads 章を追加しました")
            except SyncError as exc:
                failures.append(f"{name}: {exc}")
        print(f"\n新たに同期した資産: {total} 件")

    if failures:
        print("\n失敗:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
