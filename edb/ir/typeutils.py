#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2015-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from __future__ import annotations

import typing

from edb.edgeql import qltypes

from edb.schema import abc as s_abc
from edb.schema import modules as s_mod
from edb.schema import objtypes as s_objtypes
from edb.schema import pointers as s_pointers
from edb.schema import pseudo as s_pseudo
from edb.schema import types as s_types
from edb.schema import utils as s_utils

from . import ast as irast


def is_scalar(typeref: irast.TypeRef) -> bool:
    return typeref.is_scalar


def is_object(typeref: irast.TypeRef) -> bool:
    return (
        not is_scalar(typeref)
        and not is_collection(typeref)
        and not is_generic(typeref)
    )


def is_view(typeref: irast.TypeRef) -> bool:
    return typeref.is_view


def is_collection(typeref: irast.TypeRef) -> bool:
    return bool(typeref.collection)


def is_array(typeref: irast.TypeRef) -> bool:
    return typeref.collection == s_types.Array.schema_name


def is_tuple(typeref: irast.TypeRef) -> bool:
    return typeref.collection == s_types.Tuple.schema_name


def is_any(typeref: irast.TypeRef) -> bool:
    return isinstance(typeref, irast.AnyTypeRef)


def is_anytuple(typeref: irast.TypeRef) -> bool:
    return isinstance(typeref, irast.AnyTupleRef)


def is_generic(typeref: irast.TypeRef) -> bool:
    if is_collection(typeref):
        return any(is_generic(st) for st in typeref.subtypes)
    else:
        return is_any(typeref) or is_anytuple(typeref)


def is_abstract(typeref: irast.TypeRef) -> bool:
    return typeref.is_abstract


def type_to_typeref(schema, t: s_types.Type, *,
                    _name=None, typename=None) -> irast.TypeRef:

    if t.is_anytuple():
        result = irast.AnyTupleRef(
            id=t.id,
            name_hint=typename or t.get_name(schema),
        )
    elif t.is_any():
        result = irast.AnyTypeRef(
            id=t.id,
            name_hint=typename or t.get_name(schema),
        )
    elif not isinstance(t, s_abc.Collection):
        if t.get_is_virtual(schema):
            children = frozenset(
                type_to_typeref(schema, c) for c in t.children(schema)
            )
        else:
            children = frozenset()

        material_type = t.material_type(schema)
        if material_type is not t:
            material_typeref = type_to_typeref(schema, material_type)
        else:
            material_typeref = None

        if (material_type.is_scalar()
                and not material_type.get_is_abstract(schema)):
            base_type = material_type.get_topmost_concrete_base(schema)
            if base_type is material_type:
                base_typeref = None
            else:
                base_typeref = type_to_typeref(schema, base_type)
        else:
            base_typeref = None

        if typename is not None:
            name = typename
        else:
            name = t.get_name(schema)
        module = schema.get_global(s_mod.Module, name.module)

        if children:
            common_parent = s_utils.get_class_nearest_common_ancestor(
                schema, t.children(schema))
            common_parent_ref = type_to_typeref(schema, common_parent)
        else:
            common_parent_ref = None

        result = irast.TypeRef(
            id=t.id,
            module_id=module.id,
            name_hint=name,
            material_type=material_typeref,
            base_type=base_typeref,
            children=children,
            common_parent=common_parent_ref,
            element_name=_name,
            is_scalar=t.is_scalar(),
            is_abstract=t.get_is_abstract(schema),
            is_view=t.is_view(schema),
        )
    elif isinstance(t, s_abc.Tuple) and t.named:
        result = irast.TypeRef(
            id=t.id,
            name_hint=typename or t.get_name(schema),
            element_name=_name,
            collection=t.schema_name,
            subtypes=tuple(
                type_to_typeref(schema, st, _name=sn)
                for sn, st in t.iter_subtypes(schema)
            )
        )
    else:
        result = irast.TypeRef(
            id=t.id,
            name_hint=typename or t.get_name(schema),
            element_name=_name,
            collection=t.schema_name,
            subtypes=tuple(
                type_to_typeref(schema, st)
                for st in t.get_subtypes(schema)
            )
        )

    return result


def ir_typeref_to_type(schema, typeref: irast.TypeRef) -> s_types.Type:
    if is_anytuple(typeref):
        return s_pseudo.AnyTuple.instance

    elif is_any(typeref):
        return s_pseudo.Any.instance

    elif is_tuple(typeref):
        named = False
        subtypes = {}
        for si, st in enumerate(typeref.subtypes):
            if st.element_name:
                named = True
                type_name = st.element_name
            else:
                type_name = str(si)

            subtypes[type_name] = ir_typeref_to_type(schema, st)

        return s_types.Tuple.from_subtypes(
            schema, subtypes, {'named': named})

    elif is_array(typeref):
        subtypes = []
        for st in typeref.subtypes:
            subtypes.append(ir_typeref_to_type(schema, st))

        return s_types.Array.from_subtypes(schema, subtypes)

    else:
        return schema.get_by_id(typeref.id)


def ptrref_from_ptrcls(
        *,
        source_ref: irast.TypeRef,
        target_ref: irast.TypeRef,
        ptrcls: s_pointers.PointerLike,
        direction: s_pointers.PointerDirection,
        parent_ptr: typing.Optional[irast.PointerRef]=None,
        schema) -> irast.BasePointerRef:

    kwargs = {}

    if ptrcls.is_tuple_indirection():
        ircls = irast.TupleIndirectionPointerRef
    elif ptrcls.is_type_indirection():
        ircls = irast.TypeIndirectionPointerRef
        kwargs['optional'] = ptrcls.is_optional()
        kwargs['ancestral'] = ptrcls.is_ancestral()
    else:
        ircls = irast.PointerRef
        kwargs['id'] = ptrcls.id
        name = ptrcls.get_name(schema)
        kwargs['module_id'] = schema.get_global(
            s_mod.Module, name.module).id

    if direction is s_pointers.PointerDirection.Inbound:
        out_source = target_ref
        out_target = source_ref
    else:
        out_source = source_ref
        out_target = target_ref

    out_cardinality = ptrcls.get_cardinality(schema)
    if out_cardinality is None:
        # The cardinality is not yet known.
        dir_cardinality = None
    elif ptrcls.singular(schema, direction):
        dir_cardinality = qltypes.Cardinality.ONE
    else:
        dir_cardinality = qltypes.Cardinality.MANY

    material_ptrcls = ptrcls.material_type(schema)
    if material_ptrcls is not None and material_ptrcls is not ptrcls:
        material_ptr = ptrref_from_ptrcls(
            source_ref=source_ref,
            target_ref=target_ref,
            ptrcls=material_ptrcls,
            direction=direction,
            parent_ptr=parent_ptr,
            schema=schema)
    else:
        material_ptr = None

    if ptrcls.get_derived_from(schema) is not None:
        derived_ptrcls = ptrcls.get_nearest_non_derived_parent(schema)
        derived_from_ptr = ptrref_from_ptrcls(
            source_ref=source_ref,
            target_ref=target_ref,
            ptrcls=derived_ptrcls,
            direction=direction,
            parent_ptr=parent_ptr,
            schema=schema)
    else:
        derived_from_ptr = None

    descendants = set()

    source = ptrcls.get_source(schema)
    if isinstance(source, s_objtypes.ObjectType):
        ptrs = {material_ptrcls}
        ptrname = ptrcls.get_shortname(schema).name
        for descendant in source.descendants(schema):
            ptr = descendant.getptr(schema, ptrname)
            if ptr is not None:
                desc_material_ptr = ptr.material_type(schema)
                if desc_material_ptr not in ptrs:
                    ptrs.add(desc_material_ptr)
                    descendants.add(
                        ptrref_from_ptrcls(
                            source_ref=source_ref,
                            target_ref=target_ref,
                            ptrcls=desc_material_ptr,
                            direction=direction,
                            parent_ptr=parent_ptr,
                            schema=schema,
                        )
                    )

    kwargs.update(dict(
        dir_source=source_ref,
        dir_target=target_ref,
        out_source=out_source,
        out_target=out_target,
        name=ptrcls.get_name(schema),
        shortname=ptrcls.get_shortname(schema),
        direction=direction,
        parent_ptr=parent_ptr,
        material_ptr=material_ptr,
        derived_from_ptr=derived_from_ptr,
        descendants=descendants,
        has_properties=ptrcls.has_user_defined_properties(schema),
        required=ptrcls.get_required(schema),
        dir_cardinality=dir_cardinality,
        out_cardinality=out_cardinality,
    ))

    return ircls(**kwargs)


def ptrcls_from_ptrref(
        ptrref: irast.BasePointerRef, *,
        schema) -> s_pointers.PointerLike:

    if isinstance(ptrref, irast.TupleIndirectionPointerRef):
        ptrcls = irast.TupleIndirectionLink(
            ptrref.name.name
        )
    elif isinstance(ptrref, irast.TypeIndirectionPointerRef):
        ptrcls = irast.TypeIndirectionLink(
            source=schema.get_by_id(ptrref.out_source.id),
            target=schema.get_by_id(ptrref.out_target.id),
            optional=ptrref.optional,
            ancestral=ptrref.ancestral,
            cardinality=ptrref.out_cardinality,
        )
    else:
        ptrcls = schema.get_by_id(ptrref.id)

    return ptrcls


def is_id_ptrref(
        ptrref: irast.BasePointerRef):
    return ptrref.shortname == 'std::id'


def is_inbound_ptrref(
        ptrref: irast.BasePointerRef):
    return ptrref.direction is s_pointers.PointerDirection.Inbound


def is_computable_ptrref(
        ptrref: irast.BasePointerRef):
    return ptrref.derived_from_ptr is not None
