#!/usr/bin/env python3
"""Validate and read-only probe a DeepRacer on AWS connection profile."""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


EXPECTED_SCHEMA = "./deepracer.connection.schema.json"
HTTP_TIMEOUT_SECONDS = 15
ENVIRONMENT_FIELDS = {
    "apiEndpointUrl": ("deployment", "apiEndpointUrl"),
    "userPoolId": ("cognito", "userPoolId"),
    "userPoolClientId": ("cognito", "userPoolClientId"),
    "identityPoolId": ("cognito", "identityPoolId"),
    "region": ("deployment", "region"),
    "uploadBucketName": ("storage", "uploadBucketName"),
}
EXPECTED_KEYS = {
    "$": {"$schema", "version", "deployment", "cognito", "storage", "login"},
    "$.deployment": {"websiteUrl", "runtimeConfigUrl", "apiEndpointUrl", "region"},
    "$.cognito": {"userPoolId", "userPoolClientId", "identityPoolId"},
    "$.storage": {"uploadBucketName"},
    "$.login": {"email", "invitationAccountId", "racerAlias"},
}
FORBIDDEN_KEY_FRAGMENTS = ("password", "passwd", "token", "cookie")
FORBIDDEN_NORMALIZED_KEYS = {
    "accesskey",
    "accesskeyid",
    "awsaccesskey",
    "awsaccesskeyid",
    "awssecretaccesskey",
    "secretaccesskey",
    "secretkey",
}
REGION_RE = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USER_POOL_RE = re.compile(r"^(?P<region>[a-z]{2}(?:-gov)?-[a-z]+-\d)_[A-Za-z0-9]+$")
IDENTITY_POOL_RE = re.compile(
    r"^(?P<region>[a-z]{2}(?:-gov)?-[a-z]+-\d):[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
CLIENT_ID_RE = re.compile(r"^[a-z0-9]+$")
BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{1,61}[a-z0-9])?$")
ENV_ASSIGNMENT_RE = re.compile(
    r"\A\s*window\.EnvironmentConfig\s*=\s*(?P<json>\{.*\})\s*;\s*\Z",
    re.DOTALL,
)


def _normalise_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _is_forbidden_key(key: str) -> bool:
    normalized = _normalise_key(key)
    return normalized in FORBIDDEN_NORMALIZED_KEYS or any(
        fragment in normalized for fragment in FORBIDDEN_KEY_FRAGMENTS
    )


def _find_forbidden_keys(value: Any, path: str = "$") -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _is_forbidden_key(str(key)):
                yield child_path
            yield from _find_forbidden_keys(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _find_forbidden_keys(child, f"{path}[{index}]")


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"connection file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(value, dict):
        raise ValueError("connection file must contain a JSON object")
    return value


def _require_object(config: dict[str, Any], name: str, errors: list[str]) -> dict[str, Any] | None:
    value = config.get(name)
    if not isinstance(value, dict):
        errors.append(f"$.{name} must be an object")
        return None
    return value


def _validate_exact_keys(value: dict[str, Any], path: str, errors: list[str]) -> None:
    expected = EXPECTED_KEYS[path]
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    for key in missing:
        errors.append(f"{path}.{key} is required")
    for key in unknown:
        errors.append(f"{path}.{key} is not supported")


def _validate_https_url(value: Any, path: str, errors: list[str]) -> Any:
    if not isinstance(value, str):
        errors.append(f"{path} must be an HTTPS URL")
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        errors.append(f"{path} must be an HTTPS URL without credentials, query, or fragment")
        return None
    return parsed


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    forbidden_paths = list(_find_forbidden_keys(config))
    if forbidden_paths:
        errors.append("sensitive keys are not allowed: " + ", ".join(forbidden_paths))

    _validate_exact_keys(config, "$", errors)
    if config.get("$schema") != EXPECTED_SCHEMA:
        errors.append(f"$.$schema must equal {EXPECTED_SCHEMA!r}")
    if config.get("version") != 1 or isinstance(config.get("version"), bool):
        errors.append("$.version must be the integer 1")

    deployment = _require_object(config, "deployment", errors)
    cognito = _require_object(config, "cognito", errors)
    storage = _require_object(config, "storage", errors)
    login = _require_object(config, "login", errors)
    if deployment is not None:
        _validate_exact_keys(deployment, "$.deployment", errors)
        website = _validate_https_url(deployment.get("websiteUrl"), "$.deployment.websiteUrl", errors)
        runtime = _validate_https_url(
            deployment.get("runtimeConfigUrl"), "$.deployment.runtimeConfigUrl", errors
        )
        api = _validate_https_url(deployment.get("apiEndpointUrl"), "$.deployment.apiEndpointUrl", errors)
        if runtime is not None and not runtime.path.endswith("/env.js"):
            errors.append("$.deployment.runtimeConfigUrl must end with /env.js")
        if website is not None and runtime is not None and website.netloc != runtime.netloc:
            errors.append("$.deployment.runtimeConfigUrl must use the websiteUrl host")
        if api is not None and (not api.path.strip("/") or not api.path.endswith("/")):
            errors.append("$.deployment.apiEndpointUrl must include a deployment stage and end with /")
        region = deployment.get("region")
        if not isinstance(region, str) or not REGION_RE.fullmatch(region):
            errors.append("$.deployment.region must be a valid AWS region")

    if cognito is not None:
        _validate_exact_keys(cognito, "$.cognito", errors)
        user_pool = cognito.get("userPoolId")
        user_pool_match = USER_POOL_RE.fullmatch(user_pool) if isinstance(user_pool, str) else None
        if user_pool_match is None:
            errors.append("$.cognito.userPoolId must be a region-prefixed Cognito user pool ID")
        identity_pool = cognito.get("identityPoolId")
        identity_pool_match = (
            IDENTITY_POOL_RE.fullmatch(identity_pool) if isinstance(identity_pool, str) else None
        )
        if identity_pool_match is None:
            errors.append("$.cognito.identityPoolId must be a region-prefixed Cognito identity pool ID")
        client_id = cognito.get("userPoolClientId")
        if not isinstance(client_id, str) or not CLIENT_ID_RE.fullmatch(client_id):
            errors.append("$.cognito.userPoolClientId must contain lowercase letters and digits")
        if deployment is not None and isinstance(deployment.get("region"), str):
            region = deployment["region"]
            if user_pool_match is not None and user_pool_match.group("region") != region:
                errors.append("$.cognito.userPoolId region must match $.deployment.region")
            if identity_pool_match is not None and identity_pool_match.group("region") != region:
                errors.append("$.cognito.identityPoolId region must match $.deployment.region")

    if storage is not None:
        _validate_exact_keys(storage, "$.storage", errors)
        bucket = storage.get("uploadBucketName")
        if not isinstance(bucket, str) or not BUCKET_RE.fullmatch(bucket):
            errors.append("$.storage.uploadBucketName must be a valid S3 bucket name")

    if login is not None:
        _validate_exact_keys(login, "$.login", errors)
        email = login.get("email")
        if not isinstance(email, str) or not EMAIL_RE.fullmatch(email):
            errors.append("$.login.email must be a valid email address")
        account_id = login.get("invitationAccountId")
        if not isinstance(account_id, str) or not account_id.strip():
            errors.append("$.login.invitationAccountId must be a non-empty string")
        elif re.fullmatch(r"\d{12}", account_id):
            errors.append("$.login.invitationAccountId is an invitation ID, not a 12-digit AWS account ID")
        alias = login.get("racerAlias")
        if not isinstance(alias, str):
            errors.append("$.login.racerAlias must be a string; use an empty string when unknown")
    return errors


def parse_environment_config(source: bytes | str) -> dict[str, Any]:
    text = source.decode("utf-8", errors="strict") if isinstance(source, bytes) else source
    match = ENV_ASSIGNMENT_RE.fullmatch(text)
    if match is None:
        raise ValueError("env.js must contain only 'window.EnvironmentConfig = <JSON>;' ")
    try:
        value = json.loads(match.group("json"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"env.js contains invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(value, dict):
        raise ValueError("env.js EnvironmentConfig must be a JSON object")
    missing = sorted(set(ENVIRONMENT_FIELDS) - set(value))
    if missing:
        raise ValueError("env.js is missing public fields: " + ", ".join(missing))
    return value


def _http_get(url: str, timeout: int = HTTP_TIMEOUT_SECONDS) -> tuple[int, bytes]:
    request = Request(url, method="GET", headers={"User-Agent": "deepracer-connection-check/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.getcode(), response.read(1_048_577)
    except HTTPError as exc:
        return exc.code, exc.read(1_048_577)


def _network_error(label: str, exc: BaseException) -> str:
    if isinstance(exc, URLError):
        reason = exc.reason
    else:
        reason = exc
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return f"{label} timed out"
    return f"{label} request failed: {reason}"


def check_live(config: dict[str, Any]) -> list[str]:
    errors = validate_config(config)
    if errors:
        return errors

    deployment = config["deployment"]
    try:
        status, body = _http_get(deployment["websiteUrl"])
        if status != 200:
            errors.append(f"website returned HTTP {status}; expected 200")
        elif b"deepracer" not in body.lower():
            errors.append("website response does not contain a DeepRacer page marker")
    except (OSError, URLError) as exc:
        errors.append(_network_error("website", exc))

    live_config: dict[str, Any] | None = None
    try:
        status, body = _http_get(deployment["runtimeConfigUrl"])
        if status != 200:
            errors.append(f"env.js returned HTTP {status}; expected 200")
        else:
            try:
                live_config = parse_environment_config(body)
            except (UnicodeDecodeError, ValueError) as exc:
                errors.append(str(exc))
    except (OSError, URLError) as exc:
        errors.append(_network_error("env.js", exc))

    if live_config is not None:
        for field, path in ENVIRONMENT_FIELDS.items():
            local: Any = config
            for segment in path:
                local = local[segment]
            live = live_config[field]
            if live != local:
                errors.append(f"drift {'.'.join(path)}: local={local!r}, live={live!r}")

    profile_url = urljoin(deployment["apiEndpointUrl"], "profile")
    try:
        status, _ = _http_get(profile_url)
        if status not in {401, 403}:
            errors.append(f"unauthenticated /profile returned HTTP {status}; expected 401 or 403")
    except (OSError, URLError) as exc:
        errors.append(_network_error("unauthenticated /profile", exc))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "check-live"):
        subcommand = subcommands.add_parser(command)
        subcommand.add_argument("config", type=Path, help="connection JSON file")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors = validate_config(config) if args.command == "validate" else check_live(config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2 if args.command == "validate" else 1
    print(f"OK: {args.command} passed for {args.config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
