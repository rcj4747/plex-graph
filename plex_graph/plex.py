'''
Playing around with pulling movie data from plex servers and graphing
relationships between movies via actors.
'''
import ast
import logging
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

import plexapi
import requests
from plexapi.library import LibrarySection
from plexapi.myplex import MyPlexAccount, MyPlexResource
from plexapi.server import PlexServer

from plex_graph.data import Movie, MovieData
from plex_graph.exceptions import PlexUserAuthFailure, UnknownFailure

CONFIG_PATH: Path = Path.home().joinpath('.config', 'plex-graph')
CONFIG_FILE: Path = CONFIG_PATH / 'plex_servers'


@dataclass()
class PlexServerConfig:
    '''PlexServer connection data'''
    name: str
    urls: List[str]
    token: str
    lasturl: Optional[str] = None
    connection: Optional[PlexServer] = None


def server_config_write(config: ConfigParser) -> None:
    '''Store plex server authentication on disk'''
    if not CONFIG_PATH.exists():
        logging.debug('Creating config directory %s', CONFIG_PATH)
        CONFIG_PATH.mkdir(parents=True)
    logging.debug('Storing/updating Plex server connection data')
    with CONFIG_FILE.open(mode='w') as config_file:
        config.write(config_file)


def account_auth(user: str, password: str) -> None:
    '''Authenticate with Plex service and store plex server keys'''
    config: ConfigParser = ConfigParser()
    try:
        account: MyPlexAccount = MyPlexAccount(user, password)
    except plexapi.exceptions.BadRequest as excp:
        if excp.startswith('(401) unauthorized'):
            raise PlexUserAuthFailure(
                'Plex user name or password is incorrect')
        raise UnknownFailure('Received "BadRequest" from plexapi: %s',
                             excp)
    logging.debug('Authenticated to account %s', account.username)

    servers: List[MyPlexResource]
    servers = [resource for resource in account.resources()
               if 'server' in resource.provides.split(',')]
    for server in servers:
        logging.debug('Retrieved connection data for server "%s"', server.name)
        config[f'server:{server.name}'] = {
            'baseurls': str([conn.httpuri for conn in server.connections]),
            'token': server.accessToken,
        }
    server_config_write(config)


def server_read() -> ConfigParser:
    '''Read plex server authentication from disk.'''
    with CONFIG_FILE.open(mode='r') as config_file:
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


def server_config_update(
        config: ConfigParser,
        servers: List[PlexServerConfig]) -> ConfigParser:
    '''
    After connecting to servers, update ConfigParser data with lasturl data.

    The plex API may return multiple URIs for each server.  To speed future
    connections we will save the URI that worked so we can try that first.

    Returns the updated ConfigParser.
    '''

    for server in servers:
        if server.lasturl:
            logging.debug('Adding lasturl(%s) for %s',
                          server.lasturl, server.name)
            config[f'server:{server.name}']['lasturl'] = server.lasturl
    server_config_write(config)
    return config


def get_movie_sections(server: PlexServer) -> List[LibrarySection]:
    '''
    Finds all 'Movie' library sections on a server.

    Returns a list of plexapi.library.MovieSection objects
    '''
    movie_sections = [section for section in
                      server.connection.library.sections()
                      if section.title == 'Movies']
    logging.debug('Found movie section(s) %s', movie_sections)
    return movie_sections


def parse_movies(movie_sections: List[LibrarySection]) -> MovieData:
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
