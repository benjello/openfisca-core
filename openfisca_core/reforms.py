# -*- coding: utf-8 -*-


# OpenFisca -- A versatile microsimulation software
# By: OpenFisca Team <contact@openfisca.fr>
#
# Copyright (C) 2011, 2012, 2013, 2014, 2015 OpenFisca Team
# https://github.com/openfisca
#
# This file is part of OpenFisca.
#
# OpenFisca is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# OpenFisca is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import collections

from . import columns, formulas, periods, taxbenefitsystems, tools


class Reform(taxbenefitsystems.AbstractTaxBenefitSystem):
    """A reform is a variant of a TaxBenefitSystem, that refers to the real TaxBenefitSystem as its reference."""
    label = None
    name = None

    def __init__(self, entity_class_by_key_plural = None, label = None, legislation_json = None, name = None,
            reference = None):
        if reference is not None:
            self.reference = reference
        assert self.reference is not None, u'Reform requires a reference tax-benefit-system.'
        assert isinstance(self.reference, taxbenefitsystems.AbstractTaxBenefitSystem)

        if entity_class_by_key_plural is None and self.entity_class_by_key_plural is None:
            entity_class_by_key_plural = self.reference.entity_class_by_key_plural
        if legislation_json is None and self.legislation_json is None:
            legislation_json = self.reference.legislation_json
        if self.preprocess_compact_legislation is None and self.reference.preprocess_compact_legislation is not None:
            self.preprocess_compact_legislation = self.reference.preprocess_compact_legislation
        if self.Scenario is None:
            self.Scenario = self.reference.Scenario

        self.CURRENCY = self.reference.CURRENCY
        self.DECOMP_DIR = self.reference.DECOMP_DIR

        super(Reform, self).__init__(
            entity_class_by_key_plural = entity_class_by_key_plural,
            legislation_json = legislation_json,
            )

        if name is not None:
            self.name = name
        assert self.name is not None

        if label is not None:
            self.label = label
        if self.label is None:
            self.label = self.name


def clone_column(column):
    reform_column = tools.empty_clone(column)
    reform_column.__dict__ = column.__dict__.copy()
    return reform_column


def clone_entity_classes(entity_class_by_key_plural):
    return {
        key_plural: clone_entity_class(entity_class)
        for key_plural, entity_class in entity_class_by_key_plural.iteritems()
        }


def clone_entity_class(entity_class):
    class ReformEntity(entity_class):
        pass
    ReformEntity.column_by_name = entity_class.column_by_name.copy()
    return ReformEntity


def find_item_at_date(items, date, nearest_in_period = None):
    """
    Find an item (a dict with start, stop, value key) at a specific date in a list of items which have each one
    a start date and a stop date.
    """
    instant = periods.instant(date)
    instant_str = str(instant)
    for item in items:
        if item['start'] <= instant_str <= item['stop']:
            return item
    if nearest_in_period is not None and nearest_in_period.start <= instant <= nearest_in_period.stop:
        earliest_item = min(items, key = lambda item: item['start'])
        if instant_str < earliest_item['start']:
            return earliest_item
        latest_item = max(items, key = lambda item: item['stop'])
        if instant_str > latest_item['stop']:
            return latest_item
    return None


def new_simple_reform_class(label = None, legislation_json = None, name = None, reference = None):
    assert isinstance(name, basestring)
    assert isinstance(reference, taxbenefitsystems.AbstractTaxBenefitSystem)
    reform_entity_class_by_key_plural = clone_entity_classes(reference.entity_class_by_key_plural)
    reform_entity_class_by_symbol = {
        entity_class.symbol: entity_class
        for entity_class in reform_entity_class_by_key_plural.itervalues()
        }
    reform_label = label
    reform_legislation_json = legislation_json
    reform_name = name
    reform_reference = reference

    class SimpleReform(Reform):
        entity_class_by_key_plural = reform_entity_class_by_key_plural
        label = reform_label
        legislation_json = reform_legislation_json
        name = reform_name
        reference = reform_reference

        formula = staticmethod(formulas.make_reference_formula_decorator(
            entity_class_by_symbol = reform_entity_class_by_symbol,
            update = True,
            ))

        @classmethod
        def input_variable(cls, entity_class = None, **kwargs):
            # Ensure that entity_class belongs to reform (instead of reference tax-benefit system).
            entity_class = cls.entity_class_by_key_plural[entity_class.key_plural]
            assert 'update' not in kwargs
            kwargs['update'] = True
            return columns.reference_input_variable(entity_class = entity_class, **kwargs)

    return SimpleReform


# TODO Delete this helper when it is no more used.
def replace_simple_formula_column_function(column, function):
    reform_column = clone_column(column)
    formula_class = column.formula_class
    reform_formula_class = type(
        u'reform_{}'.format(column.name).encode('utf-8'),
        (formula_class, ),
        {'function': staticmethod(function)},
        )
    reform_column.formula_class = reform_formula_class
    return reform_column


def update_legislation(legislation_json, path, period = None, value = None, start = None, stop = None):
    """
    Update legislation JSON with a value defined for a specific couple of period defined by
    its start and stop instant or a period object.

    This function does not modify input parameters.
    """
    assert value is not None
    if period is not None:
        start = period.start
        stop = period.stop

    def build_node(root_node, path_index):
        if isinstance(root_node, collections.Sequence):
            return [
                build_node(node, path_index + 1) if path[path_index] == index else node
                for index, node in enumerate(root_node)
                ]
        elif isinstance(root_node, collections.Mapping):
            return collections.OrderedDict((
                (
                    key,
                    (
                        updated_legislation_items(node, start, stop, value)
                        if path_index == len(path) - 1
                        else build_node(node, path_index + 1)
                        )
                    if path[path_index] == key
                    else node
                    )
                for key, node in root_node.iteritems()
                ))
        else:
            raise ValueError(u'Unexpected type for node: {!r}'.format(root_node))

    updated_legislation = build_node(legislation_json, 0)
    return updated_legislation


def updated_legislation_items(items, start_instant, stop_instant, value):
    """
    Iterates items (a dict with start, stop, value key) and returns new items sorted by start date,
    according to these rules:
    * if the period matches no existing item, the new item is yielded as-is
    * if the period strictly overlaps another one, the new item is yielded as-is
    * if the period non-strictly overlaps another one, the existing item is partitioned, the period in common removed,
      the new item is yielded as-is and the parts of the existing item are yielded
    """
    assert isinstance(items, collections.Sequence)
    new_items = []
    new_item = collections.OrderedDict((
        ('start', start_instant),
        ('stop', stop_instant),
        ('value', value),
        ))
    new_item_start = start_instant
    new_item_stop = stop_instant
    inserted = False
    for item in items:
        item_start = periods.instant(item['start'])
        item_stop = periods.instant(item['stop'])
        if item_stop < new_item_start or item_start > new_item_stop:  # non-overlapping items are kept: add and skip
            new_items.append(
                collections.OrderedDict((
                    ('start', item['start']),
                    ('stop', item['stop']),
                    ('value', item['value']),
                    ))
                )
            continue

        if item_stop == new_item_stop and item_start == new_item_start:  # exact matching: replace
            if not inserted:
                new_items.append(
                    collections.OrderedDict((
                        ('start', str(new_item_start)),
                        ('stop', str(new_item_stop)),
                        ('value', new_item['value']),
                        ))
                    )
                inserted = True
            continue

        if item_start < new_item_start and item_stop <= new_item_stop:
            # left edge overlapping are corrected and new_item inserted
            new_items.append(
                collections.OrderedDict((
                    ('start', item['start']),
                    ('stop', str(new_item_start.offset(-1, 'day'))),
                    ('value', item['value']),
                    ))
                )
            if not inserted:
                new_items.append(
                    collections.OrderedDict((
                        ('start', str(new_item_start)),
                        ('stop', str(new_item_stop)),
                        ('value', new_item['value']),
                        ))
                    )
                inserted = True

        if item_start < new_item_start and item_stop > new_item_stop:
            # new_item contained in item: divide, shrink left, insert, new, shrink right
            new_items.append(
                collections.OrderedDict((
                    ('start', item['start']),
                    ('stop', str(new_item_start.offset(-1, 'day'))),
                    ('value', item['value']),
                    ))
                )
            if not inserted:
                new_items.append(
                    collections.OrderedDict((
                        ('start', str(new_item_start)),
                        ('stop', str(new_item_stop)),
                        ('value', new_item['value']),
                        ))
                    )
                inserted = True

            new_items.append(
                collections.OrderedDict((
                    ('start', str(new_item_stop.offset(+1, 'day'))),
                    ('stop', item['stop']),
                    ('value', item['value']),
                    ))
                )
        if item_start >= new_item_start and item_stop < new_item_stop:
            # right edge overlapping are corrected
            if not inserted:
                new_items.append(
                    collections.OrderedDict((
                        ('start', str(new_item_start)),
                        ('stop', str(new_item_stop)),
                        ('value', new_item['value']),
                        ))
                    )
                inserted = True

            new_items.append(
                collections.OrderedDict((
                    ('start', str(new_item_stop.offset(+1, 'day'))),
                    ('stop', item['stop']),
                    ('value', item['value']),
                    ))
                )
        if item_start >= new_item_start and item_stop <= new_item_stop:
            # drop those
            continue

    return sorted(new_items, key = lambda item: item['start'])
