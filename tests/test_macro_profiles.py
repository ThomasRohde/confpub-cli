"""Tests for site-scoped learned Confluence macro profiles."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from confpub.converter import convert_markdown
from confpub.macro_profiles import (
    MacroProfile,
    extract_macro_candidates,
    load_macro_profiles,
    prepare_macros,
    save_macro_profile,
)
from confpub.reverse_converter import convert_storage_to_markdown


MERMAID_STORAGE = (
    '<ac:structured-macro ac:name="mermaid-cloud" ac:schema-version="1" '
    'data-layout="default" ac:local-id="volatile" ac:macro-id="volatile">'
    '<ac:parameter ac:name="toolbar">bottom</ac:parameter>'
    '<ac:parameter ac:name="filename">Sample</ac:parameter>'
    '<ac:parameter ac:name="zoom">fit</ac:parameter>'
    '<ac:parameter ac:name="revision">1</ac:parameter>'
    '</ac:structured-macro>'
)


def _mermaid_profile(alias: str = "mermaid") -> MacroProfile:
    candidate = extract_macro_candidates(
        MERMAID_STORAGE,
        attachments=[{"title": "Sample", "metadata": {"mediaType": "text/plain"}}],
        page_id="327681",
        title="Diagrams",
    )[0]
    return candidate.model_copy(update={"alias": alias})


def test_extracts_attachment_backed_macro_without_vendor_assumptions():
    profile = _mermaid_profile()

    assert profile.macro_name == "mermaid-cloud"
    assert profile.storage_format == "structured-macro"
    assert profile.body_type == "attachment"
    assert profile.attachment_parameter == "filename"
    assert profile.attachment_media_type == "text/plain"
    assert profile.attributes == {"ac:schema-version": "1", "data-layout": "default"}
    assert "ac:local-id" not in profile.attributes


def test_profiles_are_scoped_by_confluence_site(monkeypatch, tmp_path):
    monkeypatch.setattr("confpub.config.CONFIG_DIR", tmp_path)
    save_macro_profile("https://one.atlassian.net/wiki", _mermaid_profile())

    assert "mermaid" in load_macro_profiles("https://one.atlassian.net/wiki/")
    assert load_macro_profiles("https://two.atlassian.net/wiki") == {}


def test_prepare_and_render_attachment_profile(tmp_path):
    source = tmp_path / "checkout-flow"
    source.write_text("flowchart LR\nA --> B\n", encoding="utf-8")
    profiles = {"mermaid": _mermaid_profile()}
    markdown = "{macro:mermaid|source=checkout-flow|zoom=width}"

    prepared = prepare_macros(markdown, tmp_path, profiles)
    storage = convert_markdown(
        markdown,
        macro_profiles=profiles,
        macro_sources=prepared.sources,
    )

    assert prepared.warnings == []
    assert [asset.filename for asset in prepared.assets] == ["checkout-flow"]
    assert 'ac:name="mermaid-cloud"' in storage
    assert 'ac:schema-version="1"' in storage
    assert '<ac:parameter ac:name="filename">checkout-flow</ac:parameter>' in storage
    assert '<ac:parameter ac:name="zoom">width</ac:parameter>' in storage
    assert "source" not in storage
    assert "flowchart" not in storage


def test_reverse_conversion_uses_learned_alias_and_downloaded_source():
    result = convert_storage_to_markdown(
        MERMAID_STORAGE,
        attachment_map={"Sample": "assets/diagrams/Sample"},
        macro_profiles={"mermaid": _mermaid_profile()},
    )

    assert "{macro:mermaid|source=assets/diagrams/Sample}" in result.markdown
    assert result.unknown_macros == []


def test_forge_profile_rehydrates_body_from_source(tmp_path):
    storage = (
        '<ac:adf-extension><ac:adf-node type="extension">'
        '<ac:adf-attribute key="extension-key">ari/app/env/static/diagram</ac:adf-attribute>'
        '<ac:adf-attribute key="local-id">old</ac:adf-attribute>'
        '<ac:adf-attribute key="parameters"><ac:adf-parameter key="guest-params">'
        '<ac:adf-parameter key="__body-content">old body</ac:adf-parameter>'
        '</ac:adf-parameter></ac:adf-attribute></ac:adf-node></ac:adf-extension>'
    )
    profile = extract_macro_candidates(storage)[0].model_copy(update={"alias": "diagram"})
    assert "old body" not in (profile.storage_template or "")
    source = tmp_path / "diagram.txt"
    source.write_text("new diagram body", encoding="utf-8")
    markdown = "{macro:diagram|source=diagram.txt}"
    prepared = prepare_macros(markdown, tmp_path, {"diagram": profile})

    rendered = convert_markdown(
        markdown,
        macro_profiles={"diagram": profile},
        macro_sources=prepared.sources,
    )

    assert "new diagram body" in rendered
    assert "old body" not in rendered
    assert "ari/app/env/static/diagram" in rendered


def test_reverse_plain_text_profile_extracts_local_source():
    storage = (
        '<ac:structured-macro ac:name="diagram-source">'
        '<ac:parameter ac:name="theme">dark</ac:parameter>'
        '<ac:plain-text-body><![CDATA[flowchart LR\nA --> B\n]]></ac:plain-text-body>'
        '</ac:structured-macro>'
    )
    profile = extract_macro_candidates(storage)[0].model_copy(update={"alias": "diagram"})

    result = convert_storage_to_markdown(
        storage,
        macro_profiles={"diagram": profile},
        macro_source_prefix="assets/page/macro-sources",
    )

    assert "{macro:diagram|source=assets/page/macro-sources/diagram-1.txt}" in result.markdown
    assert result.generated_files == {
        "assets/page/macro-sources/diagram-1.txt": "flowchart LR\nA --> B\n",
    }


def test_reverse_forge_profile_extracts_local_source():
    storage = (
        '<ac:adf-extension><ac:adf-node type="extension">'
        '<ac:adf-attribute key="extension-key">ari/app/env/static/diagram</ac:adf-attribute>'
        '<ac:adf-attribute key="parameters"><ac:adf-parameter key="guest-params">'
        '<ac:adf-parameter key="__body-content">flowchart TD</ac:adf-parameter>'
        '</ac:adf-parameter></ac:adf-attribute></ac:adf-node></ac:adf-extension>'
    )
    profile = extract_macro_candidates(storage)[0].model_copy(update={"alias": "diagram"})

    result = convert_storage_to_markdown(
        storage,
        macro_profiles={"diagram": profile},
    )

    assert "{macro:diagram|source=macro-sources/diagram-1.txt}" in result.markdown
    assert result.generated_files["macro-sources/diagram-1.txt"] == "flowchart TD"


def test_macro_learn_cli_persists_selected_profile(run_cli, monkeypatch, tmp_path):
    monkeypatch.setattr("confpub.config.CONFIG_DIR", tmp_path)
    monkeypatch.setenv("CONFPUB_URL", "https://flounder.atlassian.net")
    mock_client = MagicMock()
    mock_client.get_page_by_id.return_value = {
        "id": "327681",
        "title": "Diagrams",
        "body": {"storage": {"value": MERMAID_STORAGE}},
    }
    mock_client.get_attachments.return_value = [
        {"title": "Sample", "metadata": {"mediaType": "text/plain"}},
    ]
    monkeypatch.setattr("confpub.confluence.build_client", lambda: mock_client)

    result = run_cli("macro", "learn", "--from-page", "327681", "--alias", "mermaid")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["result"]["profile"]["macro_name"] == "mermaid-cloud"
    assert payload["result"]["profile"]["body_type"] == "attachment"
    assert "mermaid" in load_macro_profiles("https://flounder.atlassian.net")
