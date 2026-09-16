"""Deferred report messages: translate templates, never SQL or user values."""

import json
from pathlib import Path


LANGUAGES = ('en', 'zh', 'ja')
CATALOG = json.loads(Path(__file__).with_name('messages.json').read_text(encoding='utf-8'))


def validate_language(language):
    if language not in LANGUAGES:
        raise ValueError('language must be en, zh, or ja')
    return language


class Message(str):
    """Behave as English text during analysis, retaining translation boundaries."""

    def __new__(cls, template, *values):
        value = super().__new__(cls, template.format(*values))
        value.template, value.values, value.parts = template, values, None
        return value

    def __add__(self, other):
        value = super().__new__(type(self), str(self) + str(other))
        value.parts = (self, other)
        return value

    def __radd__(self, other):
        value = super().__new__(type(self), str(other) + str(self))
        value.parts = (other, self)
        return value

    def render(self, language):
        if self.parts is not None:
            return ''.join(render(part, language) for part in self.parts)
        template = self.template if language == 'en' else CATALOG[self.template][language]
        return template.format(*(render(value, language) for value in self.values))


def message(template, *values):
    # Fail visibly during development when a new message lacks translations.
    if template not in CATALOG:
        raise ValueError('Missing report translation: ' + template)
    return Message(template, *values)


def message_join(separator, values):
    result = ''
    for i, value in enumerate(values):
        result = result + (separator if i else '') + value
    return result


def render(value, language):
    return value.render(language) if isinstance(value, Message) else str(value)


def localize_report(report, language):
    validate_language(language)
    report['language'] = language
    report['findings'] = [dict(f, **{key: render(f[key], language)
                                   for key in ('title', 'impact', 'recommendation')})
                          for f in report['findings']]
    report['limitations'] = [render(value, language) for value in report['limitations']]
    return report


def diagnostic(error):
    """Preserve known parser messages; do not leak untranslated runtime errors."""
    if error.args and isinstance(error.args[0], Message):
        return error.args[0]
    return message('Incomplete DDL structure.')
