import httpx
import pytest
from app import gateway


def test_ark_request_output_budget_and_sanitized_model_activation(client, novel, monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL', 'https://ark.cn-beijing.volces.com/api/v3')
    monkeypatch.setenv('LLM_MODEL', 'doubao-seed-2-1-pro-260628')
    monkeypatch.setenv('LLM_TRANSPORT', 'http')
    captured = []
    def request(url, **kwargs):
        captured.append(kwargs['json'])
        return httpx.Response(404, json={'error': {'code': 'ModelNotOpen', 'message': 'private-account-id and credentials'}}, request=httpx.Request('POST', url))
    monkeypatch.setattr(gateway.httpx, 'post', request)
    with pytest.raises(ValueError, match='模型尚未开通') as error:
        gateway.complete(novel['id'], None, 'outline', '简短大纲', '小说作者', max_tokens=1200)
    assert 'private-account' not in str(error.value)
    assert captured[0]['max_completion_tokens'] == 1200
    assert 'max_tokens' not in captured[0]
    assert captured[0]['thinking'] == {'type': 'disabled'}


def test_ark_catalog_filters_inactive_and_nonwriting_models(client, monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL', 'https://ark.cn-beijing.volces.com/api/v3')
    monkeypatch.setenv('LLM_TRANSPORT', 'http')
    data = {'data': [
        {'id': 'old-model', 'status': 'Shutdown', 'task_type': ['TextGeneration']},
        {'id': 'embedding', 'task_type': ['TextEmbedding']},
        {'id': 'doubao-seed-2-1-pro-260628', 'task_type': ['TextGeneration']},
        {'id': 'metadata-missing', 'task_type': None},
    ]}
    monkeypatch.setattr(gateway.httpx, 'get', lambda url, **kwargs: httpx.Response(200, json=data, request=httpx.Request('GET', url)))
    assert client.get('/api/models').json() == {'models': ['doubao-seed-2-1-pro-260628'], 'source': 'catalog'}
