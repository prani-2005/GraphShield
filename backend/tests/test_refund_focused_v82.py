from pathlib import Path
import pytest
from graphshield.refund_agent import _normalize_llm_base


def test_groq_base_url_normalization():
    assert _normalize_llm_base('https://api.groq.com/openai/v1')=='https://api.groq.com/openai/v1'
    assert _normalize_llm_base(r'https\://api.groq.com/openai/v1')=='https://api.groq.com/openai/v1'
    assert _normalize_llm_base('https://api.groq.com/openai/v1/chat/completions')=='https://api.groq.com/openai/v1'
    with pytest.raises(ValueError):
        _normalize_llm_base('http://api.groq.com/openai/v1')
    with pytest.raises(ValueError):
        _normalize_llm_base('https://api.groq.com/not-the-api')


def test_ui_is_only_refund():
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text(encoding='utf8')
    for forbidden in ('read_document','edit_document','Converted OpenAPI tools','Honest limitations'):
        assert forbidden not in html
    assert 'V9 · HYDRADB HACKATHON' in html
