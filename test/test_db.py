import socket
import unittest

from osgeo import gdal
from osgeo import ogr

gdal.UseExceptions()
from changegen import db

DBNAME = "conflate"
DBUSER = "postgres"
DBPORT = "15432"
DBHOST = "localhost"

"""These tests require a Postgres database to be running locally."""

# check if there's a db running @ specified port
testsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
is_db = testsock.connect_ex((DBHOST, int(DBPORT))) == 0


@unittest.skipUnless(is_db, f"DB not running at {DBHOST}:{DBPORT}, skipping test")
class TestDB(unittest.TestCase):
    def test_connect(self):
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        self.assertTrue(_l.data)

    def test_fail(self):
        """Ensure failure to connect to datasource with nonexistent_user"""
        _l = db.OGRDBReader(DBNAME, DBPORT, dbuser="nonexistent_user")
        self.assertEqual(_l.data, None)

    def test_get_layers(self):
        """Check that get_layers() returns a list."""
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        self.assertIsInstance(_l.get_layers(), list)

    def test_self_intersection(self):
        """Sanity-check on intersections
        such that there should always be at least 1
        intersection among a feature and it's source layer"""
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        layers = _l.get_layers()
        intersections = _l.intersections(layers[0], layers[0])
        isection = intersections.GetNextFeature()
        self.assertTrue(isection)

    def test_self_intersection_returns_intersection_point(self):
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        layers = _l.get_layers()
        intersections = _l.intersections(
            layers[0],
            layers[0],
        )
        ifeat = intersections.GetNextFeature()
        self.assertEqual(ifeat.GetGeometryRef().GetGeometryType(), ogr.wkbPoint)

    def test_id_return(self):
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        layers = _l.get_layers()
        intersections, ids = _l.intersections(
            "trails_new", "osm_roads_trails", ids=True
        )
        self.assertTrue(len(ids) > 0)

    def test_generator(self):
        """Test layer generator"""
        _l = db.OGRDBReader(DBNAME, DBPORT, DBUSER)
        layers = _l.get_layers()
        layer_iter = _l.get_layer_iter(layers[0])
        f1, f2 = next(layer_iter), next(layer_iter)
        self.assertTrue(f1 != None)
        self.assertIsInstance(f1, ogr.Feature)
        self.assertNotEqual(f1, f2)
