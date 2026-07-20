from __future__ import annotations

import copy
import importlib.util
import json
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "deepracer_connection.py"
SPEC = importlib.util.spec_from_file_location("deepracer_connection", TOOL_PATH)
assert SPEC and SPEC.loader
connection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = connection
SPEC.loader.exec_module(connection)


class DeepRacerConnectionTests(unittest.TestCase):
    def load_example(self) -> dict:
        return json.loads(
            (ROOT / "config" / "deepracer.connection.example.json").read_text(encoding="utf-8")
        )

    def live_environment(self, config: dict) -> dict:
        return {
            "apiEndpointUrl": config["deployment"]["apiEndpointUrl"],
            "userPoolId": config["cognito"]["userPoolId"],
            "userPoolClientId": config["cognito"]["userPoolClientId"],
            "identityPoolId": config["cognito"]["identityPoolId"],
            "region": config["deployment"]["region"],
            "uploadBucketName": config["storage"]["uploadBucketName"],
        }

    def env_script(self, config: dict) -> bytes:
        payload = json.dumps(self.live_environment(config), separators=(",", ":"))
        return f"window.EnvironmentConfig = {payload};\n".encode()

    def live_responses(self, config: dict, profile_status: int = 403) -> list[tuple[int, bytes]]:
        return [
            (200, b"<html><title>DeepRacer on AWS</title></html>"),
            (200, self.env_script(config)),
            (profile_status, b""),
        ]

    def test_example_is_valid(self) -> None:
        self.assertEqual(connection.validate_config(self.load_example()), [])

    def test_rejects_missing_and_unknown_fields(self) -> None:
        config = self.load_example()
        del config["storage"]["uploadBucketName"]
        config["login"]["unexpected"] = "value"
        errors = connection.validate_config(config)
        self.assertIn("$.storage.uploadBucketName is required", errors)
        self.assertIn("$.login.unexpected is not supported", errors)

    def test_rejects_insecure_urls_and_api_without_stage(self) -> None:
        config = self.load_example()
        config["deployment"]["websiteUrl"] = "http://example.test/"
        config["deployment"]["apiEndpointUrl"] = "https://api.example.test/"
        errors = connection.validate_config(config)
        self.assertTrue(any("websiteUrl must be an HTTPS URL" in error for error in errors))
        self.assertTrue(any("must include a deployment stage" in error for error in errors))

    def test_rejects_invalid_email_and_region_mismatches(self) -> None:
        config = self.load_example()
        config["login"]["email"] = "not-an-email"
        config["deployment"]["region"] = "us-west-2"
        errors = connection.validate_config(config)
        self.assertIn("$.login.email must be a valid email address", errors)
        self.assertIn("$.cognito.userPoolId region must match $.deployment.region", errors)
        self.assertIn("$.cognito.identityPoolId region must match $.deployment.region", errors)

    def test_rejects_twelve_digit_aws_account_id(self) -> None:
        config = self.load_example()
        config["login"]["invitationAccountId"] = "123456789012"
        self.assertTrue(
            any("not a 12-digit AWS account ID" in error for error in connection.validate_config(config))
        )

    def test_rejects_sensitive_keys_recursively(self) -> None:
        forbidden = (
            "password",
            "temporaryPassword",
            "permanentPassword",
            "secretAccessKey",
            "sessionToken",
            "accessToken",
            "refreshToken",
            "idToken",
            "cookie",
        )
        for forbidden_key in forbidden:
            with self.subTest(forbidden_key=forbidden_key):
                config = self.load_example()
                config["login"]["nested"] = {forbidden_key: "must-not-be-stored"}
                errors = connection.validate_config(config)
                self.assertTrue(any("sensitive keys are not allowed" in error for error in errors))

    def test_parse_environment_config_requires_json_assignment_only(self) -> None:
        config = self.load_example()
        parsed = connection.parse_environment_config(self.env_script(config))
        self.assertEqual(parsed, self.live_environment(config))
        with self.assertRaisesRegex(ValueError, "must contain only"):
            connection.parse_environment_config("alert('x');")
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            connection.parse_environment_config("window.EnvironmentConfig = {nope: 1};")

    def test_check_live_accepts_matching_public_values_and_auth_boundary(self) -> None:
        config = self.load_example()
        with patch.object(connection, "_http_get", side_effect=self.live_responses(config)) as http_get:
            self.assertEqual(connection.check_live(config), [])
        self.assertEqual(
            [call.args[0] for call in http_get.call_args_list],
            [
                config["deployment"]["websiteUrl"],
                config["deployment"]["runtimeConfigUrl"],
                config["deployment"]["apiEndpointUrl"] + "profile",
            ],
        )

    def test_check_live_reports_precise_runtime_drift(self) -> None:
        config = self.load_example()
        live = copy.deepcopy(config)
        live["storage"]["uploadBucketName"] = "different-live-bucket"
        responses = self.live_responses(live)
        with patch.object(connection, "_http_get", side_effect=responses):
            errors = connection.check_live(config)
        self.assertEqual(len([error for error in errors if error.startswith("drift ")]), 1)
        self.assertIn("drift storage.uploadBucketName", errors[0])
        self.assertIn("example-deepracer-upload-bucket", errors[0])
        self.assertIn("different-live-bucket", errors[0])

    def test_check_live_rejects_missing_marker_and_non_json_env(self) -> None:
        config = self.load_example()
        responses = [(200, b"ordinary page"), (200, b"not JavaScript JSON"), (403, b"")]
        with patch.object(connection, "_http_get", side_effect=responses):
            errors = connection.check_live(config)
        self.assertTrue(any("DeepRacer page marker" in error for error in errors))
        self.assertTrue(any("must contain only" in error for error in errors))

    def test_check_live_rejects_profile_200_and_5xx(self) -> None:
        config = self.load_example()
        for status in (200, 500):
            with self.subTest(status=status):
                with patch.object(
                    connection, "_http_get", side_effect=self.live_responses(config, profile_status=status)
                ):
                    errors = connection.check_live(config)
                self.assertTrue(any(f"HTTP {status}" in error for error in errors))

    def test_check_live_reports_network_timeout(self) -> None:
        config = self.load_example()
        responses = [
            URLError(socket.timeout("timed out")),
            (200, self.env_script(config)),
            (403, b""),
        ]
        with patch.object(connection, "_http_get", side_effect=responses):
            errors = connection.check_live(config)
        self.assertIn("website timed out", errors)

    def test_validate_cli_accepts_example(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(TOOL_PATH), "validate", str(ROOT / "config" / "deepracer.connection.example.json")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
