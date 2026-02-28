"""Tests for confpub.assets module."""

from pathlib import Path
from unittest.mock import MagicMock

from confpub.assets import (
    AssetRef,
    UploadedAsset,
    discover_assets,
    rewrite_image_urls,
    upload_assets,
)


class TestDiscoverAssets:
    def test_find_images_in_markdown(self, tmp_path):
        md = "![logo](images/logo.png)\n\nSome text\n\n![diagram](arch.svg)"
        # Create the files so they resolve properly
        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "logo.png").write_bytes(b"png")
        (tmp_path / "arch.svg").write_bytes(b"svg")

        assets = discover_assets(md, tmp_path)
        assert len(assets) == 2
        filenames = {a.filename for a in assets}
        assert "logo.png" in filenames
        assert "arch.svg" in filenames

    def test_skip_urls(self, tmp_path):
        md = "![remote](https://example.com/img.png)\n![also](//cdn.com/x.jpg)"
        assets = discover_assets(md, tmp_path)
        assert len(assets) == 0

    def test_deduplication(self, tmp_path):
        md = "![a](img.png)\n![b](img.png)"
        (tmp_path / "img.png").write_bytes(b"png")
        assets = discover_assets(md, tmp_path)
        assert len(assets) == 1

    def test_glob_patterns(self, tmp_path):
        (tmp_path / "diagrams").mkdir()
        (tmp_path / "diagrams" / "a.png").write_bytes(b"a")
        (tmp_path / "diagrams" / "b.png").write_bytes(b"b")
        (tmp_path / "diagrams" / "c.txt").write_bytes(b"c")

        assets = discover_assets("", tmp_path, asset_globs=["diagrams/*.png"])
        assert len(assets) == 2
        filenames = {a.filename for a in assets}
        assert "a.png" in filenames
        assert "b.png" in filenames
        assert "c.txt" not in filenames

    def test_combined_md_and_globs(self, tmp_path):
        (tmp_path / "logo.png").write_bytes(b"png")
        (tmp_path / "extra").mkdir()
        (tmp_path / "extra" / "icon.svg").write_bytes(b"svg")

        md = "![logo](logo.png)"
        assets = discover_assets(md, tmp_path, asset_globs=["extra/*.svg"])
        assert len(assets) == 2


class TestRewriteImageUrls:
    def test_rewrite_matching(self):
        storage = '<p>Text</p><ac:image><ri:url ri:value="logo.png" /></ac:image><p>More</p>'
        uploaded = [UploadedAsset(source_path="logo.png", filename="logo.png")]
        result = rewrite_image_urls(storage, uploaded)
        assert '<ri:attachment ri:filename="logo.png" />' in result
        assert "ri:url" not in result

    def test_rewrite_by_filename(self):
        storage = '<ac:image><ri:url ri:value="images/deep/photo.jpg" /></ac:image>'
        uploaded = [UploadedAsset(source_path="images/deep/photo.jpg", filename="photo.jpg")]
        result = rewrite_image_urls(storage, uploaded)
        assert '<ri:attachment ri:filename="photo.jpg" />' in result

    def test_no_match_keeps_original(self):
        storage = '<ac:image><ri:url ri:value="unknown.png" /></ac:image>'
        result = rewrite_image_urls(storage, [])
        assert "unknown.png" in result
        assert "ri:url" in result

    def test_multiple_images(self):
        storage = (
            '<ac:image><ri:url ri:value="a.png" /></ac:image>'
            '<ac:image><ri:url ri:value="b.png" /></ac:image>'
        )
        uploaded = [
            UploadedAsset(source_path="a.png", filename="a.png"),
            UploadedAsset(source_path="b.png", filename="b.png"),
        ]
        result = rewrite_image_urls(storage, uploaded)
        assert result.count("ri:attachment") == 2


class TestUploadAssets:
    def test_upload_returns_uploaded_assets(self):
        mock_client = MagicMock()
        mock_client.upload_attachment.return_value = {"id": "att_1"}

        assets = [
            AssetRef(source_path="img.png", resolved_path="/tmp/img.png", filename="img.png"),
        ]
        result = upload_assets(mock_client, "page_123", assets)
        assert len(result) == 1
        assert result[0].filename == "img.png"
        assert result[0].confluence_attachment_id == "att_1"
        mock_client.upload_attachment.assert_called_once_with("page_123", "/tmp/img.png")
