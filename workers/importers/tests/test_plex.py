from __future__ import annotations

import unittest
from xml.etree import ElementTree

from workers.importers.plex import PlexConnector


class PlexConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = PlexConnector("http://plex.local:32400/")

    def test_normalizes_movie_metadata(self) -> None:
        element = ElementTree.fromstring(
            """
            <Video ratingKey="42" type="movie" title="Arrival" titleSort="Arrival"
                   year="2016" duration="6960000" summary="First contact."
                   thumb="/library/metadata/42/thumb/1">
              <Genre tag="Science Fiction" />
              <Genre tag="Drama" />
              <Director tag="Denis Villeneuve" />
              <Writer tag="Eric Heisserer" />
              <Collection tag="First Contact" />
            </Video>
            """
        )

        item = self.connector._normalize_element(element, "movie")

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.external_id, "42")
        self.assertEqual(item.media_type, "movie")
        self.assertEqual(item.release_year, 2016)
        self.assertEqual(item.runtime_or_length, 6960)
        self.assertEqual(item.genres, ["Science Fiction", "Drama"])
        self.assertEqual(item.creators, ["Denis Villeneuve", "Eric Heisserer"])
        self.assertNotIn("X-Plex-Token", item.cover_url or "")

    def test_maps_partial_tv_progress_to_consume(self) -> None:
        element = ElementTree.fromstring(
            '<Directory ratingKey="84" type="show" title="Severance" '
            'leafCount="18" viewedLeafCount="7" />'
        )

        consumption = self.connector._normalize_consumption(element, "84")

        self.assertIsNotNone(consumption)
        assert consumption is not None
        self.assertEqual(consumption.interaction_type, "consume")
        self.assertAlmostEqual(consumption.progress or 0, 7 / 18)

    def test_maps_watched_movie_to_finish(self) -> None:
        element = ElementTree.fromstring(
            '<Video ratingKey="91" type="movie" title="Dune" '
            'duration="9300000" viewOffset="9300000" viewCount="1" />'
        )

        consumption = self.connector._normalize_consumption(element, "91")

        self.assertIsNotNone(consumption)
        assert consumption is not None
        self.assertEqual(consumption.interaction_type, "finish")
        self.assertEqual(consumption.progress, 1.0)
        self.assertEqual(consumption.confidence, 0.9)

    def test_ignores_unwatched_item(self) -> None:
        element = ElementTree.fromstring(
            '<Video ratingKey="7" type="movie" title="Unwatched" duration="1000" />'
        )

        self.assertIsNone(self.connector._normalize_consumption(element, "7"))


if __name__ == "__main__":
    unittest.main()
