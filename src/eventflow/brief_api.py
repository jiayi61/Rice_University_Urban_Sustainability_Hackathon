"""Extract event inputs only; the language model never generates model outputs."""
import json
import os
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def extract_brief(prompt: str) -> dict:
    key = os.getenv('OPENAI_API_KEY')
    if not key:
        raise ValueError('OPENAI_API_KEY is not configured. Fill in the city and venue fields, or configure .env.')
    fields = {'title': {'type': 'string'}, 'city_query': {'type': 'string'}, 'venue_query': {'type': 'string'},
              'date': {'type': ['string', 'null']}, 'start_time': {'type': ['string', 'null']},
              'attendance': {'type': ['integer', 'null']}, 'budget_usd': {'type': ['number', 'null']},
              'event_type': {'type': 'string', 'enum': ['stadium_concert', 'football', 'festival', 'convention', 'road_event', 'major_event']}}
    body = {'model': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'), 'store': False,
            'instructions': 'Extract the user event request. Translate city/venue to searchable English. Do not invent city, venue, attendance, budget or date. Missing strings are empty and missing numbers/dates null. date is YYYY-MM-DD, start_time HH:MM. budget_usd only if explicitly USD, otherwise null. Today: ' + date.today().isoformat(),
            'input': prompt, 'text': {'format': {'type': 'json_schema', 'name': 'event_brief', 'strict': True,
            'schema': {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}}}}
    request = Request('https://api.openai.com/v1/responses', data=json.dumps(body).encode(),
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=45) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise ValueError(f'OpenAI request failed (HTTP {exc.code}). Check the server API key, model access and quota.') from None
    except (URLError, TimeoutError):
        raise ValueError('OpenAI connection timed out or is unavailable. Retry or use the structured city and venue fields.') from None
    if result.get('status') != 'completed':
        raise ValueError('OpenAI did not complete the event extraction. Please retry.')
    try:
        text = ''.join(part['text'] for item in result['output'] if item.get('type') == 'message'
                       for part in item.get('content', []) if part.get('type') == 'output_text')
        parsed = json.loads(text)
        if not isinstance(parsed, dict) or set(parsed) != set(fields):
            raise ValueError()
        return parsed
    except (KeyError, TypeError, ValueError):
        raise ValueError('The API returned an invalid event brief. Please provide city and venue explicitly.') from None
