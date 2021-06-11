import logging
import warnings

from osgeo import ogr


class OGRDBReader(object):
    """Read features from PostGIS database via OGR."""

    def _get_layer_fields(layer):
        featureDefinition = layer.GetLayerDefn()
        fieldNames = []
        fieldCount = featureDefinition.GetFieldCount()
        for j in range(fieldCount):
            fieldNames.append(featureDefinition.GetFieldDefn(j).GetNameRef())
        return fieldNames

    def __init__(self, dbname, dbport, dbuser, dbpass=None, dbhost="localhost"):
        super(OGRDBReader, self).__init__()
        self.dbname = dbname
        self.dbport = dbport
        self.dbuser = dbuser
        self.dbpass = dbpass
        self.dbhost = dbhost

        self.conn_str = (
            f"PG: user={self.dbuser} port={self.dbport} "
            f"password={self.dbpass} host={self.dbhost} "
            f"dbname={self.dbname}"
        )
        logging.debug(f"Opening PostGIS DB connection: {self.conn_str}")
        self.data = ogr.Open(self.conn_str, True)

    def get_layers(self):
        """Return available layers from db connection."""
        if self.data.GetLayerCount() < 1:
            raise ValueError("No layers found.")

        return [
            _lobj.GetName()
            for _lobj in [
                self.data.GetLayer(iLayer=_lidx)
                for _lidx in range(self.data.GetLayerCount())
            ]
        ]

    def get_layer_epsg(self, layer):
        _l = self.data.GetLayerByName(layer)
        return _l.GetSpatialRef().GetAttrValue("AUTHORITY", 1)

    def get_num_features(self, layer):
        _l = self.data.GetLayerByName(layer)
        return _l.GetFeatureCount()

    def get_feature_by_id(self, layer, id, id_field):
        _q = f"SELECT * from {layer} WHERE {layer}.{id_field} = {id}"
        _r = self.data.ExecuteSQL(_q)
        if len(_r) > 1:
            warnings.warn(
                f"More than one ID match for {id_field}:{id} (layer: {layer})"
            )
        return _r.GetNextFeature()

    def get_all_ids_for_layer(self, layer, id_fieldname="osm_id"):
        """
        Retrieves all unique values of `id_fieldname` within `layer`.
        """
        id_query = f"SELECT distinct {id_fieldname} FROM {layer}"

        logging.debug(f"Executing SQL: {id_query}")
        queryLayer = self.data.ExecuteSQL(id_query)
        idlist = []

        _id = queryLayer.GetNextFeature()
        while _id:
            idlist.append(_id.GetFieldAsString(0))
            _id = queryLayer.GetNextFeature()

        return idlist

    def intersections(
        self,
        new_layer,
        intersecting_layer,
        new_geometry_field="geometry",
        intersecting_geometry_field="geometry",
        intersecting_id_field="osm_id",
        ids=False,
        distance_buffer=5,
    ):
        """
        Retrieves intersections between new_layer and intersecting_layer.

        Actually returns the nearest points on new_layer features that are within
        <distance_buffer> from features in intersecting_geometry_field

        if ids = True, optionally returns a list of feature IDs from the intersecting layer`
        that represent the intersecting features in intersecting_layer
        with intersections to features in new_layer.

        returns ogr.Layer
        """

        # get geometries for all close linestrings
        intersection_query = (
            "SELECT distinct intersection FROM ("
            "	SELECT                                                    "
            "	   ST_ClosestPoint(n.{new_geometry_field}, o.{intersecting_geometry_field}) as intersection,"
            "      n.{new_geometry_field} as ngeom                        "
            "	FROM                                                      "
            "	   {new_layer} AS n                                       "
            "	RIGHT JOIN {intersecting_layer} AS o                      "
            "   ON not st_equals(n.geometry, o.geometry) "
            "	AND st_dwithin(n.geometry, o.geometry, {distance_buffer:.9f})"
            ") isects "
            "WHERE isects.ngeom is not NULL                                 "
        )

        # get ids for all intersecting features in intersecting_layer
        id_query = (
            "SELECT distinct o.{intersecting_id_field} FROM "
            "{intersecting_layer} o "
            "inner join {new_layer} n "
            "on st_dwithin(n.{new_geometry_field}, o.{intersecting_geometry_field}, {distance_buffer:.5f}) "
        )

        this_intersection_query = intersection_query.format(
            new_layer=new_layer,
            intersecting_layer=intersecting_layer,
            new_geometry_field=new_geometry_field,
            intersecting_geometry_field=intersecting_geometry_field,
            distance_buffer=distance_buffer,
        )
        logging.debug(f"Executing SQL: {this_intersection_query}")
        queryLayer = self.data.ExecuteSQL(this_intersection_query)

        # extract ids from db query
        idlist = None
        if ids:
            idlist = []
            this_id_query = id_query.format(
                new_layer=new_layer,
                intersecting_layer=intersecting_layer,
                intersecting_id_field=intersecting_id_field,
                new_geometry_field=new_geometry_field,
                intersecting_geometry_field=intersecting_geometry_field,
                distance_buffer=distance_buffer,
            )
            # this is a hack - using ogr for this SQL but there's
            # no geometries being returned.
            # cleaner would be psycopg2 but we already have an
            # open db connection via OGR
            logging.debug(f"Executing SQL: {this_id_query}")

            idLayer = self.data.ExecuteSQL(this_id_query)
            _id = idLayer.GetNextFeature()
            while _id:
                idlist.append(_id.GetFieldAsString(0))
                _id = idLayer.GetNextFeature()

        if idlist:
            return queryLayer, idlist
        else:
            return queryLayer

    def get_layer_fields(self, layer):
        """Get field names from layer"""
        layer = self.data.GetLayerByName(layer)
        return OGRDBReader._get_layer_fields(layer)

    def get_layer_iter(self, layer):
        """Return generator over features in layer"""
        l = self.data.GetLayerByName(layer)
        f = l.GetNextFeature()
        while f:
            yield f
            f = l.GetNextFeature()
