import socket
import unittest

from osgeo import gdal
from osgeo import ogr

gdal.UseExceptions()

import shapely.wkt as wkt
import shapely.geometry as sg

from itertools import chain
from collections import Counter

from changegen import db
from changegen import generator
from changegen.changewriter import Node, Way

DBNAME = "conflate"
DBUSER = "postgres"
DBPORT = "15432"
DBHOST = "localhost"

"""These tests require a Postgres database to be running locally."""

# check if there's a db running @ specified port
testsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
is_db = testsock.connect_ex((DBHOST, int(DBPORT))) == 0


@unittest.skipUnless(is_db, f"DB not running at {DBHOST}:{DBPORT}, skipping test")
class TestGenerator(unittest.TestCase):
    def test_nodelist_generator(self):
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        isections = _l.intersections(
            "trails_new", "osm_roads_trails", intersection_types=["Point"]
        )
        nodes = generator._nodes_for_intersections(isections, iter(range(100000)))
        self.assertEqual(len(nodes), len(isections))

    def test_rtree_generator(self):
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        nds, rt, _ids = generator._generate_intersection_db(
            "trails_new", ["osm_roads_trails"], _l, iter(range(100000))
        )
        nearest_seattle = [
            n.object
            for n in rt.nearest((-122.33, 47.60, -122.33, 47.60), 1, objects=True)
        ]
        self.assertTrue(len(nearest_seattle) == 1)

    def test_way_node_generator(self):
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        id_gen = iter(range(100000))
        nds, rt, _ids = generator._generate_intersection_db(
            "trails_new", ["osm_roads_trails"], _l, id_gen
        )

        # test with a line from trails_new that definitely intersects with osm_roads_trails (11/6/2020)
        newline = ogr.Open("./test/data/new_trail_with_intersection.geojson")
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

    def test_modify_way(self):
        """Test modification of existing way, maintaining node"""

    #
    #
    # def test_intersection_handler(self):
    #     """Ensure that both new ways and existing ways share a node"""
    #
    #     """Note that this test relies on osm_roads_trails to be
    #     present in the database and have an intersection with the linestring
    #     in the newline_osmroadstrails.geojson file.
    #     """
    #
    #     newline = ogr.Open("./test/data/newline_osmroadstrails.geojson")
    #     nl_layer = newline.GetLayer()
    #     feat = nl_layer.GetNextFeature()
    #     feat_geom = wkt.loads(feat.GetGeometryRef().ExportToWkt())
    #
    #     _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
    #     isections = _l.intersections(feat, ["osm_roads_trails"])
    #
    #     nw, nn, mw = generator._handle_intersection(
    #         feat_geom, [], isections[0], iter(range(50000))
    #     )
    #
    #     nw_node_ids = set(chain.from_iterable([w.nds for w in nw]))
    #     mw_node_ids = set(chain.from_iterable([w.nds for w in mw]))
    #
    #     self.assertTrue(len(nw_node_ids.intersection(mw_node_ids)) > 0)
