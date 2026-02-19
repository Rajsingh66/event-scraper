from .eventbrite import EventbriteScraper
from .meetup import MeetupScraper
from .allevents import AlleventsScraper

ALL_SCRAPERS = [
    EventbriteScraper,
    MeetupScraper,
    AlleventsScraper
]