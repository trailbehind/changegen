import logging
from itertools import chain
from typing import Dict
from typing import List
from typing import Set
from typing import Union

import osmium

from .changewriter import Node
from .changewriter import Relation
from .changewriter import RelationMember
from .changewriter import Tag
from .changewriter import Way

# whether to use "way" or "w" (etc) for
# the "type" field of RelationMembers.
LONG_RELATION_MEMBER_TYPE = True

"""

Relation Management
====================

This module provides support for modifying Relations. It supports a few use-cases. 

1. A <create> tag will be created, and some objects within it need to be 
   added to relations that already exist. In this case, <modify> tags are 
   created that modify the Relations in question. 
2. more later probably

It is important to note that this module is STATEFUL. It should probably be a class. 
If you need to clear the relations DB and modified relations list, you can use _reset().

Insertion in to Existing Relations
-----------------------------------

In order to insert an object into an existing relation a particular schema 
of the input data is required. In particular, any object that is to be inserted
into a Relation must contain a Tag with a user-specifiable Key
and a Value that represents a comma-separated list of the IDs of 
Relations that the object should be inserted into. 

The default Tag Key that is used is `_member_of`. (To use another, pass it as
the `relation_tag` argument to `get_modified_relations_for_object`). 

`modify_relations_with_object` is responsible for modifying a local
database of Relations with by objects to them, as specified in the object itself. 

Before running `modify_relations_with_object`, a local database of
Relations must be generated. This is done by providing a list of 
Relation IDs to `get_relations`. This is an expensive operation, 
so should be done as infrequently as possible (likely just once).

The list of IDs provided to `get_relations` should represent all relations
that need to be inserted into. 

After processing objects is complete, call get_modified_relations 
to obtain a list of modified relations that can then be used to create
<modify> tags in a changefile. 

"""


class RelationUpdater(object):
    def __init__(self):
        self.RELATIONS_DB: Dict[str, Relation] = {}
        self.MODIFIED_RELATIONS: Set[str] = set()

    def _reset(self):
        # Used for tests currently.

        self.RELATIONS_DB = {}
        self.MODIFIED_RELATIONS = set()

    def get_modified_relations(self):
        return [self.RELATIONS_DB[_r] for _r in self.MODIFIED_RELATIONS]

    def modify_relations_with_object(
        self,
        osm_object: Union[Relation, Node, Way],
        relation_tag: str = "_member_of",
        at_id: str = None,
    ) -> List[Relation]:
        """

        This function interrogates `osm_object` for a Tag whose
        key begins with `relation_tag`. If a matching key is found that begins with
        that prefix, the function:
        * searches a database of relations using the comma-separated
        values in the Tag as the relation IDs. 
        * For all matching relations we add a RelationMember to the relation representing \
            `osm_object` and update the database.
        * if ``at_id`` is ``None``, we add the ``RelationMember`` to the end of the relation. 
        * if ``at_id`` has a value that matches an OSM ID that currently exists \
            in the relation, we add the ``RelationMember`` that represents \ 
            ``osm_object`` _after_ that index. 


        This function is not a "pure" function -- it modifies underlying state
        without returning anything.

        Relations that are not found in RELATIONS_DB are skipped.

        NOTE that this function does not support Roles.

        NOTE that this function requires that `get_relations` is invoked
        first. We need to read data from the OSM file only once. You must ensure
        that the invocation of `get_relations` obtains Relation objects
        for all Relations that are referred-to by Tags in the OSM objects to be
        inserted.



        """

        relations_in_db = 0
        try:
            relations_in_db = len(self.RELATIONS_DB.keys())
        except NameError:
            raise Exception("No Relations Database exists. Did you run get_relations?")

        if relations_in_db == 0:
            raise RuntimeWarning(
                (
                    "There are no relations in the relations database. "
                    "No objects will be added to any relations. "
                )
            )

        # search for matching tags that represent relation IDs
        relation_ids = chain.from_iterable(
            [
                tag.value.split(",")
                for tag in osm_object.tags
                if tag.key.startswith(relation_tag)
            ]
        )
        # update each relation with osm_object.
        for relation in relation_ids:
            existing_relation = None
            try:
                existing_relation = self.RELATIONS_DB[relation]
            except KeyError:
                logging.debug(
                    f"Skipping modifying relation {relation} with object {osm_object.id} because it does not exist in database."
                )
                continue

            # create a new RelationMember containing the new object
            rm_type = type(osm_object).__name__.lower()
            if not LONG_RELATION_MEMBER_TYPE:
                rm_type = rm_type[0]
            objectMember = RelationMember(
                ref=osm_object.id,
                type=rm_type,
                role="",
            )

            # Determine where to insert the new object in the list
            # of relation members. If at_id is provided, we look
            # for the index of that ID in the members list and insert
            # the new object at that index. If it's None, we insert it
            # at the end.
            relation_members = existing_relation.members
            insertion_index = len(relation_members)
            if at_id:
                # get index of RelationMember whose id equals at_id
                try:
                    insertion_index = next(
                        idx
                        for idx, rm in enumerate(relation_members)
                        if (lambda x: x.ref == at_id)(rm)
                    )
                except StopIteration:
                    logging.debug(
                        f"Could not find ID {at_id} in list of members of relation {existing_relation.id}."
                    )

            relation_members.insert(insertion_index, objectMember)

            # create a new relation containing the new member.
            new_relation = Relation(
                id=existing_relation.id,
                version=existing_relation.version,
                members=relation_members,
                tags=existing_relation.tags,
            )

            # update relations DB
            self.RELATIONS_DB.update({relation: new_relation})
            # add modified relation to set of modified relations
            self.MODIFIED_RELATIONS.add(relation)

    def get_relations(self, ids: List[str], osm_filepath: str) -> Dict[str, Relation]:
        """
        Creates an internal mapping of OSM IDs to Relation objects for each relation
        in the OSM file that's specified by `osm_filepath`
        that is specified in `ids`.

        """

        class _RelationReader(osmium.SimpleHandler):
            def __init__(__self, ids):
                super(_RelationReader, __self).__init__()
                __self.ids = set(ids)
                __self.relations: Dict[str, Relation] = {}

            def _convert_members(
                __self, members: osmium.osm.RelationMemberList
            ) -> List[RelationMember]:
                memberList: List[RelationMember] = []
                for member in members:
                    _type = member.type
                    if LONG_RELATION_MEMBER_TYPE:
                        _type = {
                            "w": "way",
                            "n": "node",
                            "r": "relation",
                        }[member.type]
                    memberList.append(
                        RelationMember(ref=member.ref, type=_type, role=member.role)
                    )
                return memberList

            def _convert_tags(__self, tags: osmium.osm.TagList) -> List[Tag]:
                tagList: List[Tag] = []
                for tag in tags:
                    tagList.append(Tag(key=tag.k, value=tag.v))
                return tagList

            def relation(__self, r):
                if str(r.id) in __self.ids:
                    __self.relations[str(r.id)] = Relation(
                        id=str(r.id),
                        version=2,
                        members=__self._convert_members(r.members),
                        tags=__self._convert_tags(r.tags),
                    )

        _reader = _RelationReader(ids)
        _reader.apply_file(osm_filepath)

        self.RELATIONS_DB = _reader.relations
