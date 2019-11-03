#!/usr/bin/env python3
'''
Playing around with pulling movie data from plex servers and graphing
relationships between movies via actors.
'''
import ast
import logging
import shelve
from configparser import ConfigParser
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

import matplotlib.pyplot as plot
import networkx as nx
import requests
from plexapi.library import LibrarySection
from plexapi.myplex import MyPlexAccount, MyPlexResource
from plexapi.server import PlexServer

MIN_RELATIONS: int = 11
PLEX_USER: str = ''
PLEX_PASS: str = ''
CONFIG_FILE: str = 'config.ini'


def setup_logging(debug: bool = False) -> None:
    '''Configure logging and set default output to INFO or DEBUG'''
    level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(level=level)


@dataclass()
class PlexServerConfig:
    '''PlexServer connection data'''
    name: str
    urls: List[str]
    token: str
    lasturl: Optional[str] = None
    connection: Optional[PlexServer] = None


@dataclass(eq=True, frozen=True)
class Movie:
    '''Plex Movie data class comprised of nearly all data plex stores'''
    name: str
    year: int
    studio: str
    content_rating: str
    rating: str
    writers: Tuple[str, ...] = field(default_factory=tuple)
    directors: Tuple[str, ...] = field(default_factory=tuple)
    actors: Tuple[str, ...] = field(default_factory=tuple)
    genres: Tuple[str, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f'{self.name}'

    def __repr__(self) -> str:
        return f'{self.name}'


@dataclass()
class MovieData:
    '''A class to store all movie-related data'''
    genres: Set[str] = field(default_factory=set)
    people: Set[str] = field(default_factory=set)
    movies: List[Movie] = field(default_factory=list)


def write_config(config: ConfigParser) -> None:
    '''Store plex server authentication on disk'''
    with open(CONFIG_FILE, 'w') as config_file:
        config.write(config_file)


def generate_config(user: str, password: str) -> None:
    '''Build the ConfigParser data for plex server authentication'''
    config: ConfigParser = ConfigParser()
    account: MyPlexAccount = MyPlexAccount(user, password)

    servers: List[MyPlexResource]
    servers = [resource for resource in account.resources()
               if 'server' in resource.provides.split(',')]
    for server in servers:
        config[f'server:{server.name}'] = {
            'baseurls': str([conn.httpuri for conn in server.connections]),
            'token': server.accessToken,
        }
    write_config(config)


def read_config() -> ConfigParser:
    '''Read plex server authentication from disk.'''
    with open(CONFIG_FILE, 'r') as config_file:
        config = ConfigParser()
        config.read_file(config_file)
    return config


def get_servers(config: ConfigParser) -> List[PlexServerConfig]:
    '''Connect to plex servers from our config'''
    servers: List[PlexServerConfig] = []
    for key in list(config.keys()):
        if key.startswith('server:'):
            name = key.split(':')[1]
            urls: List[str] = ast.literal_eval(config[key]['baseurls'])
            server = PlexServerConfig(name=name, urls=urls,
                                      token=config[key]['token'])
            if 'lasturl' in config[key]:
                server.lasturl = config[key]['lasturl']
            servers.append(server)

    for server in servers:
        logging.info('Connecting to server %s', server.name)
        connection = None

        # See if the last used URL works
        if server.lasturl:
            try:
                logging.debug('Trying %s', server.lasturl)
                connection = PlexServer(baseurl=server.lasturl,
                                        token=server.token,
                                        timeout=5)
                server.connection = connection
                continue
            except requests.exceptions.ConnectTimeout:
                logging.debug('No connection via %s', server.lasturl)

        # Try connecting to all possible URLs
        for url in server.urls:
            # Skip retrying lasturl
            if server.lasturl:
                if url == server.lasturl:
                    continue
            try:
                logging.debug('Trying %s', url)
                connection = PlexServer(baseurl=url,
                                        token=server.token,
                                        timeout=5)
                server.lasturl = url
                server.connection = connection
                break
            except requests.exceptions.ConnectTimeout:
                logging.debug('No connection via %s', url)
        if not connection:
            logging.info('No connection could be made to %s', server.name)
    return servers


def update_config(config: ConfigParser,
                  servers: List[PlexServerConfig]) -> ConfigParser:
    '''
    After connecting to servers, update ConfigParser data with lasturl data.

    The plex API may return multiple URIs for each server.  To speed future
    connections we will save the URI that worked so we can try that first.

    Returns the updated ConfigParser.
    '''

    for server in servers:
        if server.lasturl:
            config[f'server:{server.name}']['lasturl'] = server.lasturl
    write_config(config)
    return config


def get_plex_movie_sections(server: PlexServer) -> List[LibrarySection]:
    '''
    Finds all 'Movie' library sections on a server.

    Returns a list of plexapi.library.MovieSection objects
    '''
    movie_sections = [section for section in
                      server.connection.library.sections()
                      if section.title == 'Movies']
    logging.debug('Found movie section(s) %s', movie_sections)
    return movie_sections


def parse_plex_movies(movie_sections: List[LibrarySection]) -> MovieData:
    '''Parse all movies in the list of movie library sections.

    Populate the global list of movies, genres, and people from Plex
    '''
    movie_data: MovieData = MovieData()

    movie_count = 1
    for section in movie_sections:
        movie_total = len(section.all())
        for media in section.all():
            logging.info('Processing(%d/%d) "%s"',
                         movie_count, movie_total, media.title)
            movie_count += 1
            media.reload()  # Get full object metadata
            writers: Set[str] = set()
            for person in media.writers:
                person = person.tag
                movie_data.people.add(person)
                writers.add(person)
            directors: Set[str] = set()
            for person in media.directors:
                person = person.tag
                movie_data.people.add(person)
                directors.add(person)
            actors: Set[str] = set()
            for person in media.roles:
                person = person.tag
                movie_data.people.add(person)
                actors.add(person)
            genres: Set[str] = set()
            for genre in media.genres:
                genre = genre.tag
                movie_data.genres.add(genre)
                genres.add(genre)
            movie_data.movies.append(
                Movie(name=media.title,
                      year=int(media.year or 1900),
                      studio=media.studio,
                      content_rating=media.contentRating,
                      rating=media.rating,
                      writers=tuple(writers),
                      directors=tuple(directors),
                      actors=tuple(actors),
                      genres=tuple(genres),
                      ))
    return movie_data


def write_shelve(movie_data: MovieData) -> None:
    '''Store the global list of Movies, Genres, and People on disk

    To avoid pulling data from the plex server on each run we write
    a python shelve file.
    '''
    # Opening with mode 'n' will always create a new, empty database
    with shelve.open('shelve', 'n') as data:
        data['version'] = 1
        data['movie_data'] = movie_data


def read_shelve() -> MovieData:
    '''Read the global list of Movies, Genres, and People from disk

    To avoid pulling data from the plex server on each run we use
    a python shelve file to persist data between runs.
    '''
    movie_data: MovieData = MovieData()
    with shelve.open('shelve', 'r') as data:
        if 'version' in data:
            logging.debug('Found version:%d data', data['version'])
            if data['version'] == 1:
                movie_data = data['movie_data']
                return movie_data
        raise RuntimeError('Unknown data format, remove "shelve" file '
                           'and regenerate data')


def generate_data() -> None:
    '''Glue code incorporating all the functions to read data from plex
    and generate our data for future runs.
    '''
    if PLEX_USER and PLEX_PASS:
        generate_config(PLEX_USER, PLEX_PASS)
    config = read_config()
    servers = get_servers(config)
    config = update_config(config, servers)
    for server in servers:
        logging.info('Indexing server %s', server.name)
        movie_sections = get_plex_movie_sections(server)
        movie_data: MovieData = parse_plex_movies(movie_sections)
    write_shelve(movie_data)


def graph_data() -> None:
    '''Experiment with graphing Movie and Actor relationships'''
    logging.info('Loading data from disk')
    movie_data: MovieData = read_shelve()

    # Count the number of movies an actor appears in
    actors = {person: 0 for person in movie_data.people}
    for movie in movie_data.movies:
        for actor in movie.actors:
            actors[actor] = actors[actor] + 1

    # Drop people that are connected to less than {MIN_RELATIONS} movies
    # And right now that will be actors
    drops = set()
    for person in movie_data.people:
        if actors[person] < MIN_RELATIONS:
            drops.add(person)
    logging.info('There are %d actors total', len(movie_data.people))
    movie_data.people = movie_data.people - drops
    logging.info('Dropping actors with less than %d movies leaves %d actors',
                 MIN_RELATIONS, len(movie_data.people))

    graph = nx.Graph(name='Movie/Actor relationships')
    for person in movie_data.people:
        graph.add_node(person)

    movie_count = 0
    for movie in movie_data.movies:
        relation_found = False
        for actor in movie.actors:
            if actor in movie_data.people:
                if not relation_found:
                    # Only add a movie if we'll have an actor associated
                    movie_count += 1
                    graph.add_node(movie)
                    relation_found = True
                graph.add_edge(movie, actor)
    logging.info('Now there are only %d movies', movie_count)

    logging.info(nx.classes.function.info(graph))
    nx.draw(graph, node_color='r', edge_color='b', with_labels=True)
    plot.show()


if __name__ == '__main__':
    setup_logging()
    # generate_data()
    graph_data()
