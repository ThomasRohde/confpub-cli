"""Tests for confpub.verifier module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from confpub.errors import ConfpubError, ERR_IO_FILE_NOT_FOUND
from confpub.verifier import verify_assertions


SAMPLE_ASSERTIONS = [
    {"type": "page.exists", "space": "DEV", "title": "Overview"},
    {"type": "page.parent", "title": "Child", "expected_parent": "Overview"},
    {"type": "attachment.exists", "space": "DEV", "page": "Overview", "filename": "arch.png"},
]


@pytest.fixture
def assertions_file(tmp_path):
    f = tmp_path / "assertions.json"
    f.write_text(json.dumps(SAMPLE_ASSERTIONS))
    return f


class TestVerifyAssertions:
    @patch("confpub.verifier.load_config")
    @patch("confpub.verifier.ConfluenceClient")
    def test_all_pass(self, MockClient, mock_config, assertions_file):
        mock_client = MagicMock()
        mock_client.get_page.return_value = {"id": "123", "title": "Overview"}
        mock_client.get_attachments.return_value = [{"title": "arch.png"}]
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = verify_assertions(assertions_path=str(assertions_file))
        assert result["all_passed"] is True
        assert len(result["results"]) == 3
        assert all(r["passed"] for r in result["results"])

    @patch("confpub.verifier.load_config")
    @patch("confpub.verifier.ConfluenceClient")
    def test_page_not_found(self, MockClient, mock_config, assertions_file):
        mock_client = MagicMock()
        mock_client.get_page.return_value = None  # Page doesn't exist
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = verify_assertions(assertions_path=str(assertions_file))
        assert result["all_passed"] is False
        # page.exists should fail
        page_check = result["results"][0]
        assert page_check["passed"] is False

    def test_empty_assertions(self):
        result = verify_assertions()
        assert result["all_passed"] is True
        assert result["results"] == []

    def test_missing_assertions_file(self):
        with pytest.raises(ConfpubError) as exc_info:
            verify_assertions(assertions_path="/nonexistent/assertions.json")
        assert exc_info.value.code == ERR_IO_FILE_NOT_FOUND

    @patch("confpub.verifier.load_config")
    @patch("confpub.verifier.ConfluenceClient")
    def test_unknown_assertion_type(self, MockClient, mock_config, tmp_path):
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        f = tmp_path / "bad_assertions.json"
        f.write_text(json.dumps([{"type": "unknown.check"}]))

        result = verify_assertions(assertions_path=str(f))
        assert result["all_passed"] is False
        assert result["results"][0]["error"] == "Unknown assertion type: unknown.check"
