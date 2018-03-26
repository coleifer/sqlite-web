from wtforms.widgets import (
    Input,
    TextInput,
    FileInput,
)
from wtforms.widgets.html5 import DateTimeInput, NumberInput


WIDGETS_MAPPING = {
    'TEXT': TextInput,
    'd': DateTimeInput,
    'n': NumberInput,
    'b': FileInput
}


class FakeField(object):
    def __init__(self, index, name, widget_type=Input):
        self.id = 'field-id-{}'.format(index)
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
    for index, col in enumerate(columns):

        widget_type = WIDGETS_MAPPING[col.data_type]
        field = FakeField(index=index, name=col.name, widget_type=widget_type)
        fields.append(field)

    return fields
