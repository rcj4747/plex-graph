'''
Command-line interface code for plex-graph
'''
import logging

import click

from plex_graph import data, plex


def setup_logging(debug: bool = False) -> None:
    '''Configure logging and set default output to INFO or DEBUG'''
    level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(level=level)


@click.group()
@click.option('-v', '--verbose', is_flag=True, default=False)
def plex_graph(verbose: bool) -> None:
    '''Graph relationships between Movies in a Plex server library'''
    setup_logging(debug=verbose)


@click.command()
@click.option('-u', '--user', prompt='Plex user name')
@click.option('-p', '--password', prompt='Plex password', hide_input=True)
def auth(user: str, password: str) -> None:
    '''Authenticate to Plex services and discover media servers'''
    plex.account_auth(user, password)


@click.command()
def harvest() -> None:
    '''Gather Movie data from Plex servers'''
    config = plex.server_read()
    servers = plex.get_servers(config)
    config = plex.server_config_update(config, servers)
    for server in servers:
        logging.info('Indexing server %s', server.name)
        movie_sections = plex.get_movie_sections(server)
        movie_data: data.MovieData = plex.parse_movies(movie_sections)
    data.cache_store(movie_data)


@click.command()
@click.option('-r', '--relationships', default=11, show_default=True,
              help='Required minimum movies to display an actor')
def graph(relationships: int) -> None:
    '''Display a graph of movie / actor relationships'''
    data.graph(relationships)


@click.command()
def ratings() -> None:
    '''Analyze movie ratings'''
    data.rating_histogram()


plex_graph.add_command(auth)
plex_graph.add_command(harvest)
plex_graph.add_command(graph)
plex_graph.add_command(ratings)

if __name__ == '__main__':
    plex_graph(verbose=False)
