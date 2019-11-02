#!/usr/bin/env python3
'''
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


GENRES: Set[str] = set()
PEOPLE: Set[str] = set()
MOVIES: List[Movie] = []


def write_config(config: ConfigParser) -> None:
    with open(CONFIG_FILE, 'w') as config_file:
        config.write(config_file)


def generate_config(user: str, password: str) -> None:
    config: ConfigParser = ConfigParser()
    config['auth'] = {'user': user, 'pass': password}
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
    with open(CONFIG_FILE, 'r') as config_file:
        config = ConfigParser()
        config.read_file(config_file)
    return config


def get_servers(config):
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
    for server in servers:
        if 'lasturl' in server:
            config[f'server:{server["name"]}']['lasturl'] = server['lasturl']
    write_config(config)
    return config


def get_plex_movie_sections(server):
    movie_sections = [section for section in
                      server['connection'].library.sections()
                      if section.title == 'Movies']
    print(f'Found movie section(s) {movie_sections}')
    return movie_sections


def get_plex_movies(movie_sections):
    global MOVIES
    global GENRES
    global PEOPLE

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
    # Opening with mode 'n' will always create a new, empty database
    with shelve.open('shelve', 'n') as data:
        data['MOVIES'] = MOVIES
        data['GENRES'] = GENRES
        data['PEOPLE'] = PEOPLE


def read_shelve():
    global MOVIES
    global GENRES
    global PEOPLE

    with shelve.open('shelve', 'r') as data:
        MOVIES = data['MOVIES']
        GENRES = data['GENRES']
        PEOPLE = data['PEOPLE']


def generate_data():
    if PLEX_USER and PLEX_PASS:
        generate_config(PLEX_USER, PLEX_PASS)
    config = read_config()
    servers = get_servers(config)
    config = update_config(config, servers)
    for server in servers:
        print(f'Indexing server {server["name"]}')
        movie_sections = get_plex_movie_sections(server)
        get_plex_movies(movie_sections)
    write_shelve()


def graph_data():
    print('Loading data from disk...', end='')
    read_shelve()
    print('done')

    # Drop people that are connected to less than 2 movies
    # And right now that will be actors
    actors = {person: 0 for person in PEOPLE}
    for movie in MOVIES:
        for actor in movie.actors:
            if actor == "Frank Morgan":
                print(f'Frank Morgan in {movie.name}')
            actors[actor] = actors[actor] + 1

    drops = set()
    for person in PEOPLE:
        if actors[person] < MIN_RELATIONS:
            drops.add(person)

    print(f'There are {len(PEOPLE)} actors and we will drop {len(drops)}')
    people = PEOPLE - drops
    print(f'Now there are only {len(people)} actors')

    graph = nx.Graph()
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

    nx.draw(graph, node_color='r', edge_color='b', with_labels=True)
    plot.show()


if __name__ == '__main__':
    # generate_data()
    graph_data()
