"""Championship standings snapshot, copied from omarchy-wec's Panel.qml.

These are not fetched; the window labels them with SNAPSHOT_DATE so nobody
mistakes them for live data.
"""

SNAPSHOT_DATE = "4 Sep 2026"
SEASON = "2026 FIA World Endurance Championship"
SOURCE_URL = "https://www.fiawec.com/en/page/manufacturers-classification"

# (key, chip label, title)
CATEGORIES = [
    ("manufacturers", "HYPERCAR MFRS", "HYPERCAR MANUFACTURERS"),
    ("hypercarDrivers", "HYPERCAR DRIVERS", "HYPERCAR DRIVERS"),
    ("lmgt3Teams", "LMGT3 TEAMS", "LMGT3 TEAMS"),
    ("lmgt3Drivers", "LMGT3 DRIVERS", "LMGT3 DRIVERS"),
]

# (position, name, detail, points)
STANDINGS = {
    "manufacturers": [
        (1, "Toyota", "", 132),
        (2, "BMW", "", 127),
        (3, "Ferrari", "", 88),
        (4, "Cadillac", "", 60),
        (5, "Alpine", "", 41),
        (6, "Aston Martin", "", 40),
        (7, "Peugeot", "", 15),
        (8, "Genesis", "", 6),
    ],
    "hypercarDrivers": [
        (1, "René Rast / Robin Frijns", "#20 BMW", 75),
        (2, "Kobayashi / Conway / de Vries", "#7 Toyota", 75),
        (3, "Sheldon van der Linde", "#20 BMW", 65),
        (4, "Pier Guidi / Giovinazzi / Calado", "#51 Ferrari", 57),
        (5, "Hartley / Hirakawa / Buemi", "#8 Toyota", 56),
        (6, "Magnussen / Marciello", "#15 BMW", 50),
    ],
    "lmgt3Teams": [
        (1, "TF Sport", "#33 Corvette", 76),
        (2, "The Bend Manthey", "#92 Porsche", 49),
        (3, "Team WRT", "#69 BMW", 43),
        (4, "Racing Team Turkey by TF", "#34 Corvette", 43),
        (5, "Vista AF Corse", "#21 Ferrari", 42),
        (6, "Akkodis ASP Team", "#87 Lexus", 38),
    ],
    "lmgt3Drivers": [
        (1, "Jonny Edgar", "#33 Corvette", 76),
        (2, "Nicky Catsburg", "#33 Corvette", 72),
        (3, "Ben Keating", "#33 Corvette", 54),
        (4, "Pera / Lietz / Shahin", "#92 Porsche", 49),
        (5, "McIntosh / Harper / Thompson", "#69 BMW", 43),
        (6, "Eastwood / Dempsey / Yoluç", "#34 Corvette", 43),
    ],
}
