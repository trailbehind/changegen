import unittest

from changegen import changewriter
from changegen import relations

test_relation_id = "4567"

test_relation_db = {
    test_relation_id: changewriter.Relation(
        id=test_relation_id,
        version="-1",
        members=[changewriter.RelationMember("-1", type="w", role="")],
        tags=changewriter.Tag(key="tagkey", value="tagvalue"),
    )
}

test_insertion_object = changewriter.Node(
    id="9999",
    version="-1",
    lat="0",
    lon="0",
    tags=[changewriter.Tag(key="_member_of_somerelation", value=test_relation_id)],
)

test_insertion_object_missing_relation = changewriter.Node(
    id="9999",
    version="-1",
    lat="0",
    lon="0",
    tags=[changewriter.Tag(key="_member_of_somerelation", value="-1")],
)


class TestRelations(unittest.TestCase):
    def test_add_node_to_relation(self):
        """Ensure that a Node gets added to a Relation properly."""
        relations._reset()
        ## we need to cheat and patch RELATIONS_DB with our mock
        ## because I don't want to test get_relations here.
        relations.RELATIONS_DB = test_relation_db

        relations.modify_relations_with_object(test_insertion_object)

        modified_relations = relations.get_modified_relations()

        self.assertEqual(len(modified_relations), 1)

    def test_proper_relation_member_formatting(self):
        """Ensure that the RelationMember that's added to the Relation is proper"""
        relations._reset()
        ## we need to cheat and patch RELATIONS_DB with our mock
        ## because I don't want to test get_relations here.
        relations.RELATIONS_DB = test_relation_db

        relations.modify_relations_with_object(test_insertion_object)

        modified_relations = relations.get_modified_relations()

        self.assertTrue(modified_relations[0].members[1].type == "n")
        self.assertTrue(
            modified_relations[0].members[1].ref == test_insertion_object.id
        )
        self.assertTrue(modified_relations[0].members[1].role == "")

    def test_relation_missing(self):
        relations._reset()

        relations.RELATIONS_DB = test_relation_db

        relations.modify_relations_with_object(test_insertion_object_missing_relation)

        modified_relations = relations.get_modified_relations()

        self.assertEqual(len(modified_relations), 0)
