#!/usr/bin/env python3
'''
'''
import ast
# import pdb
from configparser import ConfigParser
from dataclasses import dataclass, field
from typing import List

import requests

from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer

PLEX_USER: str = ''
PLEX_PASS: str = ''
CONFIG_FILE: str = 'config.ini'


def write_config(config: ConfigParser) -> None:
    with open(CONFIG_FILE, 'w') as config_file:
        config.write(config_file)


def generate_config(user: str, password: str) -> None:
    config: ConfigParser = ConfigParser()
    config['auth'] = {'user': user, 'pass': password}
    account = MyPlexAccount(PLEX_USER, PLEX_PASS)
    # or server = account.resource('<SERVERNAME>').connect()

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


@dataclass
class Genre:
    name: str
    id: int


@dataclass
class Person:
    name: str
    id: str
    role: str


@dataclass
class Movie:
    name: str
    year: int
    studio: str
    contentRating: str
    rating: str
    writers: List[Person] = field(default_factory=list)
    directors: List[Person] = field(default_factory=list)
    actors: List[Person] = field(default_factory=list)
    genres: List[Genre] = field(default_factory=list)


def main():
    if PLEX_USER and PLEX_PASS:
        generate_config(PLEX_USER, PLEX_PASS)
    config = read_config()
    servers = get_servers(config)
    config = update_config(config, servers)
    for server in servers:
        print(f'Indexing server {server["name"]}')
        movie_sections = [section for section in
                          server['connection'].library.sections()
                          if section.title == 'Movies']
        print(f'Found movie section(s) {movie_sections}')
        for section in movie_sections:
            for media in section.all():
                # Any of these lists could be empty
                media.reload()  # Get full object metadata
                print(media.title)
                print(media.year)
                print(media.studio)
                print(media.rating)
                print(media.contentRating)
                if media.writers:
                    print(f' w: #{len(media.writers)}')
                    print(f' w: {media.writers[0].tag}')  # Writer name
                    print(f' w: {media.writers[0].TAG}')  # 'Writer'
                    print(f' w: {media.writers[0].id}')  # ID or None
                if media.directors:
                    print(f' d: #{len(media.directors)}')
                    print(f' d: {media.directors[0].tag}')  # Director name
                    print(f' d: {media.directors[0].TAG}')  # 'Director'
                    print(f' d: {media.directors[0].id}')  # ID or None
                if media.actors:
                    print(f' a: #{len(media.actors)}')
                    print(f' a: {media.actors[0].tag}')  # Actor name
                    print(f' a: {media.actors[0].TAG}')  # 'Role'
                    print(f' a: {media.actors[0].id}')  # ID or None
                if media.genres:
                    print(f' g: #{len(media.genres)}')
                    print(f' g: {media.genres[0].tag}')  # Genre name
                    print(f' g: {media.genres[0].TAG}')  # 'Genre'
                    print(f' g: {media.genres[0].id}')  # ID or None
#    pdb.set_trace()


if __name__ == '__main__':
    main()
