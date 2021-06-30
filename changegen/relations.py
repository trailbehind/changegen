import logging
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
into a Relation must contain a Tag with a Key that begins with a user-specifiable 
prefix and a Value that represents the ID of the Relation that the object should be
inserted into. 

The default Tag Key that is used is `_member_of`. (To use another, pass it as
the `relation_tag_prefix` argument to `get_modified_relations_for_object`). 

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

RELATIONS_DB: Dict[str, Relation] = {}
MODIFIED_RELATIONS: Set[str] = set()


def _reset():
    # Used for tests currently.
    global RELATIONS_DB
    global MODIFIED_RELATIONS

    RELATIONS_DB = {}
    MODIFIED_RELATIONS = set()


def get_modified_relations():
    return [RELATIONS_DB[_r] for _r in MODIFIED_RELATIONS]


def modify_relations_with_object(
    osm_object: Union[Relation, Node, Way], relation_tag_prefix: str = "_member_of_"
) -> List[Relation]:
    """

    This function interrogates `osm_object` for Tags whose
    keys begin with `relation_tag_prefix`. For all keys that begin with
    that prefix, the function searches a database of relations using the values
    of those tags as the relation ID. For all matching relations
    we add a RelationMember to the relation representing `osm_object`
    and update the database.

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

    # these are global because we need to update them
    # with additions to Relations. Seperate
    # invocations need access to the updates, so it
    # has to be global. I don't love it but
    # I think that's easier than having
    # clients maintain state themselves?
    global RELATIONS_DB
    global MODIFIED_RELATIONS

    relations_in_db = 0
    try:
        relations_in_db = len(RELATIONS_DB.keys())
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
    relation_ids = [
        tag.value for tag in osm_object.tags if tag.key.startswith(relation_tag_prefix)
    ]

    # update each relation with osm_object.
    for relation in relation_ids:
        existing_relation = None
        try:
            existing_relation = RELATIONS_DB[relation]
        except KeyError:
            logging.debug(
                f"Skipping modifying relation {relation} with object {osm_object.id} because it does not exist in database."
            )
            continue

        # create a new RelationMember containing the new object
        objectMember = RelationMember(
            ref=osm_object.id,
            type=type(
                osm_object
            ).__name__.lower(),  # Node --> 'node', Way --> 'way', 'Relation' -> 'relation',
            role="",
        )

        # create a new relation containing the new member.
        new_relation = Relation(
            id=existing_relation.id,
            version=existing_relation.version,
            members=existing_relation.members + [objectMember],
            tags=existing_relation.tags,
        )

        # update relations DB
        RELATIONS_DB[relation] = new_relation
        # add modified relation to set of modified relations
        MODIFIED_RELATIONS.add(relation)


def get_relations(ids: List[str], osm_filepath: str) -> Dict[str, Relation]:
    """
    Creates an internal mapping of OSM IDs to Relation objects for each relation
    in the OSM file that's specified by `osm_filepath`
    that is specified in `ids`.

    """

    # we need to update the module-level
    # variable here, so we ensure that we're
    # using global scope for this variable.
    global RELATIONS_DB

    class _RelationReader(osmium.SimpleHandler):
        def __init__(self, ids):
            super(_RelationReader, self).__init__()
            self.ids = set(ids)
            self.relations: Dict[str, Relation] = {}

        def _convert_members(
            self, members: osmium.osm.RelationMemberList
        ) -> List[RelationMember]:
            memberList: List[RelationMember] = []
            for member in members:
                memberList.append(
                    RelationMember(ref=member.ref, type=member.type, role=member.role)
                )
            return memberList

        def _convert_tags(self, tags: osmium.osm.TagList) -> List[Tag]:
            tagList: List[Tag] = []
            for tag in tags:
                tagList.append(Tag(key=tag.k, value=tag.v))
            return tagList

        def relation(self, r):
            if str(r.id) in self.ids:
                self.relations[str(r.id)] = Relation(
                    id=str(r.id),
                    version=2,
                    members=self._convert_members(r.members),
                    tags=self._convert_tags(r.tags),
                )

    _reader = _RelationReader(ids)
    _reader.apply_file(osm_filepath)

    # set the global variable
    RELATIONS_DB = _reader.relations
