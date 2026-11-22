from datetime import date
import pytest
from tests.test_reporting_analytics import reporting, voice, query, headers
from app.services.report_period_service import report_period
from app.core.exceptions import BadRequestException


@pytest.mark.parametrize('text,start,end', [
    ('pagos', '2026-01-01', '2026-11-22'),
    ('ultimos tres meses', '2026-08-22', '2026-11-22'),
    ('ultimos 7 dias', '2026-11-16', '2026-11-22'),
    ('del 1 de marzo al 30 de junio', '2026-03-01', '2026-06-30'),
    ('entre el 01/03/2026 y el 30/06/2026', '2026-03-01', '2026-06-30'),
    ('de enero a marzo de 2026', '2026-01-01', '2026-03-31'),
    ('segundo trimestre de 2026', '2026-04-01', '2026-06-30'),
    ('trimestre pasado', '2026-07-01', '2026-09-30'),
    ('mes pasado', '2026-10-01', '2026-10-31'),
    ('desde 2025-12-10 hasta 2026-01-02', '2025-12-10', '2026-01-02'),
])
def test_spoken_periods(text, start, end):
    assert report_period(text, date(2026, 11, 22)) == (start, end)


@pytest.mark.parametrize('text', ['del 31 de febrero al 4 de marzo', '2026-12-01 a 2026-01-01', 'ultimos muchos meses'])
def test_invalid_period_asks_for_clarification(text):
    with pytest.raises(BadRequestException):
        report_period(text, date(2026, 11, 22))


def test_admin_consolidates_and_exports_only_own_branches(client, reporting):
    result = voice(client, 'Ingresos por sucursal', 'admin')
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['parsed_request']['start_date'] == '2026-01-01'
    assert sum(row['value'] for row in data['report_data']['rows']) == 90
    recent = voice(client, 'Ingresos por sucursal ultimos tres meses', 'admin')
    assert recent.status_code == 200, recent.text
    assert recent.json()['parsed_request']['start_date'] == '2026-07-29'
    only = voice(client, 'Ingresos de sucursal Terminal', 'admin')
    assert only.status_code == 200, only.text
    assert only.json()['parsed_request']['branch_ids'] == ['a2']
    assert all(row['amount'] == 70 for row in only.json()['report_data']['rows'])
    assert voice(client, 'Ingresos de sucursal Inexistente', 'admin').status_code == 400
    assert voice(client, 'Ingresos de empresa Vida Sur', 'admin').status_code == 403
    request = data['parsed_request']
    request['columns'] = ['branch_name', 'value']
    projected = query(client, 'admin', **request)
    assert projected.status_code == 200, projected.text
    assert {c['key'] for c in projected.json()['columns']} == {'branch_name', 'value'}
    for fmt, signature in [('pdf', b'%PDF'), ('excel', b'PK')]:
        exported = client.post('/api/v1/reports/export/' + fmt, headers=headers('admin'), json=request)
        assert exported.status_code == 200, exported.text[:200]
        assert exported.content.startswith(signature)


def test_mobile_header_does_not_grant_other_company_access(client, reporting):
    response = client.post('/api/v1/reports/query', headers={**headers('admin'), 'X-Report-Client': 'mobile'},
                           json={'entity': 'patients', 'tenant_ids': ['beta']})
    assert response.status_code == 403


def test_show_clients_is_a_branch_ordered_list_not_a_count(client, reporting):
    result = voice(client, 'Mostrar los clientes registrados desde octubre a noviembre por sucursal.', 'admin')
    assert result.status_code == 200, result.text
    payload = result.json()
    plan, data = payload['parsed_request'], payload['report_data']
    assert not plan['aggregate'] and plan['group_by'] is None
    assert plan['start_date'] == '2026-10-01' and plan['end_date'] == '2026-11-30'
    assert plan['sort_by'] == 'branch_name'
    assert [row['full_name'] for row in data['rows']] == ['p1', 'p2', 'p3']
    assert [row['branch_name'] for row in data['rows']] == ['Centro', 'Centro', 'Terminal']
    assert all('value' not in row for row in data['rows'])
    counted = voice(client, 'Mostrar la cantidad de clientes registrados desde octubre a noviembre por sucursal.', 'admin')
    assert counted.status_code == 200, counted.text
    assert counted.json()['parsed_request']['aggregate']
    assert sum(row['value'] for row in counted.json()['report_data']['rows']) == 3


def test_ai_cannot_turn_a_client_listing_into_counts(client, reporting, monkeypatch):
    from app.services.gemini_service import GeminiService
    monkeypatch.setattr(GeminiService, 'is_configured', lambda: True)
    monkeypatch.setattr(GeminiService, 'generate_json', lambda *args, **kw: {
        'entity': 'patients', 'aggregate': True, 'group_by': 'branch', 'metric': 'count',
    })
    result = voice(client, 'Mostrar clientes por sucursal', 'admin')
    assert result.status_code == 200, result.text
    assert not result.json()['parsed_request']['aggregate']
    assert 'full_name' in result.json()['report_data']['rows'][0]
