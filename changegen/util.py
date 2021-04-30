import logging

import click


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


class NotRequiredIf(click.Option):
    def __init__(self, *args, **kwargs):
        self.not_required_if = kwargs.pop("not_required_if")
        assert self.not_required_if, "'not_required_if' parameter required"
        kwargs["help"] = (
            kwargs.get("help", "")
            + " NOTE: This argument is mutually exclusive with %s"
            % self.not_required_if
        ).strip()
        super(NotRequiredIf, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        we_are_present = self.name in opts
        other_present = self.not_required_if in opts

        if other_present:
            if we_are_present:
                raise click.UsageError(
                    "Illegal usage: `%s` is mutually exclusive with `%s`"
                    % (self.name, self.not_required_if)
                )
            else:
                self.prompt = None

        return super(NotRequiredIf, self).handle_parse_result(ctx, opts, args)
