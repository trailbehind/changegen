import gzip
import io
import logging
import os
import sys
import tempfile
import warnings
from collections import namedtuple
from shutil import copyfile
from shutil import copyfileobj

from lxml import etree

"""
changewriter.py

tony@gaiagps.com

Module for writing OSMChange files
(https://wiki.openstreetmap.org/wiki/OsmChange).

Data Types:
    Tag (namedtuple): key, value
    Node (namedtuple): id, version, lat, lon, tags (array of Tags)
    Way (namedtuple): id, version, nds (array of Node ids [ints]),
        tags (array of Tags)

Classes:
    OSMChangeWriter: writes XML changefile

Functions:
    write_osm_object: _private_ helper function to write osm object to
    OSMChangeWriter.

"""


OSMCHANGE_VERSION = "0.6"
OSMCHANGE_GENERATOR = f"osmchangewriter (Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})"

Tag = namedtuple("Tag", "key,value")
Node = namedtuple("Node", "id, version, lat, lon, tags")
Way = namedtuple("Way", "id, version, nds, tags")


def write_osm_object(osm, writer):
    """Writes an OSM object (Node, Way)
    as an XML object. Uses the type of the
    namedtuple representing each OSM object
    to determine the type of XML element to write.

    Creates child elements for each Tag or nd (node ref)
    """
    try:
        attrs = dict(osm._asdict())
        objtype = type(osm).__name__.lower()
        attrs.pop("tags")
        if hasattr(osm, "nds"):
            attrs.pop("nds")
        attrs = {k: str(attrs[k]) for k in attrs.keys()}
        with writer.element(objtype, **attrs):
            # special cases for objects with
            # <tags> or <nds> (ways). Write as sub-elems
            if hasattr(osm, "tags"):
                for tag in osm.tags:
                    writer.write(etree.Element("tag", k=str(tag.key), v=str(tag.value)))
            if hasattr(osm, "nds"):
                for nd in osm.nds:
                    writer.write(etree.Element("nd", ref=str(nd)))
            writer.flush()
    except AttributeError:
        raise RuntimeError(f"OSM Object {osm} is malformed.")


class OSMChangeWriter(object):
    """
    Write OSMChange format
    (https://wiki.openstreetmap.org/wiki/OsmChange)
    to file_like object. close() MUST be called
    to ensure compliance with XML schema.

    Provides support for modify and add tags currently,
    with support for Node, Way, and Tag OSM
    elements (defined above.)

    """

    _root_element_open = (
        f'<osmChange version="{OSMCHANGE_VERSION}" generator="{OSMCHANGE_GENERATOR}">'
    )
    _root_element_close = "</osmChange>"

    def __init__(self, filename=None, compress=False):
        super(OSMChangeWriter, self).__init__()

        self.compress = compress
        self.filename = filename
        self.fileobj = None
        self.closed = False
        self._data_written = False

        # set fileobj based on compression
        if self.filename and self.compress:
            self.fileobj = gzip.GzipFile(filename=self.filename, mode="w")
        elif self.filename and not self.compress:
            self.fileobj = open(self.filename, "wb+", buffering=0)

        # write open tag before initializing etree.xmlfile
        self.fileobj.write(OSMChangeWriter._root_element_open.encode("utf-8"))

        # etree.xmlfile is a streaming xml writer.
        #
        # we don't use the compression param to etree.xmlfile
        # to retain control of the gzip buffer, even though we don't
        # use it directly anymore.
        self.xmlwriter = etree.xmlfile(self.fileobj, encoding="utf-8")

    def __del__(self):
        """Warn if close() not called on deletion. close() is required
        for valid XML.

        Alternatively __del__ could call close() but that didn't seem right.
        """
        if self._data_written and not self.closed:
            warnings.warn(
                f"OSMChangeWriter <{hex(id(self))}>: close() not called before deletion. Invalid XML will result!",
                ResourceWarning,
            )

    def close(self):
        """
        Add the <osmChange> closing tag and close the file.
        """

        self.fileobj.flush()
        self.fileobj.write(OSMChangeWriter._root_element_close.encode("utf-8"))
        self.fileobj.close()
        self.closed = True

    def add_modify(self, elementlist):
        """Creates <modify> element containing
        all elements in elementlist."""
        with self.xmlwriter as writer:
            with writer.element("modify"):
                for e in elementlist:
                    write_osm_object(e, writer)
            writer.flush()
        self._data_written = True

    def add_create(self, elementlist):
        """Creates <create> element containing
        all elements in elementlist.

        **NOTE**: does *not* ensure that <node>
        elements are added for every <node> in any
        Ways in the elementlist.
        """
        with self.xmlwriter as writer:
            with writer.element("create"):
                for e in elementlist:
                    write_osm_object(e, writer)
            writer.flush()
        self._data_written = True
