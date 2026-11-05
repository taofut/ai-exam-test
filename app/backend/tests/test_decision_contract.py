"""Organizer checks: explicit human review is separate from model suggestion fields."""
import pytest

from test_scaffold import app, client, headers, snapshot


@pytest.mark.starter
def test_edit_decision_accepts_human_fields_without_implementing_adoption(client, app):
    before = snapshot(app)
    response = client.post(
        '/api/inventories/10001/ai-replenishment/1/adopt-edited',
        headers=headers(),
        json={'suggestedQuantity': 4, 'reason': '已核对实际维修需求', 'reviewed': True},
    )
    assert response.status_code == 501, response.text
    assert response.json()['code'] == 'NOT_IMPLEMENTED'
    assert snapshot(app) == before


@pytest.mark.starter
@pytest.mark.parametrize('changes', [
    {'reviewed': 'true'},
    {'suggestedQuantity': True},
    {'needHuman': False},
    {'knowledgeReferences': [{'docId': 999, 'quote': '伪造'}]},
])
def test_edit_decision_rejects_malformed_or_model_controlled_fields(client, changes):
    response = client.post(
        '/api/inventories/10001/ai-replenishment/1/adopt-edited',
        headers=headers(),
        json={'suggestedQuantity': 4, 'reason': '已核对', 'reviewed': True, **changes},
    )
    assert response.status_code == 422


@pytest.mark.starter
def test_edit_decision_cannot_skip_explicit_review_field(client):
    response = client.post(
        '/api/inventories/10001/ai-replenishment/1/adopt-edited', headers=headers(),
        json={'suggestedQuantity': 4, 'reason': '已核对'},
    )
    assert response.status_code == 422


@pytest.mark.starter
def test_read_only_user_is_denied_before_edit_decision_validation(client):
    response = client.post(
        '/api/inventories/10001/ai-replenishment/1/adopt-edited',
        headers=headers('SITE-R001'), json={},
    )
    assert response.status_code == 403
