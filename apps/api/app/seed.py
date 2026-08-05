from __future__ import annotations

from uuid import uuid4

from app.db import SessionLocal
from app.models import Item, MediaType, ModelConfig
from app.recommender.engine import DEFAULT_WEIGHTS

ANCHORS: list[dict] = [
    # Movies
    {"media_type": MediaType.movie, "title": "The Matrix", "year": 1999, "genres": ["Action", "Sci-Fi"], "creators": ["Lana Wachowski", "Lilly Wachowski"], "pop": 98},
    {"media_type": MediaType.movie, "title": "Inception", "year": 2010, "genres": ["Action", "Sci-Fi", "Thriller"], "creators": ["Christopher Nolan"], "pop": 96},
    {"media_type": MediaType.movie, "title": "Spirited Away", "year": 2001, "genres": ["Animation", "Fantasy", "Adventure"], "creators": ["Hayao Miyazaki"], "pop": 95},
    {"media_type": MediaType.movie, "title": "The Godfather", "year": 1972, "genres": ["Crime", "Drama"], "creators": ["Francis Ford Coppola"], "pop": 99},
    {"media_type": MediaType.movie, "title": "Parasite", "year": 2019, "genres": ["Thriller", "Drama"], "creators": ["Bong Joon-ho"], "pop": 94},
    {"media_type": MediaType.movie, "title": "Mad Max: Fury Road", "year": 2015, "genres": ["Action", "Adventure"], "creators": ["George Miller"], "pop": 90},
    {"media_type": MediaType.movie, "title": "Arrival", "year": 2016, "genres": ["Sci-Fi", "Drama"], "creators": ["Denis Villeneuve"], "pop": 88},
    {"media_type": MediaType.movie, "title": "Get Out", "year": 2017, "genres": ["Horror", "Thriller"], "creators": ["Jordan Peele"], "pop": 87},
    {"media_type": MediaType.movie, "title": "Blade Runner 2049", "year": 2017, "genres": ["Sci-Fi", "Drama"], "creators": ["Denis Villeneuve"], "pop": 89},
    {"media_type": MediaType.movie, "title": "Everything Everywhere All at Once", "year": 2022, "genres": ["Comedy", "Sci-Fi", "Adventure"], "creators": ["Daniels"], "pop": 91},
    {"media_type": MediaType.movie, "title": "Whiplash", "year": 2014, "genres": ["Drama", "Music"], "creators": ["Damien Chazelle"], "pop": 86},
    {"media_type": MediaType.movie, "title": "The Dark Knight", "year": 2008, "genres": ["Action", "Crime", "Drama"], "creators": ["Christopher Nolan"], "pop": 97},
    {"media_type": MediaType.movie, "title": "Interstellar", "year": 2014, "genres": ["Sci-Fi", "Adventure", "Drama"], "creators": ["Christopher Nolan"], "pop": 93},
    {"media_type": MediaType.movie, "title": "Dune", "year": 2021, "genres": ["Sci-Fi", "Adventure"], "creators": ["Denis Villeneuve"], "pop": 92},
    {"media_type": MediaType.movie, "title": "Princess Mononoke", "year": 1997, "genres": ["Animation", "Fantasy", "Adventure"], "creators": ["Hayao Miyazaki"], "pop": 90},
    {"media_type": MediaType.movie, "title": "Heat", "year": 1995, "genres": ["Crime", "Drama", "Action"], "creators": ["Michael Mann"], "pop": 85},
    {"media_type": MediaType.movie, "title": "Her", "year": 2013, "genres": ["Romance", "Sci-Fi", "Drama"], "creators": ["Spike Jonze"], "pop": 84},
    {"media_type": MediaType.movie, "title": "No Country for Old Men", "year": 2007, "genres": ["Crime", "Thriller", "Drama"], "creators": ["Coen Brothers"], "pop": 88},
    {"media_type": MediaType.movie, "title": "The Social Network", "year": 2010, "genres": ["Drama", "Biography"], "creators": ["David Fincher"], "pop": 83},
    {"media_type": MediaType.movie, "title": "Ex Machina", "year": 2014, "genres": ["Sci-Fi", "Thriller"], "creators": ["Alex Garland"], "pop": 82},
    # TV
    {"media_type": MediaType.tv, "title": "Breaking Bad", "year": 2008, "genres": ["Crime", "Drama", "Thriller"], "creators": ["Vince Gilligan"], "pop": 99},
    {"media_type": MediaType.tv, "title": "The Wire", "year": 2002, "genres": ["Crime", "Drama"], "creators": ["David Simon"], "pop": 97},
    {"media_type": MediaType.tv, "title": "Chernobyl", "year": 2019, "genres": ["Drama", "History"], "creators": ["Craig Mazin"], "pop": 94},
    {"media_type": MediaType.tv, "title": "The Expanse", "year": 2015, "genres": ["Sci-Fi", "Drama"], "creators": ["Mark Fergus", "Hawk Ostby"], "pop": 90},
    {"media_type": MediaType.tv, "title": "Dark", "year": 2017, "genres": ["Sci-Fi", "Mystery", "Thriller"], "creators": ["Baran bo Odar"], "pop": 91},
    {"media_type": MediaType.tv, "title": "Succession", "year": 2018, "genres": ["Drama", "Comedy"], "creators": ["Jesse Armstrong"], "pop": 93},
    {"media_type": MediaType.tv, "title": "The Bear", "year": 2022, "genres": ["Comedy", "Drama"], "creators": ["Christopher Storer"], "pop": 89},
    {"media_type": MediaType.tv, "title": "Severance", "year": 2022, "genres": ["Sci-Fi", "Thriller", "Drama"], "creators": ["Dan Erickson"], "pop": 92},
    {"media_type": MediaType.tv, "title": "Andor", "year": 2022, "genres": ["Sci-Fi", "Action", "Drama"], "creators": ["Tony Gilroy"], "pop": 90},
    {"media_type": MediaType.tv, "title": "True Detective", "year": 2014, "genres": ["Crime", "Drama", "Mystery"], "creators": ["Nic Pizzolatto"], "pop": 88},
    {"media_type": MediaType.tv, "title": "Better Call Saul", "year": 2015, "genres": ["Crime", "Drama"], "creators": ["Vince Gilligan"], "pop": 95},
    {"media_type": MediaType.tv, "title": "The Leftovers", "year": 2014, "genres": ["Drama", "Mystery"], "creators": ["Damon Lindelof"], "pop": 86},
    {"media_type": MediaType.tv, "title": "Mr. Robot", "year": 2015, "genres": ["Drama", "Thriller", "Crime"], "creators": ["Sam Esmail"], "pop": 87},
    {"media_type": MediaType.tv, "title": "Arcane", "year": 2021, "genres": ["Animation", "Action", "Adventure"], "creators": ["Christian Linke"], "pop": 94},
    {"media_type": MediaType.tv, "title": "Shogun", "year": 2024, "genres": ["Drama", "History", "Adventure"], "creators": ["Rachel Kondo", "Justin Marks"], "pop": 93},
    {"media_type": MediaType.tv, "title": "The Mandalorian", "year": 2019, "genres": ["Sci-Fi", "Action", "Adventure"], "creators": ["Jon Favreau"], "pop": 88},
    {"media_type": MediaType.tv, "title": "Fleabag", "year": 2016, "genres": ["Comedy", "Drama"], "creators": ["Phoebe Waller-Bridge"], "pop": 90},
    {"media_type": MediaType.tv, "title": "Slow Horses", "year": 2022, "genres": ["Thriller", "Drama", "Comedy"], "creators": ["Will Smith"], "pop": 87},
    {"media_type": MediaType.tv, "title": "Foundation", "year": 2021, "genres": ["Sci-Fi", "Drama"], "creators": ["David S. Goyer"], "pop": 80},
    {"media_type": MediaType.tv, "title": "Only Murders in the Building", "year": 2021, "genres": ["Comedy", "Crime", "Mystery"], "creators": ["Steve Martin", "John Hoffman"], "pop": 84},
    # Audiobooks / books
    {"media_type": MediaType.audiobook, "title": "Project Hail Mary", "year": 2021, "genres": ["Sci-Fi", "Adventure"], "creators": ["Andy Weir", "Ray Porter"], "pop": 95},
    {"media_type": MediaType.audiobook, "title": "Dune", "year": 1965, "genres": ["Sci-Fi"], "creators": ["Frank Herbert"], "pop": 94},
    {"media_type": MediaType.audiobook, "title": "The Name of the Wind", "year": 2007, "genres": ["Fantasy"], "creators": ["Patrick Rothfuss"], "pop": 90},
    {"media_type": MediaType.audiobook, "title": "Mistborn: The Final Empire", "year": 2006, "genres": ["Fantasy"], "creators": ["Brandon Sanderson"], "pop": 92},
    {"media_type": MediaType.audiobook, "title": "Ready Player One", "year": 2011, "genres": ["Sci-Fi", "Adventure"], "creators": ["Ernest Cline"], "pop": 85},
    {"media_type": MediaType.audiobook, "title": "The Martian", "year": 2011, "genres": ["Sci-Fi"], "creators": ["Andy Weir"], "pop": 93},
    {"media_type": MediaType.audiobook, "title": "11/22/63", "year": 2011, "genres": ["Sci-Fi", "Thriller"], "creators": ["Stephen King"], "pop": 88},
    {"media_type": MediaType.audiobook, "title": "Circe", "year": 2018, "genres": ["Fantasy", "Mythology"], "creators": ["Madeline Miller"], "pop": 89},
    {"media_type": MediaType.audiobook, "title": "The Way of Kings", "year": 2010, "genres": ["Fantasy"], "creators": ["Brandon Sanderson"], "pop": 94},
    {"media_type": MediaType.audiobook, "title": "Children of Time", "year": 2015, "genres": ["Sci-Fi"], "creators": ["Adrian Tchaikovsky"], "pop": 87},
    {"media_type": MediaType.book, "title": "Neuromancer", "year": 1984, "genres": ["Sci-Fi", "Cyberpunk"], "creators": ["William Gibson"], "pop": 90},
    {"media_type": MediaType.book, "title": "The Left Hand of Darkness", "year": 1969, "genres": ["Sci-Fi"], "creators": ["Ursula K. Le Guin"], "pop": 88},
    {"media_type": MediaType.book, "title": "Klara and the Sun", "year": 2021, "genres": ["Sci-Fi", "Literary"], "creators": ["Kazuo Ishiguro"], "pop": 84},
    {"media_type": MediaType.book, "title": "Piranesi", "year": 2020, "genres": ["Fantasy", "Literary"], "creators": ["Susanna Clarke"], "pop": 86},
    {"media_type": MediaType.book, "title": "The Three-Body Problem", "year": 2008, "genres": ["Sci-Fi"], "creators": ["Liu Cixin"], "pop": 91},
    # Comics
    {"media_type": MediaType.comic, "title": "Watchmen", "year": 1986, "genres": ["Superhero", "Drama"], "creators": ["Alan Moore", "Dave Gibbons"], "pop": 96},
    {"media_type": MediaType.comic, "title": "Saga", "year": 2012, "genres": ["Sci-Fi", "Fantasy"], "creators": ["Brian K. Vaughan", "Fiona Staples"], "pop": 93},
    {"media_type": MediaType.comic, "title": "Sandman", "year": 1989, "genres": ["Fantasy", "Horror"], "creators": ["Neil Gaiman"], "pop": 95},
    {"media_type": MediaType.comic, "title": "Monstress", "year": 2015, "genres": ["Fantasy", "Horror"], "creators": ["Marjorie Liu", "Sana Takeda"], "pop": 88},
    {"media_type": MediaType.comic, "title": "Descender", "year": 2015, "genres": ["Sci-Fi"], "creators": ["Jeff Lemire", "Dustin Nguyen"], "pop": 84},
    {"media_type": MediaType.comic, "title": "Bone", "year": 1991, "genres": ["Fantasy", "Adventure"], "creators": ["Jeff Smith"], "pop": 90},
    {"media_type": MediaType.comic, "title": "Blankets", "year": 2003, "genres": ["Memoir", "Drama"], "creators": ["Craig Thompson"], "pop": 85},
    {"media_type": MediaType.comic, "title": "Invincible", "year": 2003, "genres": ["Superhero", "Action"], "creators": ["Robert Kirkman"], "pop": 91},
    {"media_type": MediaType.comic, "title": "East of West", "year": 2013, "genres": ["Sci-Fi", "Western"], "creators": ["Jonathan Hickman"], "pop": 86},
    {"media_type": MediaType.comic, "title": "Hellboy", "year": 1993, "genres": ["Horror", "Fantasy"], "creators": ["Mike Mignola"], "pop": 89},
    # Extra catalog (non-anchor) for recommendations to surface
    {"media_type": MediaType.movie, "title": "Tenet", "year": 2020, "genres": ["Action", "Sci-Fi", "Thriller"], "creators": ["Christopher Nolan"], "pop": 78, "anchor": False},
    {"media_type": MediaType.movie, "title": "Sicario", "year": 2015, "genres": ["Crime", "Thriller", "Action"], "creators": ["Denis Villeneuve"], "pop": 80, "anchor": False},
    {"media_type": MediaType.movie, "title": "Howl's Moving Castle", "year": 2004, "genres": ["Animation", "Fantasy", "Adventure"], "creators": ["Hayao Miyazaki"], "pop": 88, "anchor": False},
    {"media_type": MediaType.movie, "title": "Prisoners", "year": 2013, "genres": ["Crime", "Drama", "Thriller"], "creators": ["Denis Villeneuve"], "pop": 81, "anchor": False},
    {"media_type": MediaType.tv, "title": "Devs", "year": 2020, "genres": ["Sci-Fi", "Thriller", "Drama"], "creators": ["Alex Garland"], "pop": 75, "anchor": False},
    {"media_type": MediaType.tv, "title": "For All Mankind", "year": 2019, "genres": ["Sci-Fi", "Drama", "History"], "creators": ["Ronald D. Moore"], "pop": 82, "anchor": False},
    {"media_type": MediaType.audiobook, "title": "Hyperion", "year": 1989, "genres": ["Sci-Fi"], "creators": ["Dan Simmons"], "pop": 86, "anchor": False},
    {"media_type": MediaType.audiobook, "title": "Words of Radiance", "year": 2014, "genres": ["Fantasy"], "creators": ["Brandon Sanderson"], "pop": 91, "anchor": False},
    {"media_type": MediaType.comic, "title": "Paper Girls", "year": 2015, "genres": ["Sci-Fi", "Mystery"], "creators": ["Brian K. Vaughan"], "pop": 83, "anchor": False},
    {"media_type": MediaType.comic, "title": "Y: The Last Man", "year": 2002, "genres": ["Sci-Fi", "Drama"], "creators": ["Brian K. Vaughan"], "pop": 87, "anchor": False},
]


def seed() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Item).count()
        if existing == 0:
            for row in ANCHORS:
                db.add(
                    Item(
                        id=uuid4(),
                        media_type=row["media_type"],
                        title=row["title"],
                        sort_title=row["title"],
                        genres=row["genres"],
                        creators=row["creators"],
                        release_year=row["year"],
                        popularity=float(row["pop"]),
                        is_anchor=row.get("anchor", True),
                        description=f"Seed catalog title: {row['title']}",
                    )
                )
            db.commit()
            print(f"Seeded {len(ANCHORS)} catalog items")
        else:
            print(f"Catalog already has {existing} items; skipping item seed")

        for mt in MediaType:
            cfg = (
                db.query(ModelConfig)
                .filter(ModelConfig.media_type == mt, ModelConfig.name == "default")
                .first()
            )
            if not cfg:
                weights = dict(DEFAULT_WEIGHTS)
                # Mild per-type tuning
                if mt == MediaType.tv:
                    weights["novelty"] = 0.08
                    weights["content"] = 0.5
                elif mt == MediaType.comic:
                    weights["content"] = 0.5
                    weights["popularity"] = 0.2
                elif mt == MediaType.game:
                    weights["novelty"] = 0.15
                db.add(ModelConfig(media_type=mt, name="default", weights=weights, active=True))
        db.commit()
        print("Model configs ensured")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
