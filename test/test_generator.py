import os
import socket
import tempfile
import unittest

from osgeo import gdal
from osgeo import ogr

gdal.UseExceptions()

from lxml import etree

import shapely.wkt as wkt
import shapely.geometry as sg

from itertools import chain
from collections import Counter

from changegen import db
from changegen import generator
from changegen.changewriter import Node, Way

DBNAME = os.environ.get("DBNAME", "test")
DBUSER = os.environ.get("DBUSER", "postgres")
DBPORT = os.environ.get("DBPORT", "5432")
DBHOST = os.environ.get("DBHOST", "test-db")

"""These tests require a Postgres database to be running."""

# check if there's a db running @ specified port
testsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
is_db = testsock.connect_ex((DBHOST, int(DBPORT))) == 0


@unittest.skipUnless(is_db, f"DB not running at {DBHOST}:{DBPORT}, skipping test")
class TestGenerator(unittest.TestCase):
    def test_nodelist_generator(self):
        """Ensure that the node generator generates a
        number of nodes equal to the number of intersections.
        """
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER, dbhost=DBHOST)
        isections = _l.intersections("new_ways", "original_ways")
        nodes = generator._nodes_for_intersections(isections, iter(range(100000)))
        self.assertEqual(len(nodes), len(isections))

    def test_rtree_generator(self):
        """Ensures that the rtree can be build with intersection db.
        We test this by ensuring that the rtree can return the nearest
        point to another point."""
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER, dbhost=DBHOST)
        nds, rt, _ids = generator._generate_intersection_db(
            "new_ways", ["original_ways"], _l, iter(range(100000))
        )
        nearest_seattle = [
            n.object
            for n in rt.nearest((-122.33, 47.60, -122.33, 47.60), 1, objects=True)
        ]
        self.assertTrue(len(nearest_seattle) == 1)

    def test_way_node_generator(self):
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER, dbhost=DBHOST)
        id_gen = iter(range(100000))
        nds, rt, _ids = generator._generate_intersection_db(
            "new_ways", ["original_ways"], _l, id_gen
        )

        # test with a line from trails_new that definitely intersects with osm_roads_trails (11/6/2020)
        newline = ogr.Open("./test/data/test_line.geojson")
        nl_layer = newline.GetLayer()
        feat = nl_layer.GetNextFeature()
        feat_geom = wkt.loads(feat.GetGeometryRef().ExportToWkt())

        # get expected node ID
        isection_node_id = list(rt.intersection(feat_geom.bounds))[0]
        # ensure that node id is present in the resulting Way
        ways, nodes = generator._generate_ways_and_nodes(feat_geom, id_gen, [], rt)
        self.assertIn(isection_node_id, ways[0].nds)

    def test_waysplitter(self):
        """Test splitting of 2000+ node linestring into
        intersecting smaller Ways"""
        idgen = iter(range(0, 5000))
        nds = [next(idgen) for _ in iter(range(0, 3000))]
        ways = generator._make_ways(nds, [], idgen, node_limit=2000)
        # ensure all nodes are represented
        allNodes = chain.from_iterable([w.nds for w in ways])
        self.assertEqual(sorted(list(set(allNodes))), list(range(0, 3000)))
        # ensure some nodes are duplicated (intersections). at least 5 here (3000/500)
        print(Counter(allNodes).most_common(5))
        self.assertTrue(
            all(map(lambda x: x > 1, [C[1] for C in Counter(allNodes).most_common(5)]))
        )

    def test_generate_changes_create_new_ways(self):
        """Test whether new ways generated from DB table are present in changefiles with intersections."""

        """
        These values come from a manual test creation process, 
        but yeah they're super arbitrary.
        """
        CORRECT_NUM_NEW_WAYS = 10
        CORRECT_NUM_INTERSECTING_WAYS = 4

        changefile_output = tempfile.NamedTemporaryFile(delete=False)

        generator.generate_changes(
            "new_ways",
            "original_ways",
            [],
            DBNAME,
            DBPORT,
            DBUSER,
            None,
            DBHOST,
            "test/data/osmdata.osm.pbf",
            changefile_output.name,
            self_intersections=True,
            compress=False,
        )
        with open(changefile_output.name, "r") as cf:
            doc = etree.parse(cf)
            create_counts = doc.xpath("count(//create/way)")
            self.assertEqual(create_counts, CORRECT_NUM_NEW_WAYS)
            modify_counts = doc.xpath("count(//modify/way)")
            self.assertEqual(modify_counts, CORRECT_NUM_INTERSECTING_WAYS)

        os.remove(changefile_output.name)

    def test_generate_changes_modify_existing_ways(self):
        """Test whether modified ways generated from the DB table are present in changefile."""

        """
        These values come from a manual test creation process, 
        but yeah they're super arbitrary.
        """

        CORRECT_NUM_MODIFIED_WAYS = 22

        changefile_output = tempfile.NamedTemporaryFile(delete=False)

        generator.generate_changes(
            "mod_ways",
            [],
            [],
            DBNAME,
            DBPORT,
            DBUSER,
            None,
            DBHOST,
            "test/data/osmdata.osm.pbf",
            changefile_output.name,
            self_intersections=False,
            compress=False,
            modify_only=True,
        )

        with open(changefile_output.name, "r") as cf:
            doc = etree.parse(cf)
            mod_counts = doc.xpath("count(//modify/way)")
            self.assertEqual(mod_counts, CORRECT_NUM_MODIFIED_WAYS)

        os.remove(changefile_output.name)

    def test_generate_changes_create_new_points(self):
        """Test whether points generated from the DB table are present in changefile."""

        """
        These values come from a manual test creation process, 
        but yeah they're super arbitrary.
        """
        CORRECT_NUM_NEW_POINTS = 213

        changefile_output = tempfile.NamedTemporaryFile(delete=False)

        generator.generate_changes(
            "new_points",
            [],
            [],
            DBNAME,
            DBPORT,
            DBUSER,
            None,
            DBHOST,
            "test/data/osmdata.osm.pbf",
            changefile_output.name,
            self_intersections=False,
            compress=False,
            modify_only=False,
        )

        with open(changefile_output.name, "r") as cf:
            doc = etree.parse(cf)
            new_counts = doc.xpath("count(//create/node)")
            self.assertEqual(new_counts, CORRECT_NUM_NEW_POINTS)

        os.remove(changefile_output.name)

    def test_generate_changes_modify_existing_points(self):
        """Test whether modified points generated from the DB table are present in changefile."""

        """
        These values come from a manual test creation process, 
        but yeah they're super arbitrary.
        """
        CORRECT_NUM_MOD_POINTS = 3

        changefile_output = tempfile.NamedTemporaryFile(delete=False)

        generator.generate_changes(
            "modified_points",
            [],
            [],
            DBNAME,
            DBPORT,
            DBUSER,
            None,
            DBHOST,
            "test/data/osmdata.osm.pbf",
            changefile_output.name,
            self_intersections=False,
            compress=False,
            modify_only=True,
        )

        with open(changefile_output.name, "r") as cf:
            doc = etree.parse(cf)
            mod_counts = doc.xpath("count(//modify/node)")
            self.assertEqual(mod_counts, CORRECT_NUM_MOD_POINTS)

        os.remove(changefile_output.name)

    #

    def test_point_insertion(self):
        """Ensure that point insertion calculation is accurate."""

        """Note that this test relies on original_ways to be
        present in the database and have an intersection with the linestring
        in the test_line.geojson file.
        """
        CORRECT_INSERTION_INDEX = 5

        newline = ogr.Open("./test/data/test_line_3857.geojson")
        nl_layer = newline.GetLayer()
        feat = nl_layer.GetNextFeature()
        feat_geom = wkt.loads(feat.GetGeometryRef().ExportToWkt())

        idx = generator._get_point_insertion_index(
            feat_geom, sg.Point(-13176331.8, 6216657.1)
        )

        self.assertEqual(idx, CORRECT_INSERTION_INDEX)
