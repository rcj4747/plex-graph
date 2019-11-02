#!/usr/bin/env python3
'''
Playing around with pulling movie data from plex servers and graphing
relationships between movies via actors.
'''
import ast
import shelve
from configparser import ConfigParser
from dataclasses import dataclass, field
from typing import List, Set, Tuple

import matplotlib.pyplot as plot
import networkx as nx
import requests
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer

MIN_RELATIONS: int = 11
PLEX_USER: str = ''
PLEX_PASS: str = ''
CONFIG_FILE: str = 'config.ini'


@dataclass(eq=True, frozen=True)
class Movie:
    '''Plex Movie data class comprised of nearly all data plex stores'''
    name: str
    year: int
    studio: str
    content_rating: str
    rating: str
    writers: Tuple[str] = field(default_factory=tuple)
    directors: Tuple[str] = field(default_factory=tuple)
    actors: Tuple[str] = field(default_factory=tuple)
    genres: Tuple[str] = field(default_factory=tuple)

    def __str__(self):
        return f'{self.name}'

    def __repr__(self):
        return f'{self.name}'


GENRES: Set[str] = set()
PEOPLE: Set[str] = set()
MOVIES: List[Movie] = []


def write_config(config: ConfigParser) -> None:
    '''Store plex server authentication on disk'''
    with open(CONFIG_FILE, 'w') as config_file:
        config.write(config_file)


def generate_config(user: str, password: str) -> None:
    '''Build the ConfigParser data for plex server authentication'''
    config: ConfigParser = ConfigParser()
    account = MyPlexAccount(PLEX_USER, PLEX_PASS)

    servers = [resource for resource in account.resources()
               if 'server' in resource.provides.split(',')]
    for server in servers:
        config[f'server:{server.name}'] = {
            'baseurls': str([conn.httpuri for conn in server.connections]),
            'token': server.accessToken,
            }
    write_config(config)


def read_config():
    '''Read plex server authentication from disk. Returns ConfigParser obj'''
    with open(CONFIG_FILE, 'r') as config_file:
        config = ConfigParser()
        config.read_file(config_file)
    return config


def get_servers(config):
    '''Connect to plex servers from our config and return the server objs'''
    servers = []
    for key in list(config.keys()):
        if key.startswith('server:'):
            server = key.split(':')[1]
            urls = ast.literal_eval(config[key]['baseurls'])
            server = {'name': server,
                      'urls': urls,
                      'token': config[key]['token'],
                      }
            if 'lasturl' in config[key]:
                server['lasturl'] = config[key]['lasturl']
            servers.append(server)

    for server in servers:
        print(f'Connecting to server {server["name"]}')
        connection = None

        # See if the last used URL works
        if 'lasturl' in server:
            try:
                print(f' Trying {server["lasturl"]} ... ', end='')
                connection = PlexServer(baseurl=server['lasturl'],
                                        token=server['token'],
                                        timeout=5)
                print('connected')
                server['connection'] = connection
                continue
            except requests.exceptions.ConnectTimeout:
                print('no connection')

        # Try connecting to all possible URLs
        for url in server['urls']:
            # Skip retrying lasturl
            if 'lasturl' in server:
                if url == server['lasturl']:
                    continue
            try:
                print(f' Trying {url} ... ', end='')
                connection = PlexServer(baseurl=url,
                                        token=server['token'],
                                        timeout=5)
                print('connected')
                server['lasturl'] = url
                server['connection'] = connection
                break
            except requests.exceptions.ConnectTimeout:
                print('no connection')
        if not connection:
            print(f'No connection could be made to {server["name"]}')
    return servers


def update_config(config, servers):
    '''
    After connecting to servers, update ConfigParser data with lasturl data.

    The plex API may return multiple URIs for each server.  To speed future
    connections we will save the URI that worked so we can try that first.

    Returns the updated ConfigParser.
    '''

    for server in servers:
        if 'lasturl' in server:
            config[f'server:{server["name"]}']['lasturl'] = server['lasturl']
    write_config(config)
    return config


def get_plex_movie_sections(server):
    '''
    Finds all 'Movie' library sections on a server.

    Returns a list of plexapi.library.MovieSection objects
    '''
    movie_sections = [section for section in
                      server['connection'].library.sections()
                      if section.title == 'Movies']
    print(f'Found movie section(s) {movie_sections}')
    return movie_sections


def parse_plex_movies(movie_sections):
    '''Parse all movies in the list of movie library sections.

    Populate the global list of movies, genres, and people from Plex
    '''
    global MOVIES  # noqa: W0603
    global GENRES  # noqa: W0603
    global PEOPLE  # noqa: W0603

    movie_count = 1
    for section in movie_sections:
        movie_total = len(section.all())
        for media in section.all():
            print(f'Processing({movie_count}/{movie_total}) "{media.title}"')
            movie_count += 1
            media.reload()  # Get full object metadata
            writers: List[str] = set()
            for person in media.writers:
                person = person.tag
                PEOPLE.add(person)
                writers.add(person)
            directors: List[str] = set()
            for person in media.directors:
                person = person.tag
                PEOPLE.add(person)
                directors.add(person)
            actors: List[str] = set()
            for person in media.roles:
                person = person.tag
                PEOPLE.add(person)
                actors.add(person)
            genres: List[str] = set()
            for genre in media.genres:
                genre = genre.tag
                GENRES.add(genre)
                genres.add(genre)
            MOVIES.append(Movie(name=media.title,
                                year=int(media.year or 1900),
                                studio=media.studio,
                                content_rating=media.contentRating,
                                rating=media.rating,
                                writers=tuple(writers),
                                directors=tuple(directors),
                                actors=tuple(actors),
                                genres=tuple(genres),
                                ))


def write_shelve():
    '''Store the global list of Movies, Genres, and People on disk

    To avoid pulling data from the plex server on each run we write
    a python shelve file.
    '''
    # Opening with mode 'n' will always create a new, empty database
    with shelve.open('shelve', 'n') as data:
        data['MOVIES'] = MOVIES
        data['GENRES'] = GENRES
        data['PEOPLE'] = PEOPLE


def read_shelve():
    '''Read the global list of Movies, Genres, and People from disk

    To avoid pulling data from the plex server on each run we use
    a python shelve file to persist data between runs.
    '''
    global MOVIES  # noqa: W0603
    global GENRES  # noqa: W0603
    global PEOPLE  # noqa: W0603

    with shelve.open('shelve', 'r') as data:
        MOVIES = data['MOVIES']
        GENRES = data['GENRES']
        PEOPLE = data['PEOPLE']


def generate_data():
    '''Glue code incorporating all the functions to read data from plex
    and generate our data for future runs.
    '''
    if PLEX_USER and PLEX_PASS:
        generate_config(PLEX_USER, PLEX_PASS)
    config = read_config()
    servers = get_servers(config)
    config = update_config(config, servers)
    for server in servers:
        print(f'Indexing server {server["name"]}')
        movie_sections = get_plex_movie_sections(server)
        parse_plex_movies(movie_sections)
    write_shelve()


def graph_data():
    '''Experiment with graphing Movie and Actor relationships'''
    print('Loading data from disk...', end='')
    read_shelve()
    print('done')

    # Count the number of movies an actor appears in
    actors = {person: 0 for person in PEOPLE}
    for movie in MOVIES:
        for actor in movie.actors:
            actors[actor] = actors[actor] + 1

    # Drop people that are connected to less than {MIN_RELATIONS} movies
    # And right now that will be actors
    drops = set()
    for person in PEOPLE:
        if actors[person] < MIN_RELATIONS:
            drops.add(person)
    print(f'There are {len(PEOPLE)} actors total')
    people = PEOPLE - drops
    print(f'Dropping actors with less than {MIN_RELATIONS} movies leaves '
          f'{len(people)} actors')

    graph = nx.Graph(name='Movie/Actor relationships')
    for person in people:
        graph.add_node(person)

    movie_count = 0
    for movie in MOVIES:
        relation_found = False
        for actor in movie.actors:
            if actor in people:
                if not relation_found:
                    # Only add a movie if we'll have an actor associated
                    movie_count += 1
                    graph.add_node(movie)
                    relation_found = True
                graph.add_edge(movie, actor)
    print(f'Now there are only {movie_count} movies')

    print(nx.classes.function.info(graph))
    nx.draw(graph, node_color='r', edge_color='b', with_labels=True)
    plot.show()


if __name__ == '__main__':
    # generate_data()
    graph_data()
