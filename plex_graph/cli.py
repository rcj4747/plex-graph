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


@click.group()
@click.option('-v', '--verbose', is_flag=True, default=False)
def plex_graph(verbose: bool) -> None:
    '''CLI entry-point'''
    setup_logging(debug=verbose)


@click.command()
@click.option('-u', '--user', prompt='Plex user name')
@click.option('-p', '--password', prompt='Plex password', hide_input=True)
def auth(user: str, password: str) -> None:
    '''Authenticate to Plex'''
    plex.plex_account_auth(user, password)


@click.command()
@click.option('-r', '--relationships', default=11, show_default=True,
              help='Required minimum movies to display an actor')
def graph(relationships: int) -> None:
    '''Display a graph of movie / actor relationships'''
    plex.data_graph(relationships)


plex_graph.add_command(auth)
plex_graph.add_command(graph)

if __name__ == '__main__':
    plex_graph(obj={})
