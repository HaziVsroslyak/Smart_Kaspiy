`routeGeometry.ts` contains schematic offshore corridors used only for map display.
Times/costs remain the backend graph's illustrative estimates; these coordinates
are not used to calculate sailing distances. Inland terminal markers and offshore
gates are separate. River/delta approaches and surveyed shipping lanes are absent.

`road-routes.json` contains saved OSRM/OpenStreetMap driving geometries for
Astrakhan–Makhachkala, Makhachkala–Enzeli and Enzeli–Rasht. The international
variant passes through Georgia and Azerbaijan (three border crossings); it is
not a direct Russia–Azerbaijan two-border variant. Geometry was simplified with
a tolerance of 0.0001 degrees (roughly 10 m), retaining endpoints. Reverse
display reuses the reversed line: directional traffic rules are not re-evaluated.
Data was retrieved on 2026-11-12, stored locally, and is not refreshed at runtime.
OSRM's driving profile does not verify truck dimensions, axle loads, freight
permissions or current border availability. Graph time/cost/CO2 remain demo
assumptions, independent of the saved geometry's length.

OSRM route API: https://project-osrm.org/docs/v26.6.1/http.html
Map data © OpenStreetMap contributors: https://www.openstreetmap.org/copyright

`caspian-water.json` is the Caspian polygon extracted from Natural Earth's
1:10m Ocean dataset (including its interior rings), used by regression tests only:
https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_ocean.geojson
Natural Earth data is public domain: https://www.naturalearthdata.com/about/terms-of-use/
The contour is generalized; tests check water containment and coastline crossings
at this dataset's resolution, not navigational safety or current depths.
