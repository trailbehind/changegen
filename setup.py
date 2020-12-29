from setuptools import find_packages
from setuptools import setup

setup(
    name="changegen",
    author="Trailbehind, Inc.",
    author_email="tony@gaiagps.com",
    version="0.1",
    python_requires=">=3.7",
    description="Tools for conflating third-party linestrings with OSM.",
    packages=find_packages(),
    install_requires=[
        "click",
        "tqdm",
        "shapely",
        "gdal",
        "lxml",
        "psycopg2",
        "pyproj",
        "rtree",
        "osmium"
    ],
    test_suite="test",
    entry_points="""
        [console_scripts]
        changegen=changegen.__main__:main
    """,
    include_package_data=True,
    zip_safe=True,
)
