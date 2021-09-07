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
from typing import List
from typing import Union

from lxml import etree

__doc__ = """

Writing OSMChange Files (``changewriter``)
==========================================

The :py:mod:`changewriter` module provides an interface for writing `OSMChange files <https://wiki.openstreetmap.org/wiki/OsmChange>`_. This interface is 
defined as :py:class:`OSMChangeWriter`.

It supports **addition**, **removal**, and **modification** of Nodes, 
Ways, and Relations. 

The general workflow to use this class is the following: 

* Create an instance of :py:class:`OSMChangeWriter` with a filename
* Create OSM objects using the classes provided here (:py:obj:`Node`, :py:obj:`Way`, etc.)
* Use the member functions (:py:meth:`OSMChangeWriter.add_create`, :py:meth:`OSMChangeWriter.add_modify`, etc.) to create \
    the desired nodes in the changefile
* :py:meth:`close` the changefile

.. note::
   The opening ``<osmChange>`` tag in the output file will contain a ``generator`` attribute 
   which is set as follows: ``osmchangewriter (Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})``

"""


OSMCHANGE_VERSION = "0.6"
OSMCHANGE_GENERATOR = f"osmchangewriter (Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})"

Tag = namedtuple("Tag", "key,value")
Tag.__doc__ = "OSM ``Tag`` element."

Node = namedtuple("Node", "id, version, lat, lon, tags")
Node.__doc__ = "OSM ``Node`` element."

Way = namedtuple("Way", "id, version, nds, tags")
Way.__doc__ = "OSM ``Way`` element. All fields are required. "
Way.nds.__doc__ = (
    "``Nds`` is a list of OSM IDs representing the ``Nodes`` that comprise the ``Way``."
)

Relation = namedtuple("Relation", "id, version, members, tags")
Relation.__doc__ = (
    "OSM ``Relation`` element. Members must be :py:obj:`RelationMember` objects."
)
Relation.members.__doc__ = "List of :py:obj:`RelationMember` objects."

RelationMember = namedtuple("RelationMember", "ref, type, role")
RelationMember.__doc__ = "OSM ``RelationMember`` element. "


class OSMChangeWriter(object):
    """
    Write changesets as `OSMChange format
    <https://wiki.openstreetmap.org/wiki/OsmChange>`_
    to a file.

    Provides support for ``modify``, ``create``,  add ``delete`` tags currently,
    with support for Node (:py:obj:`Node`), Way (:py:obj:`Way`), and Relation (:py:obj:`Relation`) OSM
    elements. 

    :py:meth:`close` **must** be called
    to ensure compliance with XML schema.

    :param filename: A path specifying the location of the output changefile. 
    :type filename: str
    :param compress: A boolean indicating wither to use GZip compression when writing the changefile. 
    :type compress: bool

    :raises `warnings.ResourceWarning`: if :py:meth:`close` isn't called before object is garbage-collected \
        the resulting file will be missing a closing XML tag and will be invalid. 

    Example
    -------
    .. code-block:: python
       
       writer = OSMChangeWriter('test.osc', compress=True)
       _tag = changewriter.Tag("attribute", "value")
       _node = changewriter.Node(id="-111", version="99", lat=90, lon=180, tags=[_tag])
       writer.add_create([_node])
       writer.close()


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
        Add the ``</osmChange>`` closing tag and close the file.
        """

        self.fileobj.flush()
        self.fileobj.write(OSMChangeWriter._root_element_close.encode("utf-8"))
        self.fileobj.close()
        self.closed = True

    def add_modify(self, elementlist: List[Union[Node, Relation, Way]]):
        """Creates ``<modify>`` tag containing
        all elements in elementlist."""
        with self.xmlwriter as writer:
            with writer.element("modify"):
                for e in elementlist:
                    write_osm_object(e, writer)
            writer.flush()
        self._data_written = True

    def add_create(self, elementlist: List[Union[Node, Relation, Way]]):
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

    def add_delete(self, elementlist: List[Union[Node, Relation, Way]]):
        """Creates a <delete> element containing
        all elements in elementlist"""

        with self.xmlwriter as writer:
            with writer.element("delete"):
                for e in elementlist:
                    write_osm_object(e, writer)
                writer.flush()
        self._data_written = True


def write_osm_object(osm: Union[Node, Way, Relation], writer: OSMChangeWriter):
    """

    Helper function that writes an OSM object
    (:py:obj:`Node`, :py:obj:`Way`, :py:obj:`Relation`)
    as an XML object using an :py:class:`OSMChangeWriter`. Uses the type of the
    namedtuple representing each OSM object
    to determine the type of XML element to write.

    Creates child elements for each Tag or nd (node ref) contained within the
    parent object.
    """
    try:
        attrs = dict(osm._asdict())
        objtype = type(osm).__name__.lower()
        # we don't want to write tags, nds, or members in the main element
        # for objects. They'll get written as child elements below.
        attrs.pop("tags")
        if hasattr(osm, "nds"):
            attrs.pop("nds")
        if hasattr(osm, "members"):
            attrs.pop("members")
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
            if hasattr(osm, "members"):
                for member in osm.members:
                    writer.write(
                        etree.Element(
                            "member",
                            ref=str(member.ref),
                            type=member.type,
                            role=member.role,
                        )
                    )
            writer.flush()
    except AttributeError:
        raise RuntimeError(f"OSM Object {osm} is malformed.")
