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

from __future__ import unicode_literals

import itertools
from collections import OrderedDict

from flask import session

from indico.modules.events.abstracts.models.abstracts import AbstractState
from indico.util.i18n import _
from indico.core.notifications import make_email, send_email
from indico.util.placeholders import replace_placeholders
from indico.util.rules import Condition, check_rule


class EmailNotificationCondition(Condition):
    #: Override if you want to customize the text
    #: that shouls up for "Any"
    any_caption = _("any")
    #: same for text that shows up for "none"
    none_caption = _("none")
    #: Text that will show inline in rule descriptions
    label_text = None

    @classmethod
    def get_available_values(cls, event=None, **kwargs):
        choices = cls._iter_available_values(event=event, **kwargs)
        if not cls.required:
            return OrderedDict(itertools.chain([('*', cls.any_caption), ('', cls.none_caption)], choices))
        else:
            return OrderedDict(choices)

    @classmethod
    def _iter_available_values(cls, event, **kwargs):
        raise NotImplemented


class TrackCondition(EmailNotificationCondition):
    """A condition that matches a particular track."""

    name = 'track'
    description = _("Destination Track")
    any_caption = _("any track")
    none_caption = _("no track")
    label_text = _("in")

    @classmethod
    def _iter_available_values(cls, event, **kwargs):
        return ((t.id, t.title) for t in event.tracks)

    @classmethod
    def get_test_track_set(cls, abstract):
        if abstract.state == AbstractState.accepted:
            return {abstract.accepted_track_id} if abstract.accepted_track_id else set()
        else:
            return {track.id for track in abstract.submitted_for_tracks}

    @classmethod
    def check(cls, values, abstract, **kwargs):
        return bool(set(values) & cls.get_test_track_set(abstract))

    @classmethod
    def is_none(cls, abstract, **kwargs):
        return not bool(cls.get_test_track_set(abstract))


class StateCondition(EmailNotificationCondition):
    """A condition that matches a particular abstract final state."""

    name = 'state'
    description = _("Final State")
    required = True

    compatible_with = {
        AbstractState.submitted.value: (),
        AbstractState.rejected.value: (),
        AbstractState.accepted.value: ('contribution_type', 'track'),
        AbstractState.merged.value: ('contribution_type', 'track'),
        AbstractState.duplicate.value: ('contribution_type', 'track'),
        AbstractState.withdrawn.value: ()
    }

    @classmethod
    def _iter_available_values(cls, **kwargs):
        return ((s.value, s.title) for s in AbstractState)

    @classmethod
    def check(cls, values, abstract, **kwargs):
        return abstract.state in values

    @classmethod
    def is_none(cls, abstract, **kwargs):
        return False


class ContributionTypeCondition(EmailNotificationCondition):
    """"A condition that matches a particular contribution type."""

    name = 'contribution_type'
    description = _("Contribution Type")
    any_caption = _("any type")
    none_caption = _("no type")
    label_text = _("as")

    @classmethod
    def _iter_available_values(cls, event, **kwargs):
        return ((ct.id, ct.name) for ct in event.contribution_types)

    @classmethod
    def get_test_contrib_type_id(cls, abstract):
        if abstract.state == AbstractState.accepted:
            return abstract.accepted_contrib_type_id
        else:
            return abstract.submitted_contrib_type_id

    @classmethod
    def check(cls, values, abstract, **kwargs):
        return cls.get_test_contrib_type_id(abstract) in values

    @classmethod
    def is_none(cls, abstract, **kwargs):
        return cls.get_test_contrib_type_id(abstract) is None


def send_abstract_notifications(abstract):
    """Send abstract notification e-mails.

    :param abstract: the abstract that is going to be checked
                     against the event's notification rules
    """
    for tpl in abstract.event_new.abstract_email_templates:
        matched = False
        for rule in tpl.rules:
            if check_rule('abstract-notifications', rule, abstract=abstract, event=abstract.event_new):
                matched = True
                to_recipients = []
                if tpl.include_submitter:
                    to_recipients.append(abstract.submitter.email)
                if tpl.include_authors:
                    to_recipients += [author.email for author in abstract.primary_authors]

                cc_recipients = list(tpl.extra_cc_emails)
                if tpl.include_coauthors:
                    cc_recipients += [author.email for author in abstract.secondary_authors]

                subject = replace_placeholders('abstract-notification-email', tpl.subject,
                                               abstract=abstract, escape_html=False)
                body = replace_placeholders('abstract-notification-email', tpl.body,
                                            abstract=abstract, escape_html=False)
                email = make_email(to_list=to_recipients, cc_list=cc_recipients, reply_address=tpl.reply_to_address,
                                   subject=subject, body=body)
                send_email(email, event=abstract.event_new, user=session.user)
        if tpl.stop_on_match and matched:
            break