from wtforms import (
    Field,
    IntegerField,
    DateTimeField,
    StringField,
)
from wtforms.widgets import TextInput
from wtforms.form import BaseForm


FIELDS_MAPPING = {
    'TEXT': StringField,

}

WIDGETS_MAPPING = {
    'TEXT': TextInput,
}


class FakeField(object):
    def __init__(self, name, widget_type=None):
        self.id = None
        self.name = name
        self.label = name
        self.widget_type = widget_type

    def _value(self):
        return ''

    def __call__(self, **kwargs):
        widget = self.widget_type()
        return widget(self, class_='form-control', **kwargs)


def get_fields_for_columns(columns):
    fields = []
    for col in columns:

        widget_type = WIDGETS_MAPPING[col.data_type]
        field = FakeField(name=col.name, widget_type=widget_type)
        fields.append(field)

    return fields
