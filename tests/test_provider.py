import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import urllib.request
import urllib.error
from unittest import mock

from sigil.provider import ModelProvider, NullProvider, OpenRouterProvider


def test_null_provider_echoes():
    p = NullProvider()
    out = p.complete("hello world")
    assert "hello world" in out
    assert out.startswith("[null-provider-echo]")


def test_openrouter_requires_key():
    with mock.patch.dict(os.environ, {}, clear=True):
        try:
            OpenRouterProvider(api_key=None)
            assert False, "expected ValueError without key"
        except ValueError:
            pass


def test_openrouter_missing_env_key():
    with mock.patch.dict(os.environ, {}, clear=True):
        try:
            OpenRouterProvider()
            assert False, "expected ValueError without env key"
        except ValueError:
            pass


def test_openrouter_builds_request_and_parses():
    fake_body = json.dumps(
        {"choices": [{"message": {"content": "model says hi"}}]}
    ).encode("utf-8")
    cm = mock.Mock()
    cm.__enter__ = mock.Mock(return_value=mock.Mock(read=mock.Mock(return_value=fake_body)))
    cm.__exit__ = mock.Mock(return_value=False)
    with mock.patch("urllib.request.urlopen", return_value=cm) as m:
        p = OpenRouterProvider(api_key="sk-test", model="openai/gpt-4o-mini")
        out = p.complete("hi")
        assert out == "model says hi"
        # assert request built correctly
        args, kwargs = m.call_args
        req = args[0]
        assert req.full_url == "https://openrouter.ai/api/v1/chat/completions"
        assert req.get_header("Authorization") == "Bearer sk-test"
        sent = json.loads(req.data.decode("utf-8"))
        assert sent["model"] == "openai/gpt-4o-mini"
        assert sent["messages"][0]["content"] == "hi"


def test_openrouter_401_raises_permission():
    cm = mock.Mock()
    cm.__enter__ = mock.Mock(side_effect=urllib.error.HTTPError(None, 401, "no", None, None))
    cm.__exit__ = mock.Mock(return_value=False)
    with mock.patch("urllib.request.urlopen", return_value=cm):
        p = OpenRouterProvider(api_key="sk-bad")
        try:
            p.complete("hi")
            assert False, "expected PermissionError"
        except PermissionError:
            pass


def test_max_context_tokens_present():
    assert NullProvider().max_context_tokens > 0
    assert OpenRouterProvider(api_key="x").max_context_tokens > 0
