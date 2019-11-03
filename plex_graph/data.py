'''
Playing around with pulling movie data from plex servers and graphing
relationships between movies via actors.
'''
import logging
import math
import shelve
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set, Tuple

import matplotlib.pyplot as plot
import networkx as nx

SHELVE_PATH: Path = Path.home().joinpath('.cache', 'plex-graph')
SHELVE_FILE: Path = SHELVE_PATH / 'movie_data'


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


def cache_store(movie_data: MovieData) -> None:
    '''Store the global list of Movies, Genres, and People on disk

    To avoid pulling data from the plex server on each run we write
    a python shelve file.
    '''
    if not SHELVE_PATH.exists():
        SHELVE_PATH.mkdir(parents=True)
    # Opening with mode 'n' will always create a new, empty database
    with shelve.open(str(SHELVE_FILE), 'n') as data:
        data['version'] = 1
        data['movie_data'] = movie_data


def cache_read() -> MovieData:
    '''Read the global list of Movies, Genres, and People from disk

    To avoid pulling data from the plex server on each run we use
    a python shelve file to persist data between runs.
    '''
    movie_data: MovieData = MovieData()
    with shelve.open(str(SHELVE_FILE), 'r') as data:
        if 'version' in data:
            logging.debug('Found version:%d data', data['version'])
            if data['version'] == 1:
                movie_data = data['movie_data']
                return movie_data
        raise RuntimeError(f'Unknown data format, remove {SHELVE_FILE} '
                           'and regenerate data')


def rating_histogram() -> None:
    logging.debug('Loading data from disk')
    movie_data: MovieData = cache_read()

    hist = [0 for x in range(10)]
    for movie in movie_data.movies:
        if not movie.rating:
            continue
        rating = float(movie.rating)
        rating_int = int(rating)
        i = math.floor(rating) + (0 if ((rating - rating_int) * 10) < 5 else 1)
        hist[i - 1] += 1
    print('rating:   ', end='')
    for idx in range(1, 11):
        print(f'{idx: 4}', end='')
    print()
    print('#movies:  ', end='')
    for idx in range(0, 10):
        print(f'{hist[idx]: 4}', end='')
    print()


def graph(min_relations: int) -> None:
    '''Experiment with graphing Movie and Actor relationships'''
    logging.debug('Loading data from disk')
    movie_data: MovieData = cache_read()

    # Count the number of movies an actor appears in
    actors = {person: 0 for person in movie_data.people}
    for movie in movie_data.movies:
        for actor in movie.actors:
            actors[actor] = actors[actor] + 1

    # Drop people that are connected to less than {min_relations} movies
    # And right now that will be actors
    drops = set()
    for person in movie_data.people:
        if actors[person] < min_relations:
            drops.add(person)
    logging.info('There are %d actors total', len(movie_data.people))
    movie_data.people = movie_data.people - drops
    logging.info('Dropping actors with less than %d movies leaves %d actors',
                 min_relations, len(movie_data.people))

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
