'''Exceptions for the module'''


class PlexGraphException(Exception):
    '''Base class for all plex_graph exceptions'''


class PlexUserAuthFailure(PlexGraphException):
    '''Plex user account authorization failure'''


class PlexServerAuthFailure(PlexGraphException):
    '''Plex server token authorization failure'''


class NetworkFailure(PlexGraphException):
    '''Generic network connection error'''


class UnknownFailure(PlexGraphException):
    '''Unknown runtime error'''
