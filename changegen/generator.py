import logging
import sys
from collections import Counter
from itertools import chain

import ogr
import osmium
import pyproj
import rtree
import shapely.geometry as sg
from numpy import argmax
from numpy import argsort
from numpy import cumsum
from numpy import zeros
from shapely import wkt
from shapely.ops import nearest_points
from shapely.ops import transform
from tqdm import tqdm

from .changewriter import Node
from .changewriter import OSMChangeWriter
from .changewriter import Relation
from .changewriter import RelationMember
from .changewriter import Tag
from .changewriter import Way
from .db import hstore_as_dict
from .db import OGRDBReader

WGS84 = pyproj.CRS("EPSG:4326")
WEBMERC = pyproj.CRS("EPSG:3857")
COORDINATE_PRECISION = 6
WAY_POINT_THRESHOLD = 1500


def _get_way_node_map(osm, way_idlist):
    """Returns a dictionary of osm_id : [node_ids]
    for all Ways specified with way_idlist
    from an osm.pbf file.
    """

    class _wayFilter(osmium.SimpleHandler):
        def __init__(self, ids):
            super(_wayFilter, self).__init__()
            self.ids = set(ids)
            self.node_map = {}

        def way(self, w):
            if str(w.id) in self.ids:
                self.node_map[str(w.id)] = [str(n.ref) for n in w.nodes]

    _filter = _wayFilter(way_idlist)
    _filter.apply_file(osm)
    return _filter.node_map


def _nodes_for_intersections(ilayer, idgen):
    """
    Produces a Node for each point in
    ilayer.

    ilayer is an ogr.Layer
    idgen is a generator/iterator yielding ids
    Returns a list.
    """

    if len(ilayer) == 0:
        return []

    ilayer_epsg = ilayer.GetSpatialRef().GetAttrValue("AUTHORITY", 1)
    ilayer_reproject = pyproj.Transformer.from_crs(
        pyproj.CRS(f"EPSG:{ilayer_epsg}"), WGS84, always_xy=True
    ).transform

    nodes = []
    _f = ilayer.GetNextFeature()
    while _f:
        _f_geom = transform(
            ilayer_reproject, wkt.loads(_f.GetGeometryRef().ExportToWkt())
        )
        nodes.append(
            Node(
                id=next(idgen),
                version="1",
                lat=_f_geom.y,
                lon=_f_geom.x,
                tags=[],  # maybe remove
            )
        )
        _f = ilayer.GetNextFeature()
    return nodes


def _get_deleted_way_ids(table, db, idfield="osm_id"):
    """Returns OSM ids present in osm_id column of table as list."""
    deletions_iter = db.get_layer_iter(table)
    return [_f.GetFieldAsString(_f.GetFieldIndex(idfield)) for _f in deletions_iter]


def _generate_intersection_db(layer, others, db, idgen, self=False):
    """
    Returns an rtree spatial index containing Nodes
    representing intersections between all features
    in <layer> and in all <others> layers in db.

    if <self> is true, also include intersections
    among features in <layer>.

    idgen is an iterator yielding unique ids

    returns a list of nodes and the rtree containing them,
    and a list of lists of intersecting ids for each
    table in others for modifying those intersecting ways.

    """
    nodes = []
    idlists = []
    for other in others:
        ilayer, idlist = db.intersections(
            new_layer=layer,
            intersecting_layer=other,
            ids=True,
        )
        if ilayer:
            nodes.extend(_nodes_for_intersections(ilayer, idgen))
            idlists.append(idlist)

    if self:
        ilayer = db.intersections(new_layer=layer, intersecting_layer=layer, ids=False)
        if ilayer:
            nodes.extend(_nodes_for_intersections(ilayer, idgen))

    # ensure no duplicate intersection nodes, which can happen
    # in the case of self intersections (e.g. where new features
    # are split using existing features, so they both intersect
    # with new features and existing features).
    # Dictionary trick explained here: https://stackoverflow.com/a/51635247
    if len(nodes) > 0:
        logging.info(f"{len(nodes)} intersection nodes found.")
    nodes = {
        (round(n.lat, COORDINATE_PRECISION), round(n.lon, COORDINATE_PRECISION)): n
        for n in nodes
    }.values()
    if len(nodes) > 0:
        logging.info(f"{len(nodes)} intersection nodes after duplicate removal.")

    rt = rtree.index.Index()
    for node in nodes:
        rt.insert(
            node.id,
            (
                node.lon - 0.001,
                node.lat - 0.001,
                node.lon + 0.001,
                node.lat - 0.001,
            ),  # left, bottom, right, top
            obj=node,
        )
    return nodes, rt, idlists


def _id_gen(id_offset, neg_id):
    """generator for sequential IDs"""
    id = id_offset if not neg_id else -id_offset
    while True:
        yield id
        id = (id + 1) if not neg_id else (id - 1)


def _generate_tags_from_feature(feature, fields, hstore_column=None, exclude=[]):
    """returns list of tags given layer fields and a feature containing
    fields. Will not produce a tag for any field name in <exclude>.

    If hstore_column is not null, tags will also be derived from the hstore column.
    Only tags that are _not_ present in <fields> will be added as Tags (duplicates
    are ignored, and columns take precedence.)
    """
    tags = []
    # if hstore column is present, we don't want to include
    # it in the output set of tags:
    if hstore_column:
        exclude.append(hstore_column)
    for field in fields:
        if field in exclude:
            continue  # skip
        fv = feature.GetFieldAsString(feature.GetFieldIndex(field))
        tags.append(Tag(key=field, value=fv))

    # Get values from hstore (if any) and add those that we haven't already
    # seen from <fields> as Tags to the `tags` list
    if hstore_column:
        existing_keys = set(fields)
        hstore_content = {}
        try:
            hstore_content = hstore_as_dict(
                feature.GetFieldAsString(feature.GetFieldIndex(hstore_column))
            )
        except ValueError:
            logging.error(
                '!! Error parsing hstore column "{hstore_column}" for feature {feature.GetFID()}.'
            )
        for key, value in hstore_content.items():
            if key not in existing_keys:
                tags.append(Tag(key=key, value=value))

    return tags


def _get_point_insertion_index(linestring, point):
    """Returns the index at which <point>
    should be inserted in a linestring .

    linestring: shapely.geometry.LineString
    point: shapely.geometry.Point

         N N+1
         | |
         | |
         v v
    -----+*+------
          |
          |

    returns integer
    """

    # at what % along <linestring> should <point> be inserted?
    interpolated_ptloc = linestring.project(point, normalized=True)

    # compute each constituent point's % along total length in <linestring>
    total_ls_length = 0
    ls_pts = list(linestring.coords)
    ls_pts_distances = zeros(len(ls_pts))
    for pt_idx in range(len(ls_pts) - 1):
        pointwise_dist = sg.Point(*ls_pts[pt_idx]).distance(
            sg.Point(*ls_pts[pt_idx + 1])
        )
        # distance of pt_idx + 1 from pt_idx
        ls_pts_distances[pt_idx + 1] = pointwise_dist
        # accumulate pointwise_dist into total length
        total_ls_length += pointwise_dist

    # compute fractional distance along line for each point
    # need cumulative sum of pairwise distances
    # divide each cumulative sum by total length
    ls_pts_fractional = cumsum(ls_pts_distances) / total_ls_length

    # insertion index is the smallest index in <ls_pts_fractional>
    # at which the fractional location of <point> is less than
    # the fractional index of any existing point in <linestring>.

    insertion_locations = interpolated_ptloc < ls_pts_fractional
    # np.argmax returns the first index where <insertion_locations>
    # is True, unless all elements of the array are False
    # (in which case the insertion is at idx  = len(ls_pts) -1 )
    return argmax(insertion_locations) if any(insertion_locations) else len(ls_pts) - 1


def _make_ways(nds, tags, idgen, node_limit=2000, closed=False):
    """
    Checks if <nds> contains more than <node_limit> nodes.

    If it does, produce len(<nds>) / 500 ways. Each
    resulting Way contains <tags>.

    If it doesn't, just return one Way with all nodes and tags
    included.

    If closed is True, we create a closed way by appending the
    ref of the ND at index 0 to the end of the nodelist. Will not
    do this if the Way exceeds the node limit.

    Returns a list of Ways.
    """
    max_new_len = 500
    ways = []
    n_nodes = len(nds)

    if n_nodes <= node_limit:
        if closed:
            nds.append(nds[0])
        ways.append(Way(id=next(idgen), version=1, nds=nds, tags=tags))
    else:
        joiner_node = None  # nothing to join with
        for nd_idx in range(0, n_nodes, max_new_len):
            # we must ensure that the newly-created Ways share a node
            # (joiner_node)
            new_nodes = nds[nd_idx : nd_idx + max_new_len]
            if joiner_node is not None:
                new_nodes = [joiner_node] + new_nodes
            ways.append(
                Way(
                    id=next(idgen),
                    version=1,
                    nds=new_nodes,
                    tags=tags,
                )
            )
            try:
                joiner_node = nds[nd_idx + max_new_len]  # joiner node is last node
            except IndexError:
                # end of list
                joiner_node = None

    return ways


def _modify_existing_way(way_geom, way_id, nodes, tags, intersection_db):
    """
    Create a new Way with id <way_id> made up of <nodes> and containing <tags>.

    All nodes in intersection_db that intersect with <way_geom> will be added
    to the Way and the nodelist at the index they're nearest to.

    Returns <Way>
    """
    new_nodes = nodes.copy()
    way_geom_pts = list(way_geom.coords)
    if len(way_geom_pts) > WAY_POINT_THRESHOLD:
        logging.warning(
            f"There are {len(way_geom_pts)} in the linestring (way_id: {way_id}), which is greater than the threshold ({WAY_POINT_THRESHOLD})."
        )

    add_nodes = [
        n
        for n in [
            _n.object
            for _n in intersection_db.intersection(
                way_geom.buffer(0.01).bounds, objects=True
            )
        ]
        if way_geom.intersects(sg.Point(n.lon, n.lat).buffer(0.00005))
    ]

    for n in add_nodes:

        # ensure at least 2 nodes in linestring
        if len(way_geom_pts) < 2:
            logging.warning("Malformed linestring found.")
            continue

        _g = sg.LineString(way_geom_pts)
        idx = _get_point_insertion_index(_g, sg.Point(n.lon, n.lat))
        ip_x, ip_y = way_geom_pts[idx]
        # there's a special case here where the intersection point already exists
        # on geom (e.g. if two trails intersect exactly at the endpoint of geom)
        #
        # to maintain connectivity we need to replace that Node in Geom
        # with n
        if round(  # if geom[idx] and add_node are the same
            n.lat, COORDINATE_PRECISION
        ) == round(ip_y, COORDINATE_PRECISION) and round(
            n.lon, COORDINATE_PRECISION
        ) == round(
            ip_x, COORDINATE_PRECISION
        ):

            try:
                del new_nodes[idx]  # avoid duplicating existing Node n
                del way_geom_pts[idx]
            except IndexError as e:
                logging.warning(
                    "Out of bounds error in Node removal. Does the intersection db have duplicates? "
                )

            new_nodes.insert(idx, n.id)
            way_geom_pts.insert(idx, (n.lon, n.lat))

        else:
            # just add the node id to the Way, because it doesn't
            # already exist in the linestring.
            new_nodes.insert(idx, n.id)
            way_geom_pts.insert(idx, (n.lon, n.lat))

    # If this is a long linestring we need to split it into many ways maybe
    # ways = _make_ways(node_ids_for_way, tags, idgen, node_limit=2000)
    w = Way(id=way_id, nds=new_nodes, tags=tags, version=2)
    return w


def _generate_relation_for_ways(ways, idgen, tags):
    """
    Produce a Relation representing all Ways.

    Adds Tags to relation.
    """
    multi_way_relation = None

    logging.debug(f"Creating Relation with {len(ways)} members.")
    multi_way_relation = Relation(
        id=next(idgen),
        version=1,
        members=[RelationMember(w.id, "way", "outer") for w in ways],
        tags=tags,
    )
    return multi_way_relation


def _generate_ways_and_nodes(
    geom,
    idgen,
    tags,
    intersection_db,
    nodes=None,
    way_id=None,
    max_nodes_per_way=2000,
    closed=False,
):
    """produce way and node objects for a geometry,
    using generator idgen to assign IDs. Adds tags
    to Way.

    if intersection_db is provided, all nodes in db that
    intersect with geom will be  added to the resulting Way
    at the index they're nearest to.

    any nodes added in add_nodes are NOT returned in
    the <nodes> retval.

    if `closed` is true, we produce a closed way by copying
    the `nd` ref of the first node to the end of the
    `nds` list of the newly-created Way.

    """
    nodes = []
    node_ids_for_way = []
    for (x, y) in geom.coords:
        this_point = sg.Point(x, y)

        # don't create a new node if there's already one in the intersection DB
        potential_inodes = [
            (n, this_point.distance(sg.Point(n.lon, n.lat)))
            for n in [
                _n.object
                for _n in intersection_db.intersection(
                    this_point.buffer(0.001).bounds, objects=True
                )
            ]
            if this_point.buffer(0.0001).intersects(sg.Point(n.lon, n.lat))
        ]
        sorted_inodes = sorted(potential_inodes, key=lambda x: x[1])

        if len(potential_inodes) > 0:
            node_ids_for_way.append(sorted_inodes[0][0].id)
        else:
            # make a new node
            _id = next(idgen)
            node_ids_for_way.append(_id)
            nodes.append(Node(id=_id, lat=y, lon=x, version=1, tags=[]))

    add_nodes = [
        n
        for n in [
            _n.object for _n in intersection_db.intersection(geom.bounds, objects=True)
        ]
        if sg.Point(n.lon, n.lat).intersects(geom) and n.id not in node_ids_for_way
    ]

    for n in add_nodes:
        ls_points = [(_n.lon, _n.lat) for _n in nodes]
        if len(ls_points) < 2:
            logging.warning("Malformed linestring found.")
            continue  # skip linestrings that are not linestrings
        _tmp_ls = sg.LineString(ls_points)
        idx = _get_point_insertion_index(_tmp_ls, sg.Point(n.lon, n.lat))
        ip_x, ip_y = list(_tmp_ls.coords)[idx]
        # there's a special case here where the intersection point already exists
        # on geom (e.g. if two trails intersect exactly at the endpoint of geom)
        #
        # to maintain connectivity we need to replace that Node in Geom
        # with n

        if sg.Point(n.lon, n.lat).almost_equals(
            sg.Point(ip_x, ip_y), COORDINATE_PRECISION
        ):
            try:
                del nodes[idx]  # avoid duplicating existing Node n
            except IndexError as e:
                logging.warning(
                    f"Out of bounds error in Node removal. Does the intersection db have duplicates? {len(add_nodes)} idx: {idx}, {len(nodes)}, {len(list(geom.coords))}"
                )

            node_ids_for_way[idx] = n.id

        else:
            # just add the node id to the Way, because it doesn't
            # already exist in the linestring.
            node_ids_for_way.insert(idx, n.id)

    # If this is a long linestring we need to split it into many ways maybe
    ways = _make_ways(
        node_ids_for_way, tags, idgen, node_limit=max_nodes_per_way, closed=closed
    )
    return ways, nodes


def generate_changes(
    table,
    others,
    deletions,
    dbname,
    dbport,
    dbuser,
    dbpass,
    dbhost,
    osmsrc,
    outfile,
    id_offset=0,
    neg_id=False,
    compress=True,
    self_intersections=False,
    max_nodes_per_way=2000,
    modify_only=False,
    hstore_column=None,
):
    """
    Generate an osm changefile (outfile) based on features in <table>
    (present in the database for which connection parameters are required).

    All features in `table` will be added to the changefile,
    as well as any features from `others` that must be modified to
    properly represent linestring intersections. <osmsrc> is a file path
    pointing to an osmium-readable OSM source file (.pbf) for the purpose
    of querying existing node IDS to maintain intersections when modifying
    existing waysm.

    `others` (either a string or list of strings) specifies the other table(s)
    in the database which must be queried for intersections with any newly-added
    features in `table`. Any intersections will produce a <modify> change file tag
    for the intersecting features in <other> that shares a junction node with
    the intersecting feature in `table`.


    :param table: Database table name from which new features will be derived.
    :type table: str

    """

    _global_node_id_all_ways = []
    ids = _id_gen(id_offset, neg_id)

    # <others> needs to be a list.
    others = [others] if isinstance(others, str) else others

    db_reader = OGRDBReader(dbname, dbport, dbuser, dbpass, dbhost)
    change_writer = OSMChangeWriter(outfile, compress=compress)

    new_feature_iter = db_reader.get_layer_iter(table)
    layer_fields = db_reader.get_layer_fields(table)
    n_features = db_reader.get_num_features(table)

    # generate intersection nodes
    (
        intersection_nodes,
        intersection_db,
        intersecting_idlists,
    ) = _generate_intersection_db(
        table, others, db_reader, ids, self=self_intersections
    )

    # We need to reproject layer features from native CRS
    # to OSM-compatible WGS84. <projection> can be used
    # with shapely.ops.transform.
    layer_epsg = db_reader.get_layer_epsg(table)
    projection = pyproj.Transformer.from_crs(
        pyproj.CRS(f"EPSG:{layer_epsg}"), WGS84, always_xy=True
    ).transform
    ## If we're creating "modify" nodes instead of create nodes,
    ## we need to go get the IDs of the nodes that make up
    ## any Ways that will be modified. Currently this only
    ## supports linestrings.

    existing_nodes_for_ways = []
    if modify_only:
        existing_nodes_for_ways = _get_way_node_map(
            osmsrc, db_reader.get_all_ids_for_layer(table)
        )

    # Main work loop; features in <table> are work unit.
    for feature in tqdm(
        new_feature_iter,
        desc="Processing New Features: ",
        total=n_features,
        unit="feature",
    ):
        try:  # want to log but skip most feature-level exceptions
            # skip null geometries
            if not feature.GetGeometryRef():
                logging.debug(f"feature {feature.GetFID()} has no geometry")
                continue

            # compute intersections + extract geometry + tags + reproject
            feat_geom = wkt.loads(feature.GetGeometryRef().ExportToWkt())
            feat_tags = _generate_tags_from_feature(
                feature, layer_fields, hstore_column=hstore_column
            )

            wgs84_geom = transform(projection, feat_geom)

            new_nodes = []
            new_ways = []
            new_relations = []

            if isinstance(wgs84_geom, sg.MultiLineString) or isinstance(
                wgs84_geom, sg.MultiPolygon
            ):
                raise NotImplementedError("Multi geometries not supported.")
            if isinstance(wgs84_geom, sg.Point):
                if modify_only:
                    existing_id = feature.GetFieldAsString(
                        feature.GetFieldIndex("osm_id")
                    )

                    new_nodes.append(
                        Node(
                            id=existing_id,
                            version=2,
                            lat=wgs84_geom.y,
                            lon=wgs84_geom.x,
                            tags=[tag for tag in feat_tags if tag.key != "osm_id"],
                        )
                    )
                else:
                    new_nodes.append(
                        Node(
                            id=next(ids),
                            version=1,
                            lat=wgs84_geom.y,
                            lon=wgs84_geom.x,
                            tags=feat_tags,
                        )
                    )

            elif isinstance(wgs84_geom, sg.LineString):
                ## NOTE that modify_only does not support modifying geometries.
                if modify_only:
                    existing_id = feature.GetFieldAsString(
                        feature.GetFieldIndex("osm_id")
                    )

                    new_ways.append(
                        Way(
                            id=existing_id,
                            version=2,
                            nds=existing_nodes_for_ways[existing_id],
                            tags=[tag for tag in feat_tags if tag.key != "osm_id"],
                        )
                    )
                else:  # not modifying, just creating
                    ways, nodes = _generate_ways_and_nodes(
                        wgs84_geom,
                        ids,
                        feat_tags,
                        intersection_db,
                        max_nodes_per_way=max_nodes_per_way,
                    )
                    new_nodes.extend(nodes)
                    new_ways.extend(ways)
                    _global_node_id_all_ways.extend(
                        chain.from_iterable([w.nds for w in ways])
                    )
            elif isinstance(wgs84_geom, sg.Polygon):
                ## If we're taking all features to be newly-created (~modify_only)
                ## we need to create ways and nodes for that feature.
                ## IF we're only modifying existing features with features
                ## in the table, we just create a new Way with existing ID and nodes and new tags.

                ## NOTE that modify_only does not support modifying geometries.
                if modify_only:
                    existing_id = feature.GetFieldAsString(
                        feature.GetFieldIndex("osm_id")
                    )

                    new_ways.append(
                        Way(
                            id=existing_id,
                            version=2,
                            nds=existing_nodes_for_ways[existing_id],
                            tags=[tag for tag in feat_tags if tag.key != "osm_id"],
                        )
                    )
                else:  # not modifying, just creating
                    # simple polygons can be treated like Ways.
                    if len(wgs84_geom.interiors) == 0:
                        ways, nodes = _generate_ways_and_nodes(
                            wgs84_geom.exterior,
                            ids,
                            feat_tags,
                            intersection_db,
                            max_nodes_per_way=max_nodes_per_way,
                            closed=True,
                        )
                        new_nodes.extend(nodes)
                        new_ways.extend(ways)
                        _global_node_id_all_ways.extend(
                            chain.from_iterable([w.nds for w in ways])
                        )
                        # !! In some cases when the outer ring of the Polygon
                        # is longer than max_nodes_per_way, we create a Relation
                        # to represent that way.
                        if len(ways) > 1:
                            new_relations.append(
                                _generate_relation_for_ways(
                                    ways,
                                    ids,
                                    ways[0].tags + [Tag("type", "multipolygon")],
                                )
                            )
                    else:  # more complex polygons (w/ holes) need to be Relations
                        outer_ways, outer_nodes = _generate_ways_and_nodes(
                            # no tags on these ways, they belong on the relation
                            wgs84_geom.exterior,
                            ids,
                            [],
                            intersection_db,
                            max_nodes_per_way=max_nodes_per_way,
                            closed=True,
                        )
                        inner_ways, inner_nodes = [], []
                        for hole in wgs84_geom.interiors:
                            _ways, _nodes = _generate_ways_and_nodes(
                                # no tags on any of these Ways
                                hole,
                                ids,
                                [],
                                intersection_db,
                                max_nodes_per_way=max_nodes_per_way,
                                closed=True,
                            )
                            inner_ways.extend(_ways)
                            inner_nodes.extend(_nodes)
                        # Build relation
                        members = [
                            RelationMember(ref=w.id, type="way", role="outer")
                            for w in outer_ways
                        ]
                        members.extend(
                            [
                                RelationMember(ref=w.id, type="way", role="inner")
                                for w in inner_ways
                            ]
                        )
                        # add 'multipolygon' tag (even though it's not.)
                        # https://wiki.openstreetmap.org/wiki/Relation:multipolygon#One_outer_and_one_inner_ring
                        feat_tags.append(Tag(key="type", value="multipolygon"))
                        relation = Relation(
                            id=next(ids),
                            version="1",
                            members=members,
                            tags=feat_tags,  # original polygon tags on relation
                        )
                        new_ways.extend(outer_ways + inner_ways)
                        new_nodes.extend(outer_nodes + inner_nodes)
                        new_relations.append(relation)

            else:
                raise RuntimeError(f"{type(wgs84_geom)} is not LineString or Polygon")

            ## Write new ways and nodes to file
            if len(new_ways) > 0 or len(new_nodes) > 0:
                if modify_only:
                    change_writer.add_modify(new_ways)
                    change_writer.add_modify(new_nodes)
                else:
                    change_writer.add_create(new_nodes + new_ways)
            if len(new_relations) > 0:
                change_writer.add_create(new_relations)

        except Exception as e:
            logging.warning(
                f"Exception encountered processing a feature. [exception={repr(e)} fid={feature.GetFID()}]"
            )
            continue

    # Write all modified ways with intersections
    # Because we have to re-generate nodes for all points
    # within the intersecting linestrings, we write
    # those as new nodes. We also get deletion ways +
    # their corresponding nodes here too, to save time.
    logging.info(f"Retrieving deletion nodes for tables: {deletions}")
    deletion_way_ids = [_get_deleted_way_ids(table, db_reader) for table in deletions]
    logging.info(
        f"Retrieving existing Node IDs for modified and deleted ways (file: {osmsrc})"
    )

    modified_ways = []
    way_node_map = _get_way_node_map(
        osmsrc, list(chain.from_iterable(intersecting_idlists + deletion_way_ids))
    )

    # only if there are intersections
    if len(intersection_nodes) > 0:
        # for all intersecting layers
        for i, other_layer in enumerate(others):
            # get fields, feature, + projection
            other_layer_fields = db_reader.get_layer_fields(other_layer)
            other_layer_epsg = db_reader.get_layer_epsg(other_layer)
            projection = pyproj.Transformer.from_crs(
                pyproj.CRS(f"EPSG:{other_layer_epsg}"), WGS84, always_xy=True
            ).transform

            # get list of intersecting IDS (already computed)
            intersecting_ids = intersecting_idlists[i]

            # modify all features with known intersections
            # generate original OSM node ID database from source file
            for id in tqdm(
                intersecting_ids, desc=f"Processing {other_layer} intersections"
            ):

                # generate modified way and correspdoning nodes
                _feat = db_reader.get_feature_by_id(other_layer, id, "osm_id")
                _feat_tags = _generate_tags_from_feature(
                    _feat, other_layer_fields, hstore_column=hstore_column
                )
                other_feat_geom = wkt.loads(_feat.GetGeometryRef().ExportToWkt())
                other_feat_wgs84 = transform(projection, other_feat_geom)

                try:
                    existing_node_ids = way_node_map[id]
                except KeyError as e:
                    logging.error(f"Way with ID {id} not found. Is it a relation?")
                    continue

                # mod_ways, mod_nodes = _generate_ways_and_nodes(
                #     other_feat_wgs84, ids, _feat_tags, intersection_db
                # )
                if isinstance(other_feat_wgs84, sg.LineString):
                    # Linestrings we can directly modify
                    mod_way = _modify_existing_way(
                        other_feat_wgs84,
                        id,
                        existing_node_ids,
                        _feat_tags,
                        intersection_db,
                    )
                if isinstance(other_feat_wgs84, sg.Polygon):
                    # Polygons we need to modify the outermost ring of a polygon relation.
                    # However, we need to be sure that the ID that's being referenced here is that of a
                    # Way and not a Relation. This is complicated and likely not worth implementing
                    # right now.
                    logging.warning(
                        (
                            "Polygon Intersection Warning: a feature intersects "
                            "With a polygon. Modifying this polygon to add an intersection "
                            "node is not currently supported."
                        )
                    )

                modified_ways.append(mod_way)
                _global_node_id_all_ways.extend(mod_way.nds)

    if len(modified_ways) > 0:
        # write any modified ways from intersecting layers
        change_writer.add_modify(modified_ways)

    # Write all intersecting nodes to file:
    change_writer.add_create(intersection_nodes)

    # Write deletions, including ways + nodes
    ids_to_delete = []
    for way_id in chain.from_iterable(deletion_way_ids):
        # constituent node ids
        ids_to_delete.extend(way_node_map[way_id])
        # way id itself
        ids_to_delete.append(way_id)
    change_writer.add_delete(ids_to_delete)

    change_writer.close()

    _node_counts = Counter(_global_node_id_all_ways)
    logging.debug(f"Most common nodes (N=20): {_node_counts.most_common(20)}")

    return True


def generate_deletions(
    table,
    idfield,
    dbname,
    dbport,
    dbuser,
    dbpass,
    dbhost,
    osmsrc,
    outfile,
    compress=True,
    skip_nodes=True,
):
    """
    Produce a changefile with <delete> nodes for all IDs in table.
    IDs are chosen via idfield.

    TODO: provide an option to not delete Nodes (which could break intersections.)

    """
    db_reader = OGRDBReader(dbname, dbport, dbuser, dbpass, dbhost)
    change_writer = OSMChangeWriter(outfile, compress=compress)

    logging.info(f"Retrieving deletion nodes for table: {table}")
    deletion_way_ids = set(_get_deleted_way_ids(table, db_reader, idfield))
    logging.info(f"Retrieving existing Node IDs for deleted ways (file: {osmsrc})")

    way_node_map = []
    if not skip_nodes:
        way_node_map = _get_way_node_map(osmsrc, deletion_way_ids)

    # Write deletions, including ways + nodes
    # we need to ensure that we don't write <delete> tags
    # for the same Node twice, so we keep track of the ones we've
    # written and skip them if they re-occur
    objs_to_delete = []
    known_nodes = set()
    for way_id in deletion_way_ids:
        # constituent node ids
        if not skip_nodes:
            for nid in way_node_map[way_id]:
                if nid not in known_nodes:
                    objs_to_delete.append(
                        Node(id=nid, version=99, lat=0, lon=0, tags=[])
                    )
                else:
                    logging.debug(f"Skipping node {nid} as it already was written.")
                known_nodes.add(nid)
        # way id itself
        objs_to_delete.append(Way(id=way_id, version=99, nds=[], tags=[]))
    change_writer.add_delete(objs_to_delete)
    change_writer.close()
