# This file is part of Indico.
# Copyright (C) 2002 - 2016 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

from indico.core.db import db
from indico.modules.events.abstracts.models.abstracts import Abstract
from indico.modules.events.abstracts.models.fields import AbstractFieldValue
from indico.modules.events.abstracts.settings import abstracts_settings
from indico.modules.events.contributions.models.fields import ContributionField
from indico.util.i18n import _
from indico.util.string import encode_utf8
from indico.util.text import wordsCounter

FIELD_TYPE_MAP = {
    'input': 'text',
    'textarea': 'text',
    'selection': 'single_choice'
}


class AbstractFieldWrapper(object):
    """Wraps an actual ``ContributionField`` in order to emulate the old ``AbstractField``s."""

    @classmethod
    def wrap(cls, field):
        if field.field_type == 'single_choice':
            return AbstractSelectionFieldWrapper(field)
        return AbstractTextFieldWrapper(field)

    def __init__(self, contrib_field):
        self.field = contrib_field

    def getType(self):
        field = self.field

        if field.field_type == 'text':
            return 'textarea' if field.field_data.get('multiline') else 'input'
        else:
            return 'selection'

    def isMandatory(self):
        return self.field.is_required

    def getId(self):
        return self.field.legacy_id or str(self.field.id)

    def getCaption(self):
        return self.field.title

    def isActive(self):
        return self.field.is_active

    def getValues(self):
        data = self.field.field_data
        data.update({
            'id': self.field.id,
            'caption': self.field.title.encode('utf-8'),
            'isMandatory': self.field.is_required
        })
        return data

    def check(self, content):
        if self.field.is_active and self.field.is_required and not content:
            return [_("The field '{}' is mandatory").format(self.field.title)]
        return []


class AbstractTextFieldWrapper(AbstractFieldWrapper):
    """Wraps legacy ``AbstractTextAreaField`` and ``AbstractInputField``."""

    @property
    def max_words(self):
        return self.field.field_data.get('max_words', 0)

    @property
    def max_chars(self):
        return self.field.field_data.get('max_chars', 0)

    def getLimitation(self):
        return 'chars' if self.max_words is None else 'words'

    def getMaxLength(self):
        return self.max_words if self.max_chars is None else self.max_chars

    def getValues(self):
        data = super(AbstractTextFieldWrapper, self).getValues()
        data.update({
            'maxLength': self.getMaxLength(),
            'limitation': self.getLimitation()
        })
        return data

    def check(self, content):
        errors = super(AbstractTextFieldWrapper, self).check(content)

        if self.max_words and wordsCounter(str(content)) > self.max_words:
            errors.append(_("The field '{}' cannot be more than {} words long").format(
                self.field.title, self.max_words))
        elif self.max_chars and len(content) > self.max_chars:
            errors.append(_("The field '{}' cannot be more than {} characters long").format(
                self.field.title, self.max_chars))

        return errors


class AbstractDescriptionFieldProxy(object):
    """Simulates an ``AbstractTextField``"""

    def __init__(self, event):
        self.event = event

    @property
    def legacy_id(self):
        return 'content'

    @property
    def title(self):
        return _('Content')

    @property
    def is_active(self):
        return abstracts_settings.get(self.event, 'description_settings')['active']

    @property
    def field_type(self):
        return 'text'

    @property
    def field_data(self):
        settings = abstracts_settings.get(self.event, 'description_settings')
        return {
            'max_words': settings['max_words'],
            'max_chars': settings['max_chars'],
            'multiline': True
        }

    @property
    def is_required(self):
        return abstracts_settings.get(self.event, 'description_settings')['required']


class AbstractSelectionFieldWrapper(AbstractFieldWrapper):
    """Wraps legacy ``AbstractSelectionField``."""

    def getOption(self, option_id):
        return next((SelectedFieldOptionWrapper(option)
                     for option in self.field.field_data['options'] if option['id'] == option_id), None)

    def getOptions(self):
        return [SelectedFieldOptionWrapper(option) for option in self.field.field_data['options']]

    def getValues(self):
        data = super(AbstractSelectionFieldWrapper, self).getValues()
        data.update({
            'options': self.field.field_data['options']
        })
        return data

    def check(self, content):
        errors = super(AbstractSelectionFieldWrapper, self).check(content)

        if content:
            if next((op for op in self.getOptions() if op.getId() == content), None) is None:
                errors.append(_("The option with ID '{}' in the field {} doesn't exit").format(
                    content, self.field.title))

        return errors


class SelectedFieldOptionWrapper(object):
    """Wraps a selection field option."""

    def __init__(self, option):
        self.id = option['id']
        self.deleted = option['is_deleted']
        self.value = option['option']

    def __eq__(self, other):
        if isinstance(other, SelectedFieldOptionWrapper):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

    def __unicode__(self):
        return self.value

    @encode_utf8
    def __str__(self):
        return unicode(self)

    def getValue(self):
        return self.value

    def getId(self):
        return self.id

    def isDeleted(self):
        return self.deleted


class AbstractFieldManagerAdapter(object):
    """
    Provides an interface that closely resembles the old AbstractFieldMgr.

    But actually returns stored ``ContributionField``s.
    """

    def __init__(self, event):
        self.event = event

    @property
    def description_field(self):
        return AbstractDescriptionFieldProxy(self.event)

    def _notifyModification(self):
        pass

    def hasField(self, field_id):
        if field_id == 'content':
            return True

        legacy = self.event.contribution_fields.filter(ContributionField.legacy_id == field_id)
        if legacy:
            return True
        else:
            return AbstractFieldWrapper.wrap(
                self.event.contribution_fields.filter(ContributionField.id == int(field_id)).count()) > 0

    def getFieldById(self, field_id):
        if field_id == 'content':
            field = self.description_field
        else:
            field = self.event.contribution_fields.filter(ContributionField.legacy_id == field_id).first()
            if not field:
                field = self.event.contribution_fields.filter(ContributionField.id == int(field_id)).first()
        return AbstractFieldWrapper.wrap(field) if field else None

    def getFields(self):
        fields = [AbstractFieldWrapper.wrap(field) for field in self.event.contribution_fields]
        fields.append(AbstractFieldWrapper.wrap(AbstractDescriptionFieldProxy(self.event)))
        return fields

    def getActiveFields(self):
        fields = [AbstractFieldWrapper.wrap(field) for field in self.event.contribution_fields if field.is_active]
        fields.append(AbstractFieldWrapper.wrap(AbstractDescriptionFieldProxy(self.event)))
        return fields

    def hasActiveField(self, field_id):
        if field_id == 'content':
            return self.description_field.is_active
        return self.getFieldById(field_id).isActive() if self.getFieldById(field_id) else False

    def hasAnyActiveField(self):
        return (self.event.contribution_fields.filter(ContributionField.is_active).count() > 0 or
                self.description_field.is_active)

    def enableField(self, field_id):
        field = self.getFieldById(field_id)
        if field:
            field.is_active = True

    def disableField(self, field_id):
        field = self.getFieldById(field_id)
        if field:
            field.is_active = False


class AbstractDescriptionValue(object):
    """Simulates a ``ContributionFieldValue``."""

    def __init__(self, abstract):
        self.abstract = abstract

    @property
    def contribution_field(self):
        return AbstractDescriptionFieldProxy(self.abstract)

    @property
    def data(self):
        return self.abstract.description

    @data.setter
    def data(self, description):
        self.abstract.description = description


class AbstractLegacyMixin(object):
    """Implements legacy interface of ZODB ``Abstract`` object."""

    def _get_field_value(self, field_id):
        if field_id == 'content':
            return AbstractDescriptionValue(self.as_new)
        else:
            field = ContributionField.find_first(legacy_id=field_id, event_new=self.event)
            fval = AbstractFieldValue.find_first(contribution_field=field, abstract=self.as_new)
            if fval:
                return fval
            else:
                return AbstractFieldValue(contribution_field=field, abstract=self.as_new, data={})

    @property
    def event(self):
        return self._owner._owner.as_event

    @property
    def as_new(self):
        return Abstract.find_one(event_new=self.event, legacy_id=self._id)

    def getFields(self):
        data = {val.contribution_field.legacy_id: AbstractFieldContentWrapper(val)
                for val in self.as_new.field_values}
        data['content'] = self.as_new.description
        return data

    def getField(self, field_id):
        field_val = self._get_field_value(field_id)
        return AbstractFieldContentWrapper(field_val)

    def removeField(self, field_id):
        field_val = self._get_field_value(field_id)
        if field_val:
            self.as_new.field_values.remove(field_val)

    def setField(self, field_id, val):
        field_val = self._get_field_value(field_id)
        field_val.data = val


class AbstractFieldContentWrapper(object):
    """Emulates legacy ``AbstractFieldContent`` object."""

    def __init__(self, field_val):
        self.field_val = field_val

    @property
    def field(self):
        return self.field_val.contribution_field

    @property
    def value(self):
        return self.field_val.data

    def __eq__(self, other):
        if isinstance(other, AbstractFieldContentWrapper) and self.field.id == other.field.id:
            return self.field_val.data == other.data
        elif not isinstance(other, AbstractFieldContentWrapper):
            return self.field_val.data == other
        return False

    def __len__(self):
        return len(self.field_val.data)

    def __ne__(self, other):
        if isinstance(other, AbstractFieldContentWrapper) and self.field.id == other.field.id:
            return self.field_val.data != other.data
        elif not isinstance(other, AbstractFieldContentWrapper):
            return self.field_val.data != other
        return True

    def __str__(self):
        if self.field.field_type == 'single_choice':
            return str(AbstractSelectionFieldWrapper(self.field).getOption(self.value))
        return str(self.value)


class AbstractManagerLegacyMixin(object):
    """Adds methods necessary to the creation of abstracts, from the legacy code."""

    def _new_abstract(self, legacy_abstract, abstract_data):
        Abstract(legacy_id=legacy_abstract.getId(), event_new=legacy_abstract.getConference().as_event)
        db.session.flush()

    def _remove_abstract(self, legacy_abstract):
        db.session.delete(legacy_abstract.as_new)