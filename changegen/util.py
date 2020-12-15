import logging


def setup_logging(debug=False):
    """ Setup logging, mostly hiding logging from third party libraries. """
    logging.basicConfig(
        format="%(asctime)s [%(process)d] [%(name)s-%(levelname)s] %(filename)s:%(lineno)s:%(funcName)s %(message)s"
        if debug
        else "%(asctime)s %(message)s",
        level=logging.DEBUG if debug else logging.INFO,
        datefmt="%H:%M:%S",
    )
    for name in ["s3transfer", "botocore", "requests.packages.urllib3.connectionpool"]:
        logging.getLogger(name).setLevel(logging.WARNING)
