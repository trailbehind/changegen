import io
import os
import tempfile
import unittest
from gzip import GzipFile

from lxml import etree

from changegen import changewriter

test_tags = [
    changewriter.Tag("attribute", "value"),
    changewriter.Tag("attribute2", "value2"),
]
test_nodes = [
    changewriter.Node(id="-111", version="99", lat=90, lon=180, tags=test_tags),
    changewriter.Node(id="-112", version="99", lat=80, lon=170, tags=test_tags),
]
test_objects = [
    test_nodes[0],  # node
    changewriter.Way(
        id="-55", version="99", nds=[n.id for n in test_nodes], tags=test_tags
    ),
]


class TestWriter(unittest.TestCase):
    """Test OSMChangeWriter"""

    def test_modify_node(self):
        """Ensure a single modify node is written correctly"""
        xmloutput = tempfile.NamedTemporaryFile(delete=False)
        writer = changewriter.OSMChangeWriter(filename=xmloutput.name)
        objects_to_test = [test_objects[0]]  # just test node
        writer.add_modify(objects_to_test)
        writer.close()
        _of = open(xmloutput.name, "rb")
        parsed = etree.parse(_of)
        _of.close()
        parsedRoot = parsed.getroot()
        parsedElements = list(parsedRoot[0])
        parsedTags = parsed.xpath("/osmChange/modify/node/tag")

        self.assertTrue(parsedRoot[0].tag == "modify")
        self.assertTrue(parsedElements[0].tag == "node")
        self.assertTrue(len(parsedElements) == len(objects_to_test))
        self.assertTrue(
            set(parsedElements[0].keys()) == set(["id", "version", "lat", "lon"])
        )

        self.assertTrue(len(parsedTags) == len(test_objects[0].tags))
        xmloutput.close()
        os.remove(xmloutput.name)

    def test_modify_way(self):
        """Ensure a single modify way is written correctly"""
        xmloutput = tempfile.NamedTemporaryFile(delete=False)
        writer = changewriter.OSMChangeWriter(filename=xmloutput.name)
        objects_to_test = [test_objects[1]]  # just test way
        writer.add_modify(objects_to_test)
        writer.close()
        _of = open(xmloutput.name, "rb")
        parsed = etree.parse(_of)
        _of.close()
        parsedRoot = parsed.getroot()
        parsedElements = list(parsedRoot[0])
        parsedTags = parsed.xpath("/osmChange/modify/way/tag")

        self.assertTrue(parsedRoot[0].tag == "modify")
        self.assertTrue(parsedElements[0].tag == "way")
        self.assertTrue(len(parsedElements) == len(objects_to_test))
        self.assertTrue(set(parsedElements[0].keys()) == set(["id", "version"]))
        self.assertTrue(len(parsedTags) == len(test_objects[0].tags))

        xmloutput.close()
        os.remove(xmloutput.name)

    def test_create_node(self):
        """Ensure a single create node is written correctly"""
        xmloutput = tempfile.NamedTemporaryFile(delete=False)
        writer = changewriter.OSMChangeWriter(filename=xmloutput.name)
        objects_to_test = [test_objects[0]]  # just test node
        writer.add_create(objects_to_test)
        writer.close()
        _of = open(xmloutput.name, "rb")
        parsed = etree.parse(_of)
        _of.close()
        parsedRoot = parsed.getroot()
        parsedElements = list(parsedRoot[0])
        parsedTags = parsed.xpath("/osmChange/create/node/tag")

        self.assertTrue(parsedRoot[0].tag == "create")
        self.assertTrue(parsedElements[0].tag == "node")
        self.assertTrue(len(parsedElements) == len(objects_to_test))
        self.assertTrue(
            set(parsedElements[0].keys()) == set(["id", "version", "lat", "lon"])
        )
        self.assertTrue(len(parsedTags) == len(test_objects[0].tags))

        xmloutput.close()
        os.remove(xmloutput.name)

    def test_create_way(self):
        """Ensure a single create node is written correctly"""
        xmloutput = tempfile.NamedTemporaryFile(delete=False)
        writer = changewriter.OSMChangeWriter(filename=xmloutput.name)
        objects_to_test = [test_objects[1]]  # just test way
        writer.add_create(objects_to_test)
        writer.close()
        _of = open(xmloutput.name, "rb")
        parsed = etree.parse(_of)
        _of.close()
        parsedRoot = parsed.getroot()
        parsedElements = list(parsedRoot[0])
        parsedTags = parsed.xpath("/osmChange/create/way/tag")

        self.assertTrue(parsedRoot[0].tag == "create")
        self.assertTrue(parsedElements[0].tag == "way")
        self.assertTrue(set(parsedElements[0].keys()) == set(["id", "version"]))
        self.assertTrue(len(parsedElements) == len(objects_to_test))
        self.assertTrue(len(parsedTags) == len(test_objects[0].tags))

        xmloutput.close()
        os.remove(xmloutput.name)

    def test_modify_multiple(self):
        """Ensure a multiple modify nodes are written correctly"""

        xmloutput = tempfile.NamedTemporaryFile(delete=False)
        writer = changewriter.OSMChangeWriter(filename=xmloutput.name)
        objects_to_test = test_objects  # just test way
        writer.add_modify(objects_to_test)
        writer.close()
        _of = open(xmloutput.name, "rb")
        parsed = etree.parse(_of)
        _of.close()
        parsedRoot = parsed.getroot()
        parsedElements = list(parsedRoot[0])
        self.assertTrue(parsedRoot[0].tag == "modify")
        self.assertTrue(len(parsedElements) == len(objects_to_test))

        xmloutput.close()
        os.remove(xmloutput.name)

    def test_create_multiple(self):
        """Ensure a multiple modify nodes are written correctly"""

        xmloutput = tempfile.NamedTemporaryFile(delete=False)
        writer = changewriter.OSMChangeWriter(filename=xmloutput.name)
        objects_to_test = test_objects  # just test way
        writer.add_create(objects_to_test)
        writer.close()
        _of = open(xmloutput.name, "rb")
        parsed = etree.parse(_of)
        _of.close()
        parsedRoot = parsed.getroot()
        parsedElements = list(parsedRoot[0])
        self.assertTrue(parsedRoot[0].tag == "create")
        self.assertTrue(len(parsedElements) == len(objects_to_test))

        xmloutput.close()
        os.remove(xmloutput.name)

    def test_write_file(self):
        """Ensure that providing a filename to OSMChangeWriter produces a file"""
        with tempfile.NamedTemporaryFile(delete=False) as of:
            writer = changewriter.OSMChangeWriter(filename=of.name)
            objects_to_test = test_objects  # just test way
            writer.add_create(objects_to_test)
            writer.close()
            with open(of.name, "r") as f:
                f.seek(0)
                parsed = etree.parse(f)
                parsedRoot = parsed.getroot()
                parsedElements = list(parsedRoot[0])

                self.assertTrue(parsedRoot[0].tag == "create")
                self.assertTrue(len(parsedElements) == len(objects_to_test))
            of.close()

    def test_close(self):
        """Ensure close() function correctly adds osmChange tags"""
        with tempfile.NamedTemporaryFile(delete=False) as of:
            writer = changewriter.OSMChangeWriter(filename=of.name)
            objects_to_test = test_objects  # just test way
            writer.add_create(objects_to_test)
            writer.close()

            _of = open(of.name, "rb")
            parsed = etree.parse(_of)
            _of.close()
            parsedRoot = parsed.getroot()
            self.assertTrue(parsedRoot.tag == "osmChange")
            self.assertTrue(parsedRoot[0].tag == "create")
            of.close()

    def test_compression(self):
        """Test compression"""

        xmloutput = tempfile.NamedTemporaryFile(delete=False)

        writer = changewriter.OSMChangeWriter(filename=xmloutput.name, compress=True)
        objects_to_test = test_objects  # just test way
        writer.add_create(objects_to_test)
        writer.close()

        parsed = etree.parse(GzipFile(xmloutput.name, "r"))
        parsedRoot = parsed.getroot()
        self.assertTrue(parsedRoot.tag == "osmChange")
        xmloutput.close()
