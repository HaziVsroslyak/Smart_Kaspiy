import unittest

from route_weather import ScenarioWeather, resolve_route_weather


class RouteWeatherTests(unittest.TestCase):
    def test_limits_and_gusts(self) -> None:
        for wind, gust, wave, restricted in [
            (19.9, None, 2.5, False), (20, None, 1, True),
            (4, 20, None, True), (0, None, 2.51, True), (0, None, None, False),
        ]:
            with self.subTest(wind=wind, gust=gust, wave=wave):
                result = resolve_route_weather(ScenarioWeather(
                    source="scenario", wind_speed_ms=wind, wind_gust_ms=gust, wave_height_m=wave,
                ), 0, None)
                self.assertEqual(result.sea_restricted, restricted)
                self.assertEqual(result.wave_height_m, wave)
                self.assertLessEqual(result.severity, 10)

    def test_manual_compatibility(self) -> None:
        result = resolve_route_weather(None, 7, None)
        self.assertEqual(result.severity, 7)
        self.assertFalse(result.sea_restricted)
        self.assertIsNone(result.wave_height_m)
