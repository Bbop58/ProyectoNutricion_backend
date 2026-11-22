"""Deterministic Spanish report periods using the caller's Bolivia date."""
import calendar
import re
from datetime import date, timedelta
from app.core.exceptions import BadRequestException

MONTHS = 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()
WORDS = dict(zip('un uno una dos tres cuatro cinco seis siete ocho nueve diez once doce'.split(), [1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]))


def report_period(text, today):
    def finish(start, end):
        if start > end:
            raise BadRequestException('La fecha inicial debe ser anterior a la final. Indica el periodo completo.')
        return start.isoformat(), end.isoformat()

    try:
        iso = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', text)
        numeric = re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', text)
        if iso:
            return finish(date.fromisoformat(iso[0]), date.fromisoformat(iso[-1]))
        if numeric:
            values = [date(int(y), int(m), int(d)) for d, m, y in numeric]
            return finish(values[0], values[-1])
        named = list(re.finditer(r'\b(\d{1,2})\s+(?:de\s+)?(' + '|'.join(MONTHS) + r')(?:\s+(?:de[l]?\s+)?(20\d{2}))?\b', text))
        if named:
            year = next((int(m[3]) for m in reversed(named) if m[3]), today.year)
            values = [date(int(m[3]) if m[3] else year, MONTHS.index(m[2]) + 1, int(m[1])) for m in named]
            shared_month = re.search(r'\b(?:del?|entre el)\s+(\d{1,2})\s+(?:al|y el)\s+\d{1,2}\s+(?:de\s+)?' + named[0][2], text)
            if len(values) == 1 and shared_month:
                values.insert(0, date(year, MONTHS.index(named[0][2]) + 1, int(shared_month[1])))
            return finish(values[0], values[-1])
        recent = re.search(r'ultim[oa]s?\s+(\d+|' + '|'.join(WORDS) + r')\s+(dias?|semanas?|meses?|anos?)', text)
        if recent:
            n = int(recent[1]) if recent[1].isdigit() else WORDS[recent[1]]
            if not 1 <= n <= 366:
                raise BadRequestException('Indica un periodo entre 1 y 366 unidades.')
            unit = recent[2]
            if unit.startswith('mes'):
                index = today.year * 12 + today.month - 1 - n
                start = date(index // 12, index % 12 + 1, min(today.day, calendar.monthrange(index // 12, index % 12 + 1)[1]))
            elif unit.startswith('ano'):
                start = date(today.year - n, today.month, min(today.day, calendar.monthrange(today.year - n, today.month)[1]))
            else:
                start = today - timedelta(days=n * (7 if unit.startswith('semana') else 1) - 1)
            return finish(start, today)
        quarter = re.search(r'\b(primer|segundo|tercer|cuarto|[1-4])\s+trimestre', text)
        if quarter or 'este trimestre' in text or 'trimestre pasado' in text:
            year_match = re.search(r'\b(20\d{2})\b', text)
            year = int(year_match[1]) if year_match else today.year
            q = ((today.month - 1) // 3) + 1
            if quarter:
                q = int(quarter[1]) if quarter[1].isdigit() else {'primer': 1, 'segundo': 2, 'tercer': 3, 'cuarto': 4}[quarter[1]]
            elif 'pasado' in text:
                q -= 1
                if not q: q, year = 4, year - 1
            month = q * 3
            end = today if 'este trimestre' in text else date(year, month, calendar.monthrange(year, month)[1])
            return finish(date(year, month - 2, 1), end)
        if 'anteayer' in text: return finish(today - timedelta(days=2), today - timedelta(days=2))
        if 'ayer' in text: return finish(today - timedelta(days=1), today - timedelta(days=1))
        if re.search(r'\bhoy\b', text): return finish(today, today)
        if 'semana pasada' in text:
            end = today - timedelta(days=today.weekday() + 1)
            return finish(end - timedelta(days=6), end)
        if 'esta semana' in text: return finish(today - timedelta(days=today.weekday()), today)
        if 'mes pasado' in text or 'mes anterior' in text:
            end = today.replace(day=1) - timedelta(days=1)
            return finish(end.replace(day=1), end)
        if 'este mes' in text or 'mes actual' in text: return finish(today.replace(day=1), today)
        if 'ano pasado' in text: return finish(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))
        mentions = list(re.finditer(r'\b(' + '|'.join(MONTHS) + r')(?:\s+(?:de[l]?\s+)?(20\d{2}))?\b', text))
        if mentions:
            year = next((int(m[2]) for m in reversed(mentions) if m[2]), today.year)
            first, last = mentions[0], mentions[-1]
            sm, em = MONTHS.index(first[1]) + 1, MONTHS.index(last[1]) + 1
            sy, ey = int(first[2]) if first[2] else year, int(last[2]) if last[2] else year
            return finish(date(sy, sm, 1), date(ey, em, calendar.monthrange(ey, em)[1]))
        year = re.search(r'\b(20\d{2})\b', text)
        if year:
            y = int(year[1])
            return finish(date(y, 1, 1), today if y == today.year else date(y, 12, 31))
        if re.search(r'\b(?:ultimos?|ultimas?|trimestre|semestre|desde|entre|fecha)\b', text):
            raise BadRequestException('Aclara el periodo: por ejemplo, últimos tres meses o del 1 de marzo al 30 de junio de 2026.')
        return finish(date(today.year, 1, 1), today)
    except ValueError:
        raise BadRequestException('La fecha indicada no existe. Revisa el día, mes y año.')
