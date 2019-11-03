'''
Command-line interface code for plex-graph
'''
import logging

import click

from plex_graph import plex


def setup_logging(debug: bool = False) -> None:
    '''Configure logging and set default output to INFO or DEBUG'''
    level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(level=level)


@click.command()
@click.option('--verbose', default=False)
def plex_graph(verbose: bool) -> None:
    '''CLI entry-point'''
    setup_logging(debug=verbose)
    # plex.generate_data()
    plex.graph_data()


if __name__ == '__main__':
    plex_graph(obj={})
