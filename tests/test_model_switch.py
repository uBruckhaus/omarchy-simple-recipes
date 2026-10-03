from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, SessionLocal
from app.models import Setting
from app.lmstudio import load_model


def response(code, data):
    return httpx.Response(code, json=data, request=httpx.Request('POST', 'http://localhost/models/load'))


def test_single_model_router_unloads_previous_and_waits_for_new_model():
    listing = response(200, {'data': [
        {'id': 'old', 'status': {'value': 'loaded'}}, {'id': 'new', 'status': {'value': 'unloaded'}}]})
    ready = response(200, {'data': [{'id': 'new', 'status': {'value': 'loaded'}}]})
    with patch('app.lmstudio.httpx.get', side_effect=[listing, ready]), \
         patch('app.lmstudio.httpx.post', side_effect=[response(400, {'error': 'model limit reached'}), response(200, {'success': True}), response(200, {'success': True})]) as post:
        assert load_model('new', 'llamacpp')['success']
    assert [call.args[0].rsplit('/', 1)[-1] for call in post.call_args_list] == ['load', 'unload', 'load']
    assert post.call_args_list[1].kwargs['json'] == {'model': 'old'}
    assert post.call_args_list[2].kwargs['json'] == {'model': 'new'}


def test_current_model_is_reused_without_unload_or_reload():
    with patch('app.lmstudio.httpx.get', return_value=response(200, {'data': [{'id': 'same', 'status': {'value': 'loaded'}}]})), \
         patch('app.lmstudio.httpx.post') as post:
        assert load_model('same', 'llamacpp')['success']
    post.assert_not_called()


def test_unknown_model_does_not_unload_working_model():
    with patch('app.lmstudio.httpx.get', return_value=response(200, {'data': [{'id': 'old', 'status': {'value': 'loaded'}}]})), \
         patch('app.lmstudio.httpx.post') as post:
        import pytest
        with pytest.raises(ValueError): load_model('missing', 'llamacpp')
    post.assert_not_called()


def test_successful_selection_persists_and_failure_keeps_previous_choice():
    client = TestClient(app)
    with patch('app.main.load_model') as load:
        result = client.post('/api/ai/select', data={'provider': 'llamacpp', 'ai_model': 'selected'})
    assert result.json()['success']
    load.assert_called_once_with('selected', 'llamacpp')
    with patch('app.main.load_model', side_effect=RuntimeError('failed')):
        assert client.post('/api/ai/select', data={'provider': 'llamacpp', 'ai_model': 'broken'}).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(Setting).where(Setting.key == 'llamacpp_model')).value == 'selected'


def test_online_selection_is_saved_without_loading_local_server():
    with patch('app.main.load_model') as load:
        assert TestClient(app).post('/api/ai/select', data={'provider': 'openai', 'ai_model': 'online-choice'}).json()['success']
    load.assert_not_called()
    with SessionLocal() as db:
        assert db.scalar(select(Setting).where(Setting.key == 'openai_model')).value == 'online-choice'
