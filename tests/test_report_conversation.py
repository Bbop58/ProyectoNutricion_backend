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
